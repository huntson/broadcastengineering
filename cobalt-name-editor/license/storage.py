"""Persistence helpers for license state and simple app settings."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Optional

# Store license next to the executable
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    DEFAULT_DIR = Path(sys.executable).parent
else:
    # Running as script
    DEFAULT_DIR = Path(__file__).parent.parent

DEFAULT_PATH = DEFAULT_DIR / "cobalt-name-editor-license.json"
SETTINGS_PATH = DEFAULT_DIR / "cobalt-name-editor-settings.json"


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


def load_settings(path: Optional[Path] = None) -> Dict[str, str]:
    target = path if path is not None else SETTINGS_PATH
    try:
        with target.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            if isinstance(payload, dict):
                return {str(k): str(v) for k, v in payload.items()}
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_settings(settings: Dict[str, str], path: Optional[Path] = None) -> Path:
    target = path if path is not None else SETTINGS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(settings, handle)
    return target
