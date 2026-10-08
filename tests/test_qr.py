import os
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch
from urllib.parse import urlsplit

import zxingcpp
from flask import Flask
from PIL import Image

from extensions import db
from models import ClickEvent, URL
from routes import url_routes


class QrCodeRouteTests(unittest.TestCase):
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
        self.now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)

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

    def decode_qr_payload(self, response):
        image = Image.open(BytesIO(response.data))
        barcodes = zxingcpp.read_barcodes(image)

        self.assertEqual(len(barcodes), 1)
        return barcodes[0].text

    def test_active_url_returns_png_with_decodable_short_url_payload(self):
        self.create_url("abc123")

        response = self.client.get("/abc123/qr")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "image/png")
        self.assertTrue(response.data)
        self.assertEqual(
            self.decode_qr_payload(response),
            "http://localhost/abc123",
        )

    def test_qr_payload_uses_request_host_and_scheme(self):
        self.create_url("host-aware")

        response = self.client.get(
            "/host-aware/qr",
            base_url="https://short.example:8443",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.decode_qr_payload(response),
            "https://short.example:8443/host-aware",
        )

    def test_unknown_short_url_returns_not_found(self):
        response = self.client.get("/missing/qr")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Short URL not found"})

    def test_deactivated_short_url_returns_forbidden_without_analytics(self):
        self.create_url("inactive", is_active=False)

        with patch("routes.rq_queue.enqueue") as enqueue:
            response = self.client.get("/inactive/qr")

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"Link Deactivated", response.data)
        enqueue.assert_not_called()
        self.assertEqual(ClickEvent.query.count(), 0)

    def test_expired_short_url_returns_gone_without_analytics(self):
        self.create_url(
            "expired",
            expires_at=self.now - timedelta(seconds=1),
        )

        with patch("routes.rq_queue.enqueue") as enqueue, patch(
            "routes.datetime",
            wraps=datetime,
        ) as mock_datetime:
            mock_datetime.now.return_value = self.now
            response = self.client.get("/expired/qr")

        self.assertEqual(response.status_code, 410)
        self.assertIn(b"Link expired", response.data)
        enqueue.assert_not_called()
        self.assertEqual(ClickEvent.query.count(), 0)

    def test_qr_request_does_not_use_redirect_cache_or_enqueue_click_event(self):
        self.create_url("no-side-effects")

        with patch("routes.redis_client.get") as cache_get, patch(
            "routes.redis_client.set"
        ) as cache_set, patch("routes.redis_client.delete") as cache_delete, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue:
            response = self.client.get("/no-side-effects/qr")

        self.assertEqual(response.status_code, 200)
        cache_get.assert_not_called()
        cache_set.assert_not_called()
        cache_delete.assert_not_called()
        enqueue.assert_not_called()
        self.assertEqual(ClickEvent.query.count(), 0)

    def test_decoded_payload_uses_existing_redirect_flow(self):
        self.create_url("scan", "https://example.com/scanned")

        qr_response = self.client.get(
            "/scan/qr",
            base_url="https://short.example",
        )
        self.assertEqual(qr_response.status_code, 200)
        decoded_payload = self.decode_qr_payload(qr_response)
        decoded_path = urlsplit(decoded_payload).path

        with patch("routes.redis_client.get", return_value=None), patch(
            "routes.redis_client.set"
        ) as cache_set, patch("routes.rq_queue.enqueue") as enqueue:
            redirect_response = self.client.get(
                decoded_path,
                follow_redirects=False,
            )

        self.assertEqual(redirect_response.status_code, 302)
        self.assertEqual(
            redirect_response.headers["Location"],
            "https://example.com/scanned",
        )
        cache_set.assert_called_once()
        enqueue.assert_called_once()


if __name__ == "__main__":
    unittest.main()
