"""Polite HTTP fetching, shared by every collector.

Both upstreams this benchmark draws on are public-good infrastructure — a
volunteer-run food database and a government portal. Neither owes us bandwidth,
so retries back off hard and the caller is expected to sleep between requests.
"""

from __future__ import annotations

import http.client
import json
import random
import sys
import time
import urllib.error
import urllib.request

UA = "gst-eval-harness/0.1 (research benchmark; contact via repository issues)"

#: Codes worth retrying. Everything else is a real answer and re-raises.
RETRYABLE = frozenset({429, 500, 502, 503, 504})


class Unavailable(RuntimeError):
    """Upstream did not answer after the configured retries."""


def fetch(url: str, *, retries: int = 6, timeout: int = 90, quiet: bool = False) -> bytes:
    """GET `url`, retrying transient failures with jittered exponential backoff.

    Raises `Unavailable` when retries are exhausted, and re-raises HTTPError
    unchanged for non-retryable codes so callers can tell "busy" from "gone".
    """
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE:
                raise
            last = exc
            wait = min(60.0, 5.0 * 2**attempt) + random.uniform(0, 3)
            if not quiet:
                print(f"    HTTP {exc.code}; retrying in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
        except (
            urllib.error.URLError,
            TimeoutError,
            # Truncated response mid-download. Observed on multi-megabyte PDFs
            # from the GST Council portal; a plain retry usually succeeds.
            http.client.IncompleteRead,
            http.client.HTTPException,
            ConnectionError,
        ) as exc:
            last = exc
            time.sleep(2**attempt + random.random())

    raise Unavailable(f"{url}: {last}")


def fetch_text(url: str, **kw) -> str:
    return fetch(url, **kw).decode("utf-8", errors="replace")


def fetch_json(url: str, **kw) -> dict:
    raw = fetch_text(url, **kw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Unavailable(f"{url}: bad JSON: {exc}") from exc
