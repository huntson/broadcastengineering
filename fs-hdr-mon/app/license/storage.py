"""Persistence helpers for license state."""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from typing import Dict, Optional


def _get_app_dir() -> Path:
    """Get the directory where the app is running from (portable mode)."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle (.exe)
        return Path(sys.executable).parent
    else:
        # Running as Python script (development mode)
        return Path(__file__).resolve().parent.parent


DEFAULT_DIR = _get_app_dir()
DEFAULT_PATH = DEFAULT_DIR / "license.json"


def _resolve_path(path: Optional[Path]) -> Path:
    return path if path is not None else DEFAULT_PATH


def load_cached_license(path: Optional[Path] = None) -> Optional[Dict[str, str]]:
    target = _resolve_path(path)
    try:
        with target.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None
    name = payload.get("name")
    key = payload.get("key")
    if not name or not key:
        return None
    return {"name": str(name), "key": str(key)}


def save_license(name: str, key: str, path: Optional[Path] = None) -> Path:
    target = _resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"name": name, "key": key}
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return target


def clear_license(path: Optional[Path] = None) -> None:
    target = _resolve_path(path)
    try:
        target.unlink()
    except FileNotFoundError:
        return
