import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import Flask

from extensions import db
from models import ClickEvent, URL
from routes import url_routes


class AnalyticsRouteTests(unittest.TestCase):
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
        self.now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def add_url(self, short_url):
        url = URL(
            original_url="https://example.com",
            short_url=short_url,
        )
        db.session.add(url)
        db.session.commit()
        return url

    def get_analytics(self, short_url):
        with patch("routes.datetime", wraps=datetime) as mock_datetime:
            mock_datetime.now.return_value = self.now
            return self.client.get(f"/{short_url}/analytics")

    def clicks_over_time(self, clicks_by_date=None):
        clicks_by_date = clicks_by_date or {}
        start_date = self.now.date() - timedelta(days=6)
        return [
            {
                "date": (start_date + timedelta(days=day_offset)).isoformat(),
                "clicks": clicks_by_date.get(
                    (start_date + timedelta(days=day_offset)).isoformat(),
                    0,
                ),
            }
            for day_offset in range(7)
        ]

    def test_existing_short_url_with_no_clicks_returns_zero(self):
        self.add_url("empty")

        with patch("routes.redis_client.get") as cache_get, patch(
            "routes.rq_queue.enqueue"
        ) as enqueue:
            response = self.get_analytics("empty")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "total_clicks": 0,
                "unique_visitors": 0,
                "top_countries": [],
                "top_referrers": [],
                "clicks_over_time": self.clicks_over_time(),
            },
        )
        cache_get.assert_not_called()
        enqueue.assert_not_called()

    def test_total_clicks_counts_only_events_for_requested_url(self):
        requested_url = self.add_url("counted")
        other_url = self.add_url("other")
        now = self.now

        db.session.add_all(
            [
                ClickEvent(url_id=requested_url.id, timestamp=now),
                ClickEvent(url_id=requested_url.id, timestamp=now),
                ClickEvent(url_id=requested_url.id, timestamp=now),
                ClickEvent(url_id=other_url.id, timestamp=now),
            ]
        )
        db.session.commit()

        response = self.get_analytics("counted")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "total_clicks": 3,
                "unique_visitors": 0,
                "top_countries": [],
                "top_referrers": [],
                "clicks_over_time": self.clicks_over_time(
                    {self.now.date().isoformat(): 3}
                ),
            },
        )

    def test_top_countries_excludes_nulls_and_returns_ranked_top_five(self):
        requested_url = self.add_url("countries")
        other_url = self.add_url("other-countries")
        now = self.now

        def events(url_id, country, count):
            return [
                ClickEvent(url_id=url_id, timestamp=now, country=country)
                for _ in range(count)
            ]

        db.session.add_all(
            events(requested_url.id, "India", 4)
            + events(requested_url.id, "Canada", 3)
            + events(requested_url.id, "Brazil", 2)
            + events(requested_url.id, "Denmark", 1)
            + events(requested_url.id, "Estonia", 1)
            + events(requested_url.id, "France", 1)
            + events(requested_url.id, None, 2)
            + events(other_url.id, "United States", 10)
        )
        db.session.commit()

        response = self.get_analytics("countries")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "total_clicks": 14,
                "unique_visitors": 0,
                "top_countries": [
                    {"country": "India", "clicks": 4},
                    {"country": "Canada", "clicks": 3},
                    {"country": "Brazil", "clicks": 2},
                    {"country": "Denmark", "clicks": 1},
                    {"country": "Estonia", "clicks": 1},
                ],
                "top_referrers": [],
                "clicks_over_time": self.clicks_over_time(
                    {self.now.date().isoformat(): 14}
                ),
            },
        )

    def test_top_referrers_excludes_nulls_and_returns_ranked_top_five(self):
        requested_url = self.add_url("referrers")
        other_url = self.add_url("other-referrers")
        now = self.now

        def events(url_id, referrer, count):
            return [
                ClickEvent(url_id=url_id, timestamp=now, referrer=referrer)
                for _ in range(count)
            ]

        db.session.add_all(
            events(requested_url.id, "https://google.example", 4)
            + events(requested_url.id, "https://bing.example", 3)
            + events(requested_url.id, "https://search.example", 2)
            + events(requested_url.id, "https://delta.example", 1)
            + events(requested_url.id, "https://echo.example", 1)
            + events(requested_url.id, "https://foxtrot.example", 1)
            + events(requested_url.id, None, 2)
            + events(other_url.id, "https://other.example", 10)
        )
        db.session.commit()

        response = self.get_analytics("referrers")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "total_clicks": 14,
                "unique_visitors": 0,
                "top_countries": [],
                "top_referrers": [
                    {"referrer": "https://google.example", "clicks": 4},
                    {"referrer": "https://bing.example", "clicks": 3},
                    {"referrer": "https://search.example", "clicks": 2},
                    {"referrer": "https://delta.example", "clicks": 1},
                    {"referrer": "https://echo.example", "clicks": 1},
                ],
                "clicks_over_time": self.clicks_over_time(
                    {self.now.date().isoformat(): 14}
                ),
            },
        )

    def test_clicks_over_time_uses_utc_dates_and_zero_fills_range(self):
        requested_url = self.add_url("timeline")
        other_url = self.add_url("other-timeline")
        start = self.now - timedelta(days=6, hours=12)
        range_end = start + timedelta(days=7)

        db.session.add_all(
            [
                ClickEvent(url_id=requested_url.id, timestamp=start),
                ClickEvent(
                    url_id=requested_url.id,
                    timestamp=start + timedelta(days=2, hours=23, minutes=59),
                ),
                ClickEvent(
                    url_id=requested_url.id,
                    timestamp=start + timedelta(days=2, hours=23, minutes=59),
                ),
                ClickEvent(
                    url_id=requested_url.id,
                    timestamp=start + timedelta(days=5, hours=12),
                ),
                ClickEvent(
                    url_id=requested_url.id,
                    timestamp=start + timedelta(days=6, hours=12),
                ),
                ClickEvent(
                    url_id=requested_url.id,
                    timestamp=start - timedelta(microseconds=1),
                ),
                ClickEvent(url_id=requested_url.id, timestamp=range_end),
                ClickEvent(
                    url_id=other_url.id,
                    timestamp=start + timedelta(days=4, hours=12),
                ),
            ]
        )
        db.session.commit()

        response = self.get_analytics("timeline")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total_clicks"], 7)
        self.assertEqual(response.get_json()["unique_visitors"], 0)
        self.assertEqual(
            response.get_json()["clicks_over_time"],
            self.clicks_over_time(
                {
                    "2026-09-21": 1,
                    "2026-09-23": 2,
                    "2026-09-26": 1,
                    "2026-09-27": 1,
                }
            ),
        )

    def test_events_with_only_null_countries_return_empty_ranking(self):
        requested_url = self.add_url("null-countries")
        now = self.now

        db.session.add_all(
            [
                ClickEvent(url_id=requested_url.id, timestamp=now),
                ClickEvent(url_id=requested_url.id, timestamp=now),
            ]
        )
        db.session.commit()

        response = self.get_analytics("null-countries")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "total_clicks": 2,
                "unique_visitors": 0,
                "top_countries": [],
                "top_referrers": [],
                "clicks_over_time": self.clicks_over_time(
                    {self.now.date().isoformat(): 2}
                ),
            },
        )

    def test_unique_visitors_counts_distinct_non_null_hashes_for_url(self):
        requested_url = self.add_url("visitors")
        other_url = self.add_url("other-visitors")

        db.session.add_all(
            [
                ClickEvent(
                    url_id=requested_url.id,
                    timestamp=self.now,
                    visitor_hash="hash-a",
                ),
                ClickEvent(
                    url_id=requested_url.id,
                    timestamp=self.now,
                    visitor_hash="hash-a",
                ),
                ClickEvent(
                    url_id=requested_url.id,
                    timestamp=self.now,
                    visitor_hash="hash-b",
                ),
                ClickEvent(url_id=requested_url.id, timestamp=self.now),
                ClickEvent(url_id=requested_url.id, timestamp=self.now),
                ClickEvent(
                    url_id=other_url.id,
                    timestamp=self.now,
                    visitor_hash="hash-c",
                ),
                ClickEvent(
                    url_id=other_url.id,
                    timestamp=self.now,
                    visitor_hash="hash-d",
                ),
            ]
        )
        db.session.commit()

        response = self.get_analytics("visitors")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "total_clicks": 5,
                "unique_visitors": 2,
                "top_countries": [],
                "top_referrers": [],
                "clicks_over_time": self.clicks_over_time(
                    {self.now.date().isoformat(): 5}
                ),
            },
        )

    def test_unknown_short_url_returns_not_found(self):
        response = self.get_analytics("missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Short URL not found"})

    def test_redirect_still_caches_and_enqueues_click_processing(self):
        created_url = self.add_url("go")

        with patch("routes.redis_client.get", return_value=None), patch(
            "routes.redis_client.set"
        ) as cache_set, patch("routes.rq_queue.enqueue") as enqueue:
            response = self.client.get("/go", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "https://example.com")

        cache_set.assert_called_once()

        cache_key, cache_value = cache_set.call_args.args
        self.assertEqual(cache_key, "go")
        self.assertEqual(
            json.loads(cache_value),
            {
                "url_id": created_url.id,
                "original_url": "https://example.com",
                "expires_at": None,
                "is_active": True,
            },
        )

        enqueue.assert_called_once()


if __name__ == "__main__":
    unittest.main()