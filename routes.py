from io import BytesIO

import qrcode
from flask import (
    Blueprint,
    current_app,
    request,
    redirect,
    render_template,
    send_file,
    url_for,
)
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
import json


url_routes = Blueprint("url_routes", __name__)


RESERVED_ALIASES = {"shorten", "analytics", "static"}
ALIAS_PATTERN = re.compile(r"[a-z0-9_-]{3,50}")


@url_routes.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@url_routes.route("/shorten", methods=["POST"])
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
            return {
                "error": "Alias must be 3-50 letters, numbers, hyphens, or underscores only"
            }, 400

        alias = alias.lower()

        if not ALIAS_PATTERN.fullmatch(alias):
            return {
                "error": "Alias must be 3-50 letters, numbers, hyphens, or underscores"
            }, 400

        if alias in RESERVED_ALIASES:
            return {
                "error": "Alias is not available. Please choose another one."
            }, 409

    # FR6: Optional expiry date
    expires_at = data.get("expires_at")

    if expires_at is not None:
        if not isinstance(expires_at, str):
            return {"error": "expires_at must be a valid datetime"}, 400

        try:
            parsed_expires_at = datetime.fromisoformat(
                expires_at.replace("Z", "+00:00")
            )
        except ValueError:
            return {"error": "expires_at must be a valid datetime"}, 400

        if parsed_expires_at.tzinfo is None:
            return {
                "error": "expires_at must include timezone information"
            }, 400

        expires_at = parsed_expires_at.astimezone(timezone.utc)

    try:
        if alias_provided:
            if URL.query.filter_by(short_url=alias).first():
                return {
                    "error": "Alias is not available. Please choose another one."
                }, 409

            short_url = alias

            url = URL(
                original_url=original_url,
                short_url=short_url,
                expires_at=expires_at
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
                short_url=short_url,
                expires_at=expires_at
            )

        db.session.add(url)
        db.session.commit()

    except IntegrityError:
        db.session.rollback()

        if alias_provided:
            return {
                "error": "Alias is not available. Please choose another one."
            }, 409

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

        range_start = datetime.combine(
            start_date,
            time.min,
            tzinfo=timezone.utc
        )

        range_end = range_start + timedelta(days=7)

        if db.engine.dialect.name == "postgresql":
            click_date = func.date(
                ClickEvent.timestamp.op("AT TIME ZONE")("UTC")
            )
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
        str(click_date): clicks
        for click_date, clicks in daily_clicks
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


@url_routes.route("/<short_url>/qr", methods=["GET"])
def get_qr_code(short_url):
    try:
        url = URL.query.filter_by(short_url=short_url).first()

    except SQLAlchemyError:
        db.session.rollback()
        return {"error": "Database error"}, 500

    if not url:
        return {"error": "Short URL not found"}, 404

    if not url.is_active:
        return render_template("deactivated.html"), 403

    if url.expires_at is not None:
        current_time = datetime.now(timezone.utc)
        expiry_time = url.expires_at

        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)

        if current_time >= expiry_time:
            return render_template("expired.html"), 410

    short_url_payload = url_for(
        "url_routes.redirect_url",
        short_url=short_url,
        _external=True,
    )

    image_buffer = BytesIO()
    qrcode.make(short_url_payload).save(image_buffer, format="PNG")
    image_buffer.seek(0)

    return send_file(image_buffer, mimetype="image/png")


# FR7: Link activation/deactivation
@url_routes.route("/<short_url>", methods=["PATCH"])
def update_link_status(short_url):
    data = request.get_json(silent=True)

    if data is None:
        return {"error": "Request body must be valid JSON"}, 400

    if "is_active" not in data:
        return {"error": "is_active is required"}, 400

    if not isinstance(data["is_active"], bool):
        return {"error": "is_active must be a boolean"}, 400

    try:
        url = URL.query.filter_by(short_url=short_url).first()

        if not url:
            return {"error": "Short URL not found"}, 404

        url.is_active = data["is_active"]

        db.session.commit()

        # FR7: Invalidate cached redirect after state change.
        redis_client.delete(short_url)

    except SQLAlchemyError:
        db.session.rollback()
        return {"error": "Database error"}, 500

    return {
        "short_url": short_url,
        "is_active": url.is_active
    }, 200


@url_routes.route("/<short_url>", methods=["GET"])
def redirect_url(short_url):
    cached_url = redis_client.get(short_url)

    if cached_url:
        try:
            cached_data = json.loads(cached_url)

        except (json.JSONDecodeError, TypeError):
            # Legacy cache entry from before FR6.
            # Treat it as a cache miss so the new cache format can be created.
            redis_client.delete(short_url)

        else:
            cached_url_id = cached_data.get("url_id")
            cached_original_url = cached_data.get("original_url")
            cached_expires_at = cached_data.get("expires_at")
            cached_is_active = cached_data.get("is_active")

            if not cached_url_id or not cached_original_url:
                redis_client.delete(short_url)

            else:
                # FR7: Deactivated links must never redirect from cache.
                if cached_is_active is False:
                    redis_client.delete(short_url)

                    return render_template(
                        "deactivated.html"
                    ), 403

                if cached_expires_at:
                    cached_expiry = datetime.fromisoformat(
                        cached_expires_at
                    )

                    if datetime.now(timezone.utc) >= cached_expiry:
                        redis_client.delete(short_url)

                        return render_template(
                            "expired.html"
                        ), 410

                current_app.logger.info(
                    "Click request diagnostics: remote_addr=%r access_route=%r "
                    "x_forwarded_for=%r referrer=%r",
                    request.remote_addr,
                    list(request.access_route),
                    request.headers.get("X-Forwarded-For"),
                    request.referrer,
                )
                rq_queue.enqueue(
                    process_click_event,
                    cached_url_id,
                    datetime.now(timezone.utc),
                    request.remote_addr,
                    request.headers.get("User-Agent"),
                    request.referrer
                )

                return redirect(cached_original_url)

    try:
        url = URL.query.filter_by(short_url=short_url).first()

    except SQLAlchemyError:
        db.session.rollback()
        return {"error": "Database error"}, 500

    if not url:
        return {"error": "Short URL not found"}, 404

    # FR7: Check activation state before allowing redirect.
    if not url.is_active:
        redis_client.delete(short_url)

        return render_template(
            "deactivated.html"
        ), 403

    # FR6: Check expiry before creating/using redirect cache.
    if url.expires_at is not None:
        current_time = datetime.now(timezone.utc)

        expiry_time = url.expires_at

        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)

        if current_time >= expiry_time:
            redis_client.delete(short_url)

            return render_template(
                "expired.html"
            ), 410

    cached_data = {
        "url_id": url.id,
        "original_url": url.original_url,
        "expires_at": (
            url.expires_at.astimezone(timezone.utc).isoformat()
            if url.expires_at is not None
            else None
        ),
        "is_active": url.is_active
    }

    redis_client.set(
        short_url,
        json.dumps(cached_data)
    )

    current_app.logger.info(
        "Click request diagnostics: remote_addr=%r access_route=%r "
        "x_forwarded_for=%r referrer=%r",
        request.remote_addr,
        list(request.access_route),
        request.headers.get("X-Forwarded-For"),
        request.referrer,
    )
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


# 1. Hot short codes
