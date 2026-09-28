from flask import Blueprint, request, redirect, render_template
from models import URL, ClickEvent
from extensions import db
from sqlalchemy import func, text
from urllib.parse import urlparse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from extensions import redis_client
from datetime import datetime, time, timedelta, timezone
from tasks import process_click_event 
from extensions import rq_queue 
import re


url_routes = Blueprint("url_routes", __name__)

RESERVED_ALIASES = {"shorten", "analytics", "static"}
ALIAS_PATTERN = re.compile(r"[a-z0-9_-]{3,50}")


@url_routes.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@url_routes.route("/shorten", methods = ["POST"])
def shorten_url():
    data = request.get_json(silent=True)

    if data is None:
        return {"error": "Request body must be valid JSON"}, 400
    
    original_url = data.get("original_url")

    if not original_url:
        return {"error": "original_url is required"}, 400

    parsed_url = urlparse(original_url)

    if not parsed_url.scheme or not parsed_url.netloc:
        return {"error": "Invalid URL"}, 400

    alias_provided = "alias" in data
    alias = data.get("alias")

    if alias_provided:
        if not isinstance(alias, str):
            return {"error": "Alias must be 3-50 letters, numbers, hyphens, or underscores only"}, 400

        alias = alias.lower()

        if not ALIAS_PATTERN.fullmatch(alias):
            return {"error": "Alias must be 3-50 letters, numbers, hyphens, or underscores"}, 400

        if alias in RESERVED_ALIASES:
            return {"error": "Alias is not available. Please choose another one."}, 409

    try: 
        if alias_provided:
            if URL.query.filter_by(short_url=alias).first():
                return {"error": "Alias is not available. Please choose another one."}, 409

            short_url = alias
            url = URL(
                original_url=original_url,
                short_url=short_url
            )

        else:
            result = db.session.execute(
            text("SELECT nextval(pg_get_serial_sequence('url', 'id'))")
            )

            next_id = result.scalar()

            short_url = encode_base62(next_id)

            url = URL(
                id=next_id,
                original_url=original_url,
                short_url=short_url
            )

        db.session.add(url)
        db.session.commit()

    except IntegrityError:
        db.session.rollback()

        if alias_provided:
            return {"error": "Alias is not available. Please choose another one."}, 409

        return {"error": "Database error"}, 500

    except SQLAlchemyError: 
        db.session.rollback() 
        return {"error": "Database error"}, 500 

    return {"short_url": short_url}, 201


@url_routes.route("/<short_url>/analytics", methods=["GET"])
def get_analytics(short_url):
    try:
        url = URL.query.filter_by(short_url=short_url).first()

        if not url:
            return {"error": "Short URL not found"}, 404

        total_clicks = (
            db.session.query(func.count(ClickEvent.id))
            .filter(ClickEvent.url_id == url.id)
            .scalar()
        )

        unique_visitors = (
            db.session.query(func.count(func.distinct(ClickEvent.visitor_hash)))
            .filter(
                ClickEvent.url_id == url.id,
                ClickEvent.visitor_hash.isnot(None),
            )
            .scalar()
        )

        country_clicks = (
            db.session.query(
                ClickEvent.country,
                func.count(ClickEvent.id).label("clicks"),
            )
            .filter(
                ClickEvent.url_id == url.id,
                ClickEvent.country.isnot(None),
            )
            .group_by(ClickEvent.country)
            .order_by(
                func.count(ClickEvent.id).desc(),
                ClickEvent.country.asc(),
            )
            .limit(5)
            .all()
        )

        referrer_clicks = (
            db.session.query(
                ClickEvent.referrer,
                func.count(ClickEvent.id).label("clicks"),
            )
            .filter(
                ClickEvent.url_id == url.id,
                ClickEvent.referrer.isnot(None),
            )
            .group_by(ClickEvent.referrer)
            .order_by(
                func.count(ClickEvent.id).desc(),
                ClickEvent.referrer.asc(),
            )
            .limit(5)
            .all()
        )

        today_utc = datetime.now(timezone.utc).date()
        start_date = today_utc - timedelta(days=6)
        range_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        range_end = range_start + timedelta(days=7)

        if db.engine.dialect.name == "postgresql":
            click_date = func.date(ClickEvent.timestamp.op("AT TIME ZONE")("UTC"))
        else:
            click_date = func.date(ClickEvent.timestamp)

        daily_clicks = (
            db.session.query(
                click_date.label("date"),
                func.count(ClickEvent.id).label("clicks"),
            )
            .filter(
                ClickEvent.url_id == url.id,
                ClickEvent.timestamp >= range_start,
                ClickEvent.timestamp < range_end,
            )
            .group_by(click_date)
            .order_by(click_date.asc())
            .all()
        )

    except SQLAlchemyError:
        db.session.rollback()
        return {"error": "Database error"}, 500

    clicks_by_date = {
        str(click_date): clicks for click_date, clicks in daily_clicks
    }
    clicks_over_time = []
    for day_offset in range(7):
        current_date = start_date + timedelta(days=day_offset)
        current_date_string = current_date.isoformat()
        clicks_over_time.append(
            {
                "date": current_date_string,
                "clicks": clicks_by_date.get(current_date_string, 0),
            }
        )

    return {
        "total_clicks": total_clicks,
        "unique_visitors": unique_visitors,
        "top_countries": [
            {"country": country, "clicks": clicks}
            for country, clicks in country_clicks
        ],
        "top_referrers": [
            {"referrer": referrer, "clicks": clicks}
            for referrer, clicks in referrer_clicks
        ],
        "clicks_over_time": clicks_over_time,
    }, 200


@url_routes.route("/<short_url>", methods = ["GET"])
def redirect_url(short_url):
    cached_url = redis_client.get(short_url)  

    if cached_url:      
        url = URL.query.filter_by(short_url=short_url).first() 

        if not url: 
            return {"error": "Short URL not found"}, 404 

        rq_queue.enqueue(   
            process_click_event,
            url.id,
            datetime.now(timezone.utc),
            request.remote_addr,
            request.headers.get("User-Agent"),
            request.referrer
        )    

        return redirect(cached_url)           

    try:
        url = URL.query.filter_by(short_url=short_url).first()

    except SQLAlchemyError:
        db.session.rollback()
        return {"error": "Database error"}, 500

    if not url:
        return {"error": "Short URL not found"}, 404

    redis_client.set(short_url, url.original_url)  

    rq_queue.enqueue(   
        process_click_event,
        url.id,
        datetime.now(timezone.utc),
        request.remote_addr,
        request.headers.get("User-Agent"),
        request.referrer
    )  
     
    return redirect(url.original_url)
          
     
def encode_base62(number):
    characters = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    result = ""

    while number > 0:
        number, remainder = divmod(number, 62)
        result = characters[remainder] + result

    return result


#1. Hot short codes
