import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from flask import Flask

from extensions import db
from models import ClickEvent, URL
from tasks import process_click_event


class ClickTrackingTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(cls.app)

        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.drop_all()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.session.query(ClickEvent).delete()
        db.session.query(URL).delete()
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def test_process_click_event_persists_metadata(self):
        url = URL(
            original_url="https://example.com",
            short_url="tracked",
        )
        db.session.add(url)
        db.session.commit()

        timestamp = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
        ip_address = "203.0.113.10"
        user_agent = "Metadata Test Agent"
        referrer = "https://source.example/article"

        with patch("tasks.get_country", return_value="India") as get_country, patch(
            "tasks.get_user_agent_info",
            return_value=("Firefox", "Desktop"),
        ) as get_user_agent_info, patch(
            "tasks.generate_visitor_hash",
            return_value="test-visitor-hash",
        ) as generate_visitor_hash:
            process_click_event(
                url.id,
                timestamp,
                ip_address,
                user_agent,
                referrer,
            )

        get_country.assert_called_once_with(ip_address)
        get_user_agent_info.assert_called_once_with(user_agent)
        generate_visitor_hash.assert_called_once_with(ip_address)

        event = ClickEvent.query.one()

        self.assertEqual(event.url_id, url.id)
        self.assertEqual(event.timestamp.replace(tzinfo=timezone.utc), timestamp)
        self.assertEqual(event.country, "India")
        self.assertEqual(event.browser, "Firefox")
        self.assertEqual(event.device_type, "Desktop")
        self.assertEqual(event.referrer, referrer)
        self.assertEqual(event.visitor_hash, "test-visitor-hash")


if __name__ == "__main__":
    unittest.main()
