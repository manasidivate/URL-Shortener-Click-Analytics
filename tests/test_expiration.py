import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import Flask

from extensions import db
from models import ClickEvent, URL
from routes import url_routes


class ExpirationRouteTests(unittest.TestCase):
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

        self.now = datetime(
            2026,
            9,
            28,
            12,
            0,
            tzinfo=timezone.utc,
        )

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def create_url(
        self,
        short_url,
        original_url="https://example.com",
        expires_at=None,
    ):
        url = URL(
            original_url=original_url,
            short_url=short_url,
            expires_at=expires_at,
        )

        db.session.add(url)
        db.session.commit()

        return url

    def test_url_without_expiry_redirects_normally(self):
        self.create_url("no-expiry")

        with patch(
            "routes.redis_client.get",
            return_value=None,
        ), patch(
            "routes.redis_client.set"
        ) as cache_set, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue:

            response = self.client.get(
                "/no-expiry",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "https://example.com",
        )
        cache_set.assert_called_once()
        enqueue.assert_called_once()

    def test_future_expiry_redirects_normally(self):
        expires_at = self.now + timedelta(hours=1)

        self.create_url(
            "future",
            expires_at=expires_at,
        )

        with patch(
            "routes.redis_client.get",
            return_value=None,
        ), patch(
            "routes.redis_client.set"
        ) as cache_set, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue, patch(
            "routes.datetime",
            wraps=datetime,
        ) as mock_datetime:

            mock_datetime.now.return_value = self.now

            response = self.client.get(
                "/future",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "https://example.com",
        )
        cache_set.assert_called_once()
        enqueue.assert_called_once()

    def test_expired_url_returns_410(self):
        expires_at = self.now - timedelta(seconds=1)

        self.create_url(
            "expired",
            expires_at=expires_at,
        )

        with patch(
            "routes.redis_client.get",
            return_value=None,
        ), patch(
            "routes.redis_client.delete"
        ) as cache_delete, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue, patch(
            "routes.datetime",
            wraps=datetime,
        ) as mock_datetime:

            mock_datetime.now.return_value = self.now

            response = self.client.get(
                "/expired",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.get_json(),
            {"error": "This short URL has expired."},
        )
        cache_delete.assert_called_once_with("expired")
        enqueue.assert_not_called()

    def test_expiry_boundary_returns_410(self):
        expires_at = self.now

        self.create_url(
            "boundary",
            expires_at=expires_at,
        )

        with patch(
            "routes.redis_client.get",
            return_value=None,
        ), patch(
            "routes.redis_client.delete"
        ) as cache_delete, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue, patch(
            "routes.datetime",
            wraps=datetime,
        ) as mock_datetime:

            mock_datetime.now.return_value = self.now

            response = self.client.get(
                "/boundary",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 410)
        cache_delete.assert_called_once_with("boundary")
        enqueue.assert_not_called()

    def test_invalid_expiry_returns_400(self):
        response = self.client.post(
            "/shorten",
            json={
                "original_url": "https://example.com",
                "expires_at": "not-a-valid-datetime",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "expires_at must be a valid datetime"},
        )
        self.assertEqual(URL.query.count(), 0)

    def test_naive_expiry_returns_400(self):
        response = self.client.post(
            "/shorten",
            json={
                "original_url": "https://example.com",
                "expires_at": "2026-09-28T13:00:00",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "expires_at must include timezone information"},
        )
        self.assertEqual(URL.query.count(), 0)

    def test_custom_alias_with_expiry(self):
        expires_at = self.now + timedelta(hours=1)

        response = self.client.post(
            "/shorten",
            json={
                "original_url": "https://example.com",
                "alias": "my-project",
                "expires_at": expires_at.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json(),
            {"short_url": "my-project"},
        )

        url = URL.query.filter_by(
            short_url="my-project"
        ).first()

        self.assertIsNotNone(url)

        self.assertEqual(
            url.expires_at.replace(tzinfo=timezone.utc),
            expires_at,
        )

    def test_base62_url_with_expiry(self):
        next_id = 123456

        from types import SimpleNamespace

        sequence_result = SimpleNamespace(
            scalar=lambda: next_id
        )

        expires_at = self.now + timedelta(hours=1)

        with patch(
            "routes.db.session.execute",
            return_value=sequence_result,
        ):
            response = self.client.post(
                "/shorten",
                json={
                    "original_url": "https://example.com",
                    "expires_at": expires_at.isoformat(),
                },
            )

        self.assertEqual(response.status_code, 201)

        short_url = response.get_json()["short_url"]

        url = URL.query.filter_by(
            short_url=short_url
        ).first()

        self.assertIsNotNone(url)

        self.assertEqual(
            url.expires_at.replace(tzinfo=timezone.utc),
            expires_at,
        )

    def test_expired_url_does_not_enqueue_click_event(self):
        expires_at = self.now - timedelta(seconds=1)

        self.create_url(
            "no-click",
            expires_at=expires_at,
        )

        with patch(
            "routes.redis_client.get",
            return_value=None,
        ), patch(
            "routes.redis_client.delete"
        ), patch(
            "routes.rq_queue.enqueue"
        ) as enqueue, patch(
            "routes.datetime",
            wraps=datetime,
        ) as mock_datetime:

            mock_datetime.now.return_value = self.now

            response = self.client.get(
                "/no-click",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 410)
        enqueue.assert_not_called()

    def test_expired_cached_url_is_invalidated_and_returns_410(self):
        expired_cache = (
            '{"url_id": 1, '
            '"original_url": "https://example.com", '
            '"expires_at": "2026-09-28T11:59:59+00:00"}'
        )

        with patch(
            "routes.redis_client.get",
            return_value=expired_cache,
        ), patch(
            "routes.redis_client.delete"
        ) as cache_delete, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue, patch(
            "routes.datetime",
            wraps=datetime,
        ) as mock_datetime:

            mock_datetime.now.return_value = self.now

            response = self.client.get(
                "/cached-expired",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.get_json(),
            {"error": "This short URL has expired."},
        )
        cache_delete.assert_called_once_with("cached-expired")
        enqueue.assert_not_called()

    def test_active_cached_url_redirects_without_database_lookup(self):
        cached_url = (
            '{"url_id": 1, '
            '"original_url": "https://example.com/cached", '
            '"expires_at": "2026-09-28T13:00:00+00:00"}'
        )

        with patch(
            "routes.redis_client.get",
            return_value=cached_url,
        ), patch(
            "routes.rq_queue.enqueue"
        ) as enqueue, patch(
            "routes.URL.query"
        ) as url_query, patch(
            "routes.datetime",
            wraps=datetime,
        ) as mock_datetime:

            mock_datetime.now.return_value = self.now

            response = self.client.get(
                "/cached-active",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "https://example.com/cached",
        )
        enqueue.assert_called_once()
        url_query.filter_by.assert_not_called()


if __name__ == "__main__":
    unittest.main()