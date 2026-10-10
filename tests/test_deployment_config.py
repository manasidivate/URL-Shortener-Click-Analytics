import base64
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, call, patch
from urllib.error import HTTPError

from app import create_app, normalize_database_url
from extensions import create_redis_clients
from scripts.download_geolite2 import DownloadError, download_database
from tasks import get_country
from werkzeug.middleware.proxy_fix import ProxyFix


class DatabaseUrlNormalizationTests(unittest.TestCase):
    def test_plain_postgresql_url_uses_psycopg_driver(self):
        self.assertEqual(
            normalize_database_url("postgresql://user:password@db.example/app"),
            "postgresql+psycopg://user:password@db.example/app",
        )

    def test_existing_and_unrelated_urls_are_unchanged(self):
        for database_url in (
            "postgresql+psycopg://user:password@db.example/app",
            "sqlite://",
            None,
        ):
            with self.subTest(database_url=database_url):
                self.assertEqual(normalize_database_url(database_url), database_url)


class ForwardedClientIpTests(unittest.TestCase):
    @staticmethod
    def create_app_with_remote_address_route():
        app = create_app()

        @app.route("/remote-address")
        def remote_address():
            from flask import request

            return {"remote_addr": request.remote_addr}

        return app

    def test_render_proxy_uses_one_trusted_forwarded_ip(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "sqlite://", "TRUSTED_PROXY_COUNT": "1"},
            clear=True,
        ):
            app = self.create_app_with_remote_address_route()

        response = app.test_client().get(
            "/remote-address",
            headers={"X-Forwarded-For": "198.51.100.99, 203.0.113.10"},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )

        self.assertEqual(response.get_json(), {"remote_addr": "203.0.113.10"})

    def test_render_proxy_uses_client_ip_from_trusted_three_hop_chain(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "sqlite://", "TRUSTED_PROXY_COUNT": "3"},
            clear=True,
        ):
            app = self.create_app_with_remote_address_route()

        response = app.test_client().get(
            "/remote-address",
            headers={
                "X-Forwarded-For": (
                    "198.51.100.99, 171.76.109.227, "
                    "162.158.54.18, 10.28.211.133"
                )
            },
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )

        self.assertEqual(response.get_json(), {"remote_addr": "171.76.109.227"})

    def test_forwarded_ip_is_not_trusted_without_proxy_configuration(self):
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite://"}, clear=True):
            app = self.create_app_with_remote_address_route()

        response = app.test_client().get(
            "/remote-address",
            headers={"X-Forwarded-For": "198.51.100.99"},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )

        self.assertEqual(response.get_json(), {"remote_addr": "127.0.0.1"})

    def test_zero_trusted_proxy_count_disables_forwarded_ip_trust(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "sqlite://", "TRUSTED_PROXY_COUNT": "0"},
            clear=True,
        ):
            app = self.create_app_with_remote_address_route()

        self.assertNotIsInstance(app.wsgi_app, ProxyFix)

        response = app.test_client().get(
            "/remote-address",
            headers={"X-Forwarded-For": "198.51.100.99"},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )

        self.assertEqual(response.get_json(), {"remote_addr": "127.0.0.1"})


class RedisConfigurationTests(unittest.TestCase):
    @patch("extensions.redis.Redis.from_url")
    def test_cache_and_queue_clients_share_redis_url_with_correct_decoding(
        self,
        from_url,
    ):
        cache_client = Mock()
        queue_client = Mock()
        from_url.side_effect = [cache_client, queue_client]

        result_cache_client, result_queue_client = create_redis_clients(
            "redis://redis.example:6379/0"
        )

        self.assertIs(result_cache_client, cache_client)
        self.assertIs(result_queue_client, queue_client)
        self.assertEqual(
            from_url.call_args_list,
            [
                call(
                    "redis://redis.example:6379/0",
                    decode_responses=True,
                ),
                call("redis://redis.example:6379/0"),
            ],
        )


