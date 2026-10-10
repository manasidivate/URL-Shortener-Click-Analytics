from flask import Flask
import os
from dotenv import load_dotenv 
from extensions import db 
from routes import url_routes
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv() 


def normalize_database_url(database_url):
    """Use psycopg 3 for Render's plain PostgreSQL connection URLs."""
    if database_url and database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://"):]

    return database_url


def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = normalize_database_url(
        os.getenv("DATABASE_URL")
    )

    trusted_proxy_count = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))
    if trusted_proxy_count < 0:
        raise ValueError("TRUSTED_PROXY_COUNT must be zero or greater")
    if trusted_proxy_count:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_proxy_count)

    db.init_app(app)

    app.register_blueprint(url_routes)

    return app




if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
