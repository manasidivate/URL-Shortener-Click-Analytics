from flask import Flask
import os
from dotenv import load_dotenv 
from extensions import db 
from routes import url_routes

load_dotenv() 

def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")

    db.init_app(app)

    app.register_blueprint(url_routes)

    return app




if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
