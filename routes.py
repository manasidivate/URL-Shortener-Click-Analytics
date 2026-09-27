from flask import Blueprint, request, redirect, render_template
from models import URL
from extensions import db
from sqlalchemy import text
from urllib.parse import urlparse
from sqlalchemy.exc import SQLAlchemyError 
from extensions import redis_client
from datetime import datetime, timezone 
from tasks import process_click_event 
from extensions import rq_queue 


url_routes = Blueprint("url_routes", __name__)


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

    try: 
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

    except SQLAlchemyError: 
        db.session.rollback() 
        return {"error": "Database error"}, 500 

    return {"short_url": short_url}, 201

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