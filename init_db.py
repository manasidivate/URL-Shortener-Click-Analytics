from app import create_app
from extensions import db
from sqlalchemy import text
import models


app = create_app()

with app.app_context():
    db.create_all()

    db.session.execute(
        text(
            """
            ALTER TABLE url
            ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE
            """
        )
    )

    db.session.commit()