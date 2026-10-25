"""Polite HTTP GET for JSON: offline guard, User-Agent, minimum interval between requests, retries.

LASTPROG_OFFLINE=1 makes every call raise OfflineError before any socket is opened (set in CI and tests).
"""

from __future__ import annotations

import logging
import os
import time

import requests

log = logging.getLogger(__name__)


class OfflineError(RuntimeError):
    """Raised for any HTTP call while LASTPROG_OFFLINE=1."""


class NotFoundError(RuntimeError):
    """HTTP 404."""


def _is_transient(exc: requests.RequestException) -> bool:
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else 0
        return status == 429 or 500 <= status <= 599
    return isinstance(
        exc,
        (
            requests.ConnectionError,
            requests.Timeout,
            requests.JSONDecodeError,
            requests.exceptions.ChunkedEncodingError,
        ),
    )


class HttpClient:
    def __init__(
        self,
        user_agent: str,
        min_interval_s: float = 1.0,
        retries: int = 3,
        backoff_s: float = 2.0,
        timeout_s: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        if retries < 1:
            raise ValueError(f"retries must be at least 1, got {retries}")
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.min_interval_s = min_interval_s
        self.retries = retries
        self.backoff_s = backoff_s
        self.timeout_s = timeout_s
        self.calls = 0
        self._last = 0.0

    def get_json(self, url: str, params: dict | None = None):
        """GET a JSON document. 404 raises NotFoundError; transient failures are retried with linear backoff."""
        if os.environ.get("LASTPROG_OFFLINE") == "1":
            raise OfflineError(f"LASTPROG_OFFLINE=1, refusing GET {url}")
        attempt = 0
        while True:
            attempt += 1
            wait = self._last + self.min_interval_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                self.calls += 1
                resp = self.session.get(url, params=params, timeout=self.timeout_s)
                self._last = time.monotonic()
                if resp.status_code == 404:
                    raise NotFoundError(f"GET {url} returned 404")
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                self._last = time.monotonic()
                if attempt >= self.retries or not _is_transient(exc):
                    raise RuntimeError(f"GET {url} failed after {attempt} attempts") from exc
                log.warning("GET %s failed (attempt %d/%d), retrying: %s", url, attempt, self.retries, exc)
                time.sleep(self.backoff_s * attempt)
