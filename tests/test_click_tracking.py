import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from flask import Flask

from extensions import db
from models import ClickEvent, URL
from routes import url_routes
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
        cls.app.register_blueprint(url_routes)

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
        self.client = self.app.test_client()

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

    def test_redirect_task_persistence_and_referrer_analytics(self):
        url = URL(
            original_url="https://example.com",
            short_url="end-to-end",
        )
        db.session.add(url)
        db.session.commit()

        ip_address = "203.0.113.10"
        user_agent = "Integration Test Agent"
        referrer = "https://source.example/article"

        with patch("routes.redis_client.get", return_value=None), patch(
            "routes.redis_client.set"
        ), patch("routes.rq_queue.enqueue") as enqueue:
            redirect_response = self.client.get(
                "/end-to-end",
                follow_redirects=False,
                headers={
                    "User-Agent": user_agent,
                    "Referer": referrer,
                },
                environ_base={"REMOTE_ADDR": ip_address},
            )

        self.assertEqual(redirect_response.status_code, 302)
        enqueue.assert_called_once()

        queued_task, *task_args = enqueue.call_args.args

        self.assertIs(queued_task, process_click_event)
        self.assertEqual(task_args[0], url.id)
        self.assertEqual(task_args[2:], [ip_address, user_agent, referrer])

        with patch("tasks.get_country", return_value=None), patch(
            "tasks.get_user_agent_info",
            return_value=("Firefox", "Desktop"),
        ), patch(
            "tasks.generate_visitor_hash",
            return_value="integration-visitor-hash",
        ):
            queued_task(*task_args)

        event = ClickEvent.query.one()

        self.assertEqual(event.url_id, url.id)
        self.assertEqual(event.referrer, referrer)

        analytics_response = self.client.get("/end-to-end/analytics")

        self.assertEqual(analytics_response.status_code, 200)
        self.assertEqual(
            analytics_response.get_json()["top_referrers"],
            [{"referrer": referrer, "clicks": 1}],
        )

    def test_redirect_without_referer_records_no_referrer(self):
        url = URL(
            original_url="https://example.com",
            short_url="direct-visit",
        )
        db.session.add(url)
        db.session.commit()

        with patch("routes.redis_client.get", return_value=None), patch(
            "routes.redis_client.set"
        ), patch("routes.rq_queue.enqueue") as enqueue:
            redirect_response = self.client.get(
                "/direct-visit",
                follow_redirects=False,
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )

        self.assertEqual(redirect_response.status_code, 302)
        queued_task, *task_args = enqueue.call_args.args
        self.assertIs(queued_task, process_click_event)
        self.assertIsNone(task_args[4])

        with patch("tasks.get_country", return_value="India"), patch(
            "tasks.get_user_agent_info",
            return_value=("Firefox", "Desktop"),
        ), patch(
            "tasks.generate_visitor_hash",
            return_value="direct-visit-hash",
        ):
            queued_task(*task_args)

        event = ClickEvent.query.one()
        self.assertIsNone(event.referrer)

        analytics_response = self.client.get("/direct-visit/analytics")
        self.assertEqual(analytics_response.status_code, 200)
        self.assertEqual(
            analytics_response.get_json()["top_referrers"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
