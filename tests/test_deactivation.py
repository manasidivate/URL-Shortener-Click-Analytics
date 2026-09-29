import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import Flask

from extensions import db
from models import ClickEvent, URL
from routes import url_routes


class DeactivationRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(
            __name__,
            template_folder=os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "templates",
            ),
        )

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
        is_active=True,
        expires_at=None,
    ):
        url = URL(
            original_url=original_url,
            short_url=short_url,
            is_active=is_active,
            expires_at=expires_at,
        )

        db.session.add(url)
        db.session.commit()

        return url

    def test_active_url_redirects_normally(self):
        self.create_url("active")

        with patch(
            "routes.redis_client.get",
            return_value=None,
        ), patch(
            "routes.redis_client.set"
        ) as cache_set, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue:

            response = self.client.get(
                "/active",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "https://example.com",
        )

        cache_set.assert_called_once()
        enqueue.assert_called_once()

    def test_patch_deactivates_url(self):
        self.create_url("deactivate")

        with patch(
            "routes.redis_client.delete"
        ) as cache_delete:

            response = self.client.patch(
                "/deactivate",
                json={"is_active": False},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "short_url": "deactivate",
                "is_active": False,
            },
        )

        url = URL.query.filter_by(
            short_url="deactivate"
        ).first()

        self.assertIsNotNone(url)
        self.assertFalse(url.is_active)

        cache_delete.assert_called_once_with("deactivate")

    def test_deactivated_url_returns_403(self):
        self.create_url(
            "inactive",
            is_active=False,
        )

        with patch(
            "routes.redis_client.get",
            return_value=None,
        ), patch(
            "routes.redis_client.delete"
        ) as cache_delete, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue:

            response = self.client.get(
                "/inactive",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 403)

        response_text = response.get_data(as_text=True)

        self.assertIn(
            "Link Deactivated",
            response_text,
        )
        self.assertIn(
            "This short link has been deactivated",
            response_text,
        )

        cache_delete.assert_called_once_with("inactive")
        enqueue.assert_not_called()

    def test_deactivated_url_does_not_redirect(self):
        self.create_url(
            "no-redirect",
            original_url="https://example.com/private",
            is_active=False,
        )

        with patch(
            "routes.redis_client.get",
            return_value=None,
        ), patch(
            "routes.rq_queue.enqueue"
        ) as enqueue:

            response = self.client.get(
                "/no-redirect",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(
            response.status_code,
            302,
        )
        enqueue.assert_not_called()

    def test_deactivated_url_does_not_enqueue_click_event(self):
        self.create_url(
            "no-click",
            is_active=False,
        )

        with patch(
            "routes.redis_client.get",
            return_value=None,
        ), patch(
            "routes.redis_client.delete"
        ), patch(
            "routes.rq_queue.enqueue"
        ) as enqueue:

            response = self.client.get(
                "/no-click",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 403)
        enqueue.assert_not_called()

        self.assertEqual(
            ClickEvent.query.count(),
            0,
        )

    def test_deactivation_invalidates_redis_cache(self):
        self.create_url("cached")

        with patch(
            "routes.redis_client.delete"
        ) as cache_delete:

            response = self.client.patch(
                "/cached",
                json={"is_active": False},
            )

        self.assertEqual(response.status_code, 200)
        cache_delete.assert_called_once_with("cached")

    def test_cached_inactive_url_returns_403(self):
        inactive_cache = (
            '{"url_id": 1, '
            '"original_url": "https://example.com", '
            '"expires_at": null, '
            '"is_active": false}'
        )

        with patch(
            "routes.redis_client.get",
            return_value=inactive_cache,
        ), patch(
            "routes.redis_client.delete"
        ) as cache_delete, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue:

            response = self.client.get(
                "/cached-inactive",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 403)

        response_text = response.get_data(as_text=True)

        self.assertIn(
            "Link Deactivated",
            response_text,
        )
        self.assertIn(
            "This short link has been deactivated",
            response_text,
        )

        cache_delete.assert_called_once_with("cached-inactive")
        enqueue.assert_not_called()

    def test_patch_requires_is_active_field(self):
        self.create_url("missing-field")

        response = self.client.patch(
            "/missing-field",
            json={},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {
                "error": "is_active is required"
            },
        )

        url = URL.query.filter_by(
            short_url="missing-field"
        ).first()

        self.assertTrue(url.is_active)

    def test_patch_requires_boolean_is_active(self):
        self.create_url("invalid-type")

        invalid_values = [
            "false",
            0,
            1,
            None,
            [],
            {},
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                response = self.client.patch(
                    "/invalid-type",
                    json={"is_active": value},
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.get_json(),
                    {
                        "error": "is_active must be a boolean"
                    },
                )

        url = URL.query.filter_by(
            short_url="invalid-type"
        ).first()

        self.assertTrue(url.is_active)

    def test_patch_unknown_short_url_returns_404(self):
        response = self.client.patch(
            "/missing",
            json={"is_active": False},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json(),
            {
                "error": "Short URL not found"
            },
        )

    def test_patch_reactivates_deactivated_url(self):
        self.create_url(
            "reactivate",
            is_active=False,
        )

        with patch(
            "routes.redis_client.delete"
        ) as cache_delete:

            response = self.client.patch(
                "/reactivate",
                json={"is_active": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "short_url": "reactivate",
                "is_active": True,
            },
        )

        url = URL.query.filter_by(
            short_url="reactivate"
        ).first()

        self.assertIsNotNone(url)
        self.assertTrue(url.is_active)

        cache_delete.assert_called_once_with("reactivate")

    def test_reactivated_url_redirects_again(self):
        self.create_url(
            "reactivated",
            is_active=False,
        )

        with patch(
            "routes.redis_client.delete"
        ):
            patch_response = self.client.patch(
                "/reactivated",
                json={"is_active": True},
            )

        self.assertEqual(patch_response.status_code, 200)

        with patch(
            "routes.redis_client.get",
            return_value=None,
        ), patch(
            "routes.redis_client.set"
        ) as cache_set, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue:

            response = self.client.get(
                "/reactivated",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "https://example.com",
        )

        cache_set.assert_called_once()
        enqueue.assert_called_once()

    def test_deactivated_expired_url_returns_403(self):
        expires_at = self.now - timedelta(seconds=1)

        self.create_url(
            "inactive-expired",
            is_active=False,
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
                "/inactive-expired",
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 403)

        response_text = response.get_data(as_text=True)

        self.assertIn(
            "Link Deactivated",
            response_text,
        )
        self.assertIn(
            "This short link has been deactivated",
            response_text,
        )

        cache_delete.assert_called_once_with("inactive-expired")
        enqueue.assert_not_called()


if __name__ == "__main__":
    unittest.main()