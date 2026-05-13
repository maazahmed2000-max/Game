"""HTTP JSON API to the game server (works in browser via urllib + CORS)."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from constants import API_BASE_URL, REQUEST_TIMEOUT_S


class ApiError(Exception):
    pass


def _full_url(path: str) -> str:
    return API_BASE_URL.rstrip("/") + path


def _request_sync(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data: Optional[bytes] = None
    headers = {}
    if body is not None and method != "GET":
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(_full_url(path), data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8")
        except Exception:
            detail = str(e)
        raise ApiError(detail or f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise ApiError(str(e.reason if hasattr(e, "reason") else e)) from e


async def api_get(path: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_request_sync, "GET", path, None)


async def api_post(path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return await asyncio.to_thread(_request_sync, "POST", path, body)
