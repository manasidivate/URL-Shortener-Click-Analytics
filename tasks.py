from models import ClickEvent
from extensions import db
from user_agents import parse
import geoip2.database
import hashlib #
import os      #
from dotenv import load_dotenv #

load_dotenv() #



def process_click_event(
    url_id,
    timestamp,
    ip_address,
    user_agent,
    referrer
):
    country = get_country(ip_address)

    browser, device_type = get_user_agent_info(user_agent)

    visitor_hash = generate_visitor_hash(ip_address) #

    click_event = ClickEvent(
        url_id=url_id,
        timestamp=timestamp,
        country=country,
        browser=browser,
        device_type=device_type,
        referrer=referrer,
        visitor_hash=visitor_hash #
    )

    try:
        db.session.add(click_event)
        db.session.commit()

    except Exception:
        db.session.rollback()
        raise


def get_user_agent_info(user_agent):
    user_agent_data = parse(user_agent)

    browser = user_agent_data.browser.family

    if user_agent_data.is_mobile:
        device_type = "Mobile"
    elif user_agent_data.is_tablet:
        device_type = "Tablet"
    elif user_agent_data.is_pc:
        device_type = "Desktop"
    else:
        device_type = "Other"

    return browser, device_type
#Testing(in venv terminal): python -c "from tasks import get_user_agent_info; print(get_user_agent_info('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'))"


def get_country(ip_address):
    reader = geoip2.database.Reader("data/GeoLite2-Country.mmdb")

    try:
        response = reader.country(ip_address)
        return response.country.name
    except geoip2.errors.AddressNotFoundError:
        return None
    finally:
        reader.close()
#Testing(in venv terminal): python -c "from tasks import get_country; print(get_country('8.8.8.8'))"


#helper function for 3.Generate visitor_hash
def generate_visitor_hash(ip_address): #
    salt = os.getenv("VISITOR_HASH_SALT")

    if not salt:
        raise ValueError("VISITOR_HASH_SALT is not configured")

    value = f"{salt}:{ip_address}"

    return hashlib.sha256(value.encode()).hexdigest() #
#Testing(in venv terminal): python -c "from tasks import generate_visitor_hash; print(generate_visitor_hash('8.8.8.8'))"
#Output -> 64-character SHA-256 hash.






