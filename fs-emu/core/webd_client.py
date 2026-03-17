"""Direct HTTP client for webd's /config REST API.

Bypasses the serial console entirely — sets configd params via webd's
HTTP interface at ~10ms per request instead of ~1.3s through config_cli.
"""

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


class WebdClient:
    """Talks to webd's REST API to get/set configd parameters."""

    def __init__(self, base_url="http://127.0.0.1:19080"):
        self.base_url = base_url
        self._pool = ThreadPoolExecutor(max_workers=8)

    def set_param(self, param_id, value, timeout=5.0):
        """Set a single configd param via webd HTTP. Returns True on success."""
        url = "%s/config?alt=json&action=set&paramid=%s&value=%s" % (
            self.base_url, param_id, value)
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def set_params(self, params, timeout=5.0):
        """Set multiple params in parallel.

        Args:
            params: list of (param_id, value) tuples
            timeout: per-request timeout in seconds

        Returns:
            Number of successful sets.
        """
        if not params:
            return 0
        futures = {
            self._pool.submit(self.set_param, pid, val, timeout): (pid, val)
            for pid, val in params
        }
        ok = 0
        for f in as_completed(futures):
            if f.result():
                ok += 1
        return ok

    def get_param(self, param_id, timeout=5.0):
        """Get a single param value. Returns string value or None."""
        url = "%s/config?alt=json&action=get&paramid=%s" % (
            self.base_url, param_id)
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                return data.get("value")
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None

    def is_available(self):
        """Quick check if webd is responding."""
        return self.get_param("eParamID_ProductID", timeout=2.0) is not None

    def get_param_enum(self, param_id, timeout=15.0):
        """Fetch the enum values for a param from desc.json.

        Returns dict {int_value: display_name} or None on failure.
        """
        url = "%s/desc.json" % self.base_url
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                desc = json.loads(resp.read())
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None

        for entry in desc:
            if not isinstance(entry, dict):
                continue
            if entry.get("param_id") == param_id:
                enums = entry.get("enum_values", [])
                if not enums:
                    return None
                return {
                    e["value"]: e.get("text", str(e["value"]))
                    for e in enums if isinstance(e, dict) and "value" in e
                }
        return None