class GeoLite2DownloaderTests(unittest.TestCase):
    @staticmethod
    def country_database_archive(database_data=b"test-mmdb-data"):
        archive_data = io.BytesIO()
        with tarfile.open(fileobj=archive_data, mode="w:gz") as archive:
            info = tarfile.TarInfo(
                "GeoLite2-Country_20261009/GeoLite2-Country.mmdb"
            )
            info.size = len(database_data)
            archive.addfile(info, io.BytesIO(database_data))
        return archive_data.getvalue()

    @staticmethod
    def response_with(body, status=200):
        response = MagicMock()
        response.getcode.return_value = status
        response.read.return_value = body
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_download_writes_country_database_from_valid_authenticated_archive(self):
        response = self.response_with(self.country_database_archive())
        opener = Mock(return_value=response)

        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "data" / "GeoLite2-Country.mmdb"
            download_database("account-id", "license-key", destination, opener=opener)

            self.assertEqual(destination.read_bytes(), b"test-mmdb-data")

        request = opener.call_args.args[0]
        expected_authorization = base64.b64encode(
            b"account-id:license-key"
        ).decode("ascii")
        self.assertEqual(
            request.get_header("Authorization"),
            f"Basic {expected_authorization}",
        )

    def test_redirected_download_does_not_forward_authorization(self):
        from email.message import Message
        from urllib.error import HTTPError

        from scripts.download_geolite2 import DOWNLOAD_URL

        archive_data = self.country_database_archive()
        redirect_headers = Message()
        redirect_headers["Location"] = (
            "https://storage.example.test/geolite2.tar.gz"
        )

        redirect = HTTPError(
            DOWNLOAD_URL,
            302,
            "Found",
            hdrs=redirect_headers,
            fp=None,
        )
        final_response = self.response_with(archive_data)

        opener = Mock(side_effect=[redirect, final_response])

        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "GeoLite2-Country.mmdb"

            download_database(
                "account-id",
                "license-key",
                destination,
                opener=opener,
            )

            self.assertEqual(destination.read_bytes(), b"test-mmdb-data")

        first_request = opener.call_args_list[0].args[0]
        redirected_request = opener.call_args_list[1].args[0]

        self.assertEqual(
            first_request.get_header("Authorization"),
            "Basic "
            + base64.b64encode(b"account-id:license-key").decode("ascii"),
        )
        self.assertEqual(
            first_request.unredirected_hdrs.get("Authorization"),
            "Basic "
            + base64.b64encode(b"account-id:license-key").decode("ascii"),
        )
        self.assertIsNone(redirected_request.get_header("Authorization"))
        self.assertNotIn("Authorization", redirected_request.unredirected_hdrs)
        self.assertEqual(
            redirected_request.full_url,
            "https://storage.example.test/geolite2.tar.gz",
        )

        redirect.close()

    def test_download_rejects_missing_credentials_before_network_access(self):
        opener = Mock()

        with self.assertRaisesRegex(DownloadError, "must both be configured"):
            download_database(None, "license-key", "unused.mmdb", opener=opener)

        opener.assert_not_called()

    def test_download_rejects_http_errors_and_invalid_archives(self):
        http_error = HTTPError(
            "https://download.maxmind.com",
            401,
            "Unauthorized",
            hdrs=None,
            fp=None,
        )

        with self.assertRaisesRegex(DownloadError, "HTTP status 401"):
            download_database(
                "account-id",
                "license-key",
                "unused.mmdb",
                opener=Mock(side_effect=http_error),
            )
        http_error.close()

        with self.assertRaisesRegex(DownloadError, "archive is invalid"):
            download_database(
                "account-id",
                "license-key",
                "unused.mmdb",
                opener=Mock(return_value=self.response_with(b"not a tar archive")),
            )

    @patch("tasks.geoip2.database.Reader")
    @patch.dict(
        os.environ,
        {"GEOLITE2_DATABASE_PATH": "custom/GeoLite2-Country.mmdb"},
        clear=False,
    )
    def test_country_lookup_uses_configured_database_path(self, reader_class):
        reader = reader_class.return_value
        reader.country.return_value.country.name = "India"

        self.assertEqual(get_country("8.8.8.8"), "India")
        reader_class.assert_called_once_with("custom/GeoLite2-Country.mmdb")
        reader.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
