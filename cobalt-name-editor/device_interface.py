"""device_interface.py – handles download/upload to a single Cobalt device.

Changes in *multi* version:
 • Accepts **just an IP** (or hostname).  Protocol and CGI paths are added automatically.
 • Keeps backward‑compatibility: if the caller passes a full URL that already contains
   the CGI script name, we leave it untouched.
"""
import requests

_DL_PATH = "/cgi-bin/download-config.cgi?primary.txt"
_UL_PATH = "/cgi-bin/update-config.cgi"

def _make_base(ip: str) -> str:
    """Return 'http://<ip>' if scheme missing."""
    if ip.startswith("http://") or ip.startswith("https://"):
        return ip
    return f"http://{ip}"

def _dl_url(target: str) -> str:
    # if the caller already passed the full download URL, don't touch it
    if _DL_PATH in target:
        return target
    return _make_base(target).rstrip("/") + _DL_PATH

def _ul_url(target: str) -> str:
    if _UL_PATH in target:
        return target
    return _make_base(target).rstrip("/") + _UL_PATH

def download_config(target: str, timeout: int = 10) -> str:
    """Fetch primary.txt from *target* and return its text.

    *target* can be:
      • plain IP/hostname – '10.96.50.160'
      • base URL – 'http://10.96.50.160'
      • full CGI URL – 'http://10.96.50.160/cgi-bin/download-config.cgi?primary.txt'
    """
    url = _dl_url(target)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text

def upload_config(target: str, file_text: str, timeout: int = 30) -> None:
    """Upload modified primary.txt back to *target*.

    Raises on any HTTP error.
    """
    url = _ul_url(target)
    files = { "file_data": ("primary.txt", file_text, "text/plain") }
    r = requests.post(url, files=files, timeout=timeout)
    r.raise_for_status()
