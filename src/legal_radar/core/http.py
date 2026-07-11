"""Einziger Ort mit HTTP-Code. Adapter rufen nur get_json/get_text."""

from __future__ import annotations

import time

import httpx

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_client = httpx.Client(
    timeout=30.0,
    headers={"User-Agent": _UA, "Accept": "application/json"},
    follow_redirects=True,
)


def _check_throttle(r) -> None:
    if r.status_code in (429, 503):
        raise httpx.HTTPError(f"throttled {r.status_code}")


def _retry(fn, attempts: int = 4):
    for i in range(attempts):
        try:
            r = fn()
            _check_throttle(r)
            r.raise_for_status()
        except httpx.HTTPError:
            if i == attempts - 1:
                raise
            time.sleep(2**i)
        else:
            return r
    raise RuntimeError("unreachable")


def get_json(url: str, **kw) -> dict:
    time.sleep(0.3)
    return _retry(lambda: _client.get(url, **kw)).json()


def get_text(url: str, **kw) -> str:
    time.sleep(0.3)
    return _retry(lambda: _client.get(url, **kw)).text
