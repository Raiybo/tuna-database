"""Tiny HTTP helper (stdlib only) with verified TLS and retries.

Uses certifi's CA bundle when available so it works on Python builds that aren't
linked to the system trust store (e.g. python.org installs on macOS)."""
from __future__ import annotations

import json
import ssl
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


def _ctx() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_SSL = _ctx()


def get_text(url: str, retries: int = 3, timeout: int = 25) -> str:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "tuna-database/0.2"})
            with urlopen(req, timeout=timeout, context=_SSL) as resp:
                return resp.read().decode("utf-8")
        except (URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"request failed ({url[:70]}...): {last}")


def get_json(url: str, retries: int = 3, timeout: int = 25) -> dict:
    return json.loads(get_text(url, retries, timeout))


def post(url: str, data: bytes, headers: dict | None = None, timeout: int = 20):
    """POST raw bytes (used by the notifier). Returns (status_code, body_text)."""
    req = Request(url, data=data, headers=headers or {}, method="POST")
    with urlopen(req, timeout=timeout, context=_SSL) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def hour_index(times, label) -> int:
    """Index in an hourly time array matching a 'YYYY-MM-DDTHH:MM' label."""
    if not label or not times:
        return -1
    key = label[:13] + ":00"
    return times.index(key) if key in times else -1
