import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from extensions import db
from models import ClickEvent, URL
from routes import encode_base62, url_routes


class ShorteningRouteTests(unittest.TestCase):
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

    def create_url(self, short_url, original_url="https://example.com"):
        url = URL(original_url=original_url, short_url=short_url)
        db.session.add(url)
        db.session.commit()
        return url

    def test_no_alias_uses_existing_base62_generation(self):
        next_id = 123456
        sequence_result = SimpleNamespace(scalar=lambda: next_id)

        with patch("routes.db.session.execute", return_value=sequence_result):
            response = self.client.post(
                "/shorten",
                json={"original_url": "https://example.com"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), {"short_url": encode_base62(next_id)})
        self.assertIsNotNone(URL.query.filter_by(short_url=encode_base62(next_id)).first())

    def test_valid_alias_is_normalized_and_stored(self):
        response = self.client.post(
            "/shorten",
            json={"original_url": "https://example.com", "alias": "My_Project-2026"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), {"short_url": "my_project-2026"})
        self.assertIsNotNone(URL.query.filter_by(short_url="my_project-2026").first())

    def test_invalid_aliases_return_bad_request_without_creating_url(self):
        invalid_aliases = ["my project", "my/project", "my.project", "my@project", "ab", "a" * 51, None]

        for alias in invalid_aliases:
            with self.subTest(alias=alias):
                response = self.client.post(
                    "/shorten",
                    json={"original_url": "https://example.com", "alias": alias},
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(URL.query.count(), 0)

    def test_existing_custom_alias_returns_conflict_without_creating_url(self):
        self.create_url("my-project")

        response = self.client.post(
            "/shorten",
            json={"original_url": "https://other.example", "alias": "MY-PROJECT"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json(),
            {"error": "Alias is not available. Please choose another one."},
        )
        self.assertEqual(URL.query.count(), 1)

    def test_alias_collision_with_generated_code_returns_conflict(self):
        self.create_url("abc123")

        response = self.client.post(
            "/shorten",
            json={"original_url": "https://other.example", "alias": "abc123"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(URL.query.count(), 1)

    def test_reserved_aliases_are_case_insensitive(self):
        for alias in ("shorten", "analytics", "static", "SHORTEN", "ANALYTICS", "STATIC"):
            with self.subTest(alias=alias):
                response = self.client.post(
                    "/shorten",
                    json={"original_url": "https://example.com", "alias": alias},
                )

                self.assertEqual(response.status_code, 409)
                self.assertEqual(
                    response.get_json(),
                    {"error": "Alias is not available. Please choose another one."},
                )
                self.assertEqual(URL.query.count(), 0)

    def test_generated_short_url_still_redirects(self):
        self.create_url("abc123", "https://example.com/generated")

        with patch("routes.redis_client.get", return_value=None), patch(
            "routes.redis_client.set"
        ) as cache_set, patch("routes.rq_queue.enqueue") as enqueue:
            response = self.client.get("/abc123", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "https://example.com/generated")
        cache_set.assert_called_once_with("abc123", "https://example.com/generated")
        enqueue.assert_called_once()

    def test_custom_alias_redirects_and_uses_existing_analytics(self):
        self.create_url("my-project", "https://example.com/alias")

        with patch("routes.redis_client.get", return_value=None), patch(
            "routes.redis_client.set"
        ) as cache_set, patch("routes.rq_queue.enqueue") as enqueue:
            redirect_response = self.client.get("/my-project", follow_redirects=False)

        analytics_response = self.client.get("/my-project/analytics")

        self.assertEqual(redirect_response.status_code, 302)
        self.assertEqual(redirect_response.headers["Location"], "https://example.com/alias")
        cache_set.assert_called_once_with("my-project", "https://example.com/alias")
        enqueue.assert_called_once()
        self.assertEqual(analytics_response.status_code, 200)
        self.assertEqual(analytics_response.get_json()["total_clicks"], 0)


if __name__ == "__main__":
    unittest.main()
