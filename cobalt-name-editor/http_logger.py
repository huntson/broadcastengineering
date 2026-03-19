"""Transparent HTTP request/response logger for bug reports.

Monkey-patches requests.Session.request so every HTTP call made by the
application (device_interface.py, main.py) is captured without touching
existing call sites.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

# Sensitive headers to redact from logs
_REDACT_HEADERS = frozenset({
    "authorization", "cookie", "set-cookie", "x-api-key",
})

_BODY_PREVIEW_LIMIT = 2000
_MAX_ENTRIES = 1000
_TRIM_THRESHOLD = 1250

# Module-level singleton
_instance: Optional[HttpLogger] = None
_original_request = requests.Session.request


@dataclass
class HttpLogEntry:
    timestamp: str
    method: str
    url: str
    request_headers: Dict[str, str] = field(default_factory=dict)
    request_body_preview: str = ""
    response_status: Optional[int] = None
    response_headers: Dict[str, str] = field(default_factory=dict)
    response_body_preview: str = ""
    elapsed_ms: Optional[float] = None
    error: Optional[str] = None

    def to_text(self) -> str:
        lines = [
            f"[{self.timestamp}] {self.method} {self.url}",
        ]
        if self.request_headers:
            lines.append(f"  Req Headers: {self.request_headers}")
        if self.request_body_preview:
            lines.append(f"  Req Body: {self.request_body_preview}")
        if self.error:
            lines.append(f"  ERROR: {self.error}")
        else:
            lines.append(f"  Status: {self.response_status}  ({self.elapsed_ms:.0f}ms)")
            if self.response_headers:
                lines.append(f"  Resp Headers: {self.response_headers}")
            if self.response_body_preview:
                lines.append(f"  Resp Body: {self.response_body_preview}")
        return "\n".join(lines)


def _sanitize_headers(headers: Any) -> Dict[str, str]:
    if not headers:
        return {}
    out = {}
    for k, v in dict(headers).items():
        if k.lower() in _REDACT_HEADERS:
            out[k] = "[REDACTED]"
        else:
            out[k] = str(v)
    return out


def _truncate(text: Any, limit: int = _BODY_PREVIEW_LIMIT) -> str:
    s = str(text) if text else ""
    if len(s) > limit:
        return s[:limit] + f"... [{len(s) - limit} more chars]"
    return s


def _extract_body_preview(kwargs: dict) -> str:
    if "data" in kwargs and kwargs["data"]:
        return _truncate(kwargs["data"])
    if "json" in kwargs and kwargs["json"]:
        import json
        try:
            return _truncate(json.dumps(kwargs["json"]))
        except (TypeError, ValueError):
            return _truncate(str(kwargs["json"]))
    return ""


class HttpLogger:
    """Thread-safe collection of HTTP log entries."""

    def __init__(self, max_entries: int = _MAX_ENTRIES) -> None:
        self._entries: List[HttpLogEntry] = []
        self._max_entries = max_entries
        self._lock = threading.Lock()

    def log_response(
        self,
        method: str,
        url: str,
        response: requests.Response,
        elapsed_ms: float,
        kwargs: dict,
    ) -> None:
        entry = HttpLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            method=method.upper(),
            url=url,
            request_headers=_sanitize_headers(kwargs.get("headers")),
            request_body_preview=_extract_body_preview(kwargs),
            response_status=response.status_code,
            response_headers=_sanitize_headers(response.headers),
            response_body_preview=_truncate(response.text),
            elapsed_ms=elapsed_ms,
        )
        self._append(entry)

    def log_error(
        self,
        method: str,
        url: str,
        error: Exception,
        elapsed_ms: float,
        kwargs: dict,
    ) -> None:
        entry = HttpLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            method=method.upper(),
            url=url,
            request_headers=_sanitize_headers(kwargs.get("headers")),
            request_body_preview=_extract_body_preview(kwargs),
            elapsed_ms=elapsed_ms,
            error=str(error),
        )
        self._append(entry)

    def _append(self, entry: HttpLogEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > _TRIM_THRESHOLD:
                self._entries = self._entries[-self._max_entries:]

    def get_entries(self) -> List[HttpLogEntry]:
        with self._lock:
            return list(self._entries)

    def get_text(self) -> str:
        entries = self.get_entries()
        if not entries:
            return "(no HTTP requests captured)"
        return "\n\n".join(e.to_text() for e in entries)

    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# ---------------------------------------------------------------------------
# Monkey-patch plumbing
# ---------------------------------------------------------------------------

def _patched_request(self, method, url, **kwargs):
    logger = get_logger()
    start = time.time()
    try:
        response = _original_request(self, method, url, **kwargs)
        elapsed = (time.time() - start) * 1000
        if logger:
            logger.log_response(method, url, response, elapsed, kwargs)
        return response
    except Exception as exc:
        elapsed = (time.time() - start) * 1000
        if logger:
            logger.log_error(method, url, exc, elapsed, kwargs)
        raise


def install() -> HttpLogger:
    """Install the HTTP logger. Returns the singleton instance."""
    global _instance
    _instance = HttpLogger()
    requests.Session.request = _patched_request
    return _instance


def get_logger() -> Optional[HttpLogger]:
    """Return the installed HttpLogger, or None."""
    return _instance


def unlogged_post(url: str, **kwargs) -> requests.Response:
    """POST without going through the monkey-patched logger.

    Used by bug_report.py to call the SMTP2GO API without logging
    the API key in the request body.
    """
    session = requests.Session()
    return _original_request(session, "POST", url, **kwargs)
