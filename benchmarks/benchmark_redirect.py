"""Measure the local hot-cache redirect latency for the existing Flask endpoint.

This script sends HTTP requests only. It does not import the application or
access Redis or PostgreSQL directly, so the normal redirect behavior warms the
cache and enqueues click events exactly as it does for a regular client.
"""

from __future__ import annotations

import http.client
import statistics
import sys
import time
from collections import Counter


HOST = "127.0.0.1"
PORT = 5000
PATH = "/info"
EXPECTED_STATUS = 302
WARMUP_REQUESTS = 20
TIMED_REQUESTS = 200
TIMEOUT_SECONDS = 5


def make_request(connection: http.client.HTTPConnection) -> int:
    """Issue one request without following the redirect and return its status."""
    connection.request("GET", PATH, headers={"Connection": "keep-alive"})
    response = connection.getresponse()
    status = response.status
    response.read()
    return status


def percentile_95(values: list[float]) -> float:
    """Return P95 using the standard-library inclusive percentile method."""
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def close_quietly(connection: http.client.HTTPConnection | None) -> None:
    if connection is not None:
        try:
            connection.close()
        except OSError:
            pass


def main() -> int:
    print("Local development benchmark: existing hot-cache redirect path")
    print(f"Target: http://{HOST}:{PORT}{PATH}")
    print("Redirect following: disabled (http.client does not follow redirects)")

    connection: http.client.HTTPConnection | None = http.client.HTTPConnection(
        HOST,
        PORT,
        timeout=TIMEOUT_SECONDS,
    )

    try:
        try:
            verification_status = make_request(connection)
        except (OSError, http.client.HTTPException) as error:
            print(f"Verification failed: {error}")
            return 1

        if verification_status != EXPECTED_STATUS:
            print(
                "Verification failed: expected HTTP "
                f"{EXPECTED_STATUS}, received HTTP {verification_status}."
            )
            print("No benchmark measurements were collected.")
            return 1

        print(f"Verification passed: received HTTP {EXPECTED_STATUS}.")
        print(f"Sending {WARMUP_REQUESTS} untimed warm-up requests...")

        for request_number in range(1, WARMUP_REQUESTS + 1):
            try:
                status = make_request(connection)
            except (OSError, http.client.HTTPException) as error:
                print(f"Warm-up request {request_number} failed: {error}")
                return 1

            if status != EXPECTED_STATUS:
                print(
                    f"Warm-up request {request_number} failed: expected HTTP "
                    f"{EXPECTED_STATUS}, received HTTP {status}."
                )
                return 1

        latencies_ms: list[float] = []
        statuses: list[int] = []
        errors: list[str] = []

        print(f"Recording {TIMED_REQUESTS} sequential requests...")
        for request_number in range(1, TIMED_REQUESTS + 1):
            start = time.perf_counter()
            try:
                status = make_request(connection)
            except (OSError, http.client.HTTPException) as error:
                elapsed_ms = (time.perf_counter() - start) * 1000
                errors.append(
                    f"Request {request_number}: {type(error).__name__}: {error} "
                    f"({elapsed_ms:.3f} ms)"
                )
                close_quietly(connection)
                connection = http.client.HTTPConnection(
                    HOST,
                    PORT,
                    timeout=TIMEOUT_SECONDS,
                )
                continue

            latencies_ms.append((time.perf_counter() - start) * 1000)
            statuses.append(status)

        status_counts = Counter(statuses)
        successful_requests = status_counts[EXPECTED_STATUS]
        unexpected_statuses = sum(
            count
            for status, count in status_counts.items()
            if status != EXPECTED_STATUS
        )
        error_count = len(errors) + unexpected_statuses

        print("\nResults")
        print(f"Successful HTTP {EXPECTED_STATUS} responses: {successful_requests}")
        print(f"Errors: {error_count}")
        print("HTTP status distribution:")
        if status_counts:
            for status, count in sorted(status_counts.items()):
                print(f"  HTTP {status}: {count}")
        else:
            print("  No HTTP responses received")

        if errors:
            print("Transport errors:")
            for error in errors:
                print(f"  {error}")

        if latencies_ms:
            print("Latency (all received HTTP responses, milliseconds):")
            print(f"  Minimum: {min(latencies_ms):.3f} ms")
            print(f"  Maximum: {max(latencies_ms):.3f} ms")
            print(f"  Mean: {statistics.mean(latencies_ms):.3f} ms")
            print(f"  Median: {statistics.median(latencies_ms):.3f} ms")
            if len(latencies_ms) >= 2:
                print(
                    "  P95: "
                    f"{percentile_95(latencies_ms):.3f} ms "
                    "(statistics.quantiles, inclusive method)"
                )
            else:
                print("  P95: unavailable (fewer than two HTTP responses)")

        if error_count:
            print(
                "\nBenchmark invalid: one or more timed requests did not return "
                f"the expected HTTP {EXPECTED_STATUS}; do not treat these results "
                "as a hot-cache baseline."
            )
            return 1

        p95_ms = percentile_95(latencies_ms)
        comparison = "meets" if p95_ms < 50 else "does not meet"
        print(
            "\nUnder this local benchmark environment, the observed hot-cache "
            f"redirect P95 was {p95_ms:.3f} ms and {comparison} the <50 ms target."
        )
        print("This local result does not guarantee production performance.")
        return 0
    finally:
        close_quietly(connection)


if __name__ == "__main__":
    sys.exit(main())
