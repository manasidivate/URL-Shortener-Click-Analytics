from flask import Flask
import os
from dotenv import load_dotenv 
from extensions import db 
from routes import url_routes

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

    db.init_app(app)

    app.register_blueprint(url_routes)

    return app




if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
