from extensions import db


class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_url = db.Column(db.String(2048), nullable=False)
    short_url = db.Column(db.String(50), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)

    click_events = db.relationship(
        "ClickEvent",
        back_populates="url"
    )


class ClickEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    url_id = db.Column(
        db.Integer,
        db.ForeignKey("url.id"),
        nullable=False
    )

    timestamp = db.Column(
        db.DateTime(timezone=True),
        nullable=False
    )

    country = db.Column(
        db.String(100),
        nullable=True
    )

    browser = db.Column(
        db.String(100),
        nullable=True
    )

    device_type = db.Column(
        db.String(50),
        nullable=True
    )

    referrer = db.Column(
        db.Text,
        nullable=True
    )

    visitor_hash = db.Column(
        db.String(64),
        nullable=True
    )

    url = db.relationship(
        "URL",
        back_populates="click_events"
    )