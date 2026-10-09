"""Download the GeoLite2 Country database during a deployment build."""

import base64
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


DOWNLOAD_URL = (
    "https://download.maxmind.com/geoip/databases/GeoLite2-Country/"
    "download?suffix=tar.gz"
)
DEFAULT_DATABASE_PATH = "data/GeoLite2-Country.mmdb"
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 3


class DownloadError(Exception):
    """Raised when a GeoLite2 database cannot be safely downloaded."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Return redirect responses so the caller can follow them safely."""

    def redirect_request(self, request, file_pointer, code, message, headers, url):
        return None


def open_without_redirects(request, timeout):
    """Open one URL while preventing urllib from copying request headers onward."""
    return build_opener(NoRedirectHandler()).open(request, timeout=timeout)


def response_or_redirect_error(opener, request):
    """Return a response, including an HTTP redirect represented as HTTPError."""
    try:
        return opener(request, timeout=30)
    except HTTPError as error:
        if error.code in REDIRECT_STATUS_CODES:
            return error
        raise


def download_database(
    account_id,
    license_key,
    destination,
    opener=open_without_redirects,
):
    """Download, validate, and atomically place the Country database."""
    if not account_id or not license_key:
        raise DownloadError(
            "MAXMIND_ACCOUNT_ID and MAXMIND_LICENSE_KEY must both be configured"
        )

    destination = Path(destination)
    credentials = f"{account_id}:{license_key}".encode("utf-8")
    authorization = base64.b64encode(credentials).decode("ascii")
    request = Request(DOWNLOAD_URL)
    # Do not allow urllib to copy credentials to a different redirect host.
    request.add_unredirected_header("Authorization", f"Basic {authorization}")

    try:
        for _ in range(MAX_REDIRECTS + 1):
            with response_or_redirect_error(opener, request) as response:
                status = response.getcode()
                if status == 200:
                    archive_data = response.read()
                    break

                if status not in REDIRECT_STATUS_CODES:
                    raise DownloadError(
                        "MaxMind returned an unsuccessful HTTP response"
                    )

                location = response.headers.get("Location")
                if not location:
                    raise DownloadError("MaxMind redirect did not provide a location")

                redirect_url = urljoin(request.full_url, location)
                if urlsplit(redirect_url).scheme != "https":
                    raise DownloadError("MaxMind redirect did not use HTTPS")

            # A newly constructed request deliberately has no Authorization header.
            request = Request(redirect_url)
        else:
            raise DownloadError("MaxMind download exceeded the redirect limit")
    except HTTPError as error:
        raise DownloadError(
            f"MaxMind download failed with HTTP status {error.code}"
        ) from error
    except URLError as error:
        raise DownloadError("MaxMind download could not be completed") from error

    try:
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as archive:
            members = [
                member
                for member in archive.getmembers()
                if member.isfile()
                and member.name.endswith("/GeoLite2-Country.mmdb")
            ]
            if len(members) != 1:
                raise DownloadError(
                    "GeoLite2 archive does not contain one Country database file"
                )

            database_file = archive.extractfile(members[0])
            if database_file is None:
                raise DownloadError("GeoLite2 database file could not be extracted")

            database_data = database_file.read()
    except (tarfile.TarError, OSError) as error:
        raise DownloadError("Downloaded GeoLite2 archive is invalid") from error

    if not database_data:
        raise DownloadError("Downloaded GeoLite2 database file is empty")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(database_data)
        os.replace(temporary_path, destination)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise DownloadError("GeoLite2 database file could not be written") from error


def main():
    try:
        download_database(
            os.getenv("MAXMIND_ACCOUNT_ID"),
            os.getenv("MAXMIND_LICENSE_KEY"),
            os.getenv("GEOLITE2_DATABASE_PATH", DEFAULT_DATABASE_PATH),
        )
    except DownloadError as error:
        print(f"GeoLite2 download failed: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
