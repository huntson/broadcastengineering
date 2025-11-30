"""License verification helpers using Ed25519 signatures."""

from __future__ import annotations

import base64
import json
import time
from functools import lru_cache
from typing import Tuple

import importlib.resources as resources
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

DEFAULT_PRODUCT = "woa-desktop"


def _b64u_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


@lru_cache(maxsize=1)
def load_public_key() -> bytes:
    """Return the embedded public key bytes."""
    with resources.files(__package__).joinpath("lic_public.key").open("rb") as handle:
        data = handle.read()
    if not data:
        raise ValueError("lic_public.key is empty")
    return data


def verify_name_key(
    entered_name: str,
    entered_key: str,
    expected_product: str = DEFAULT_PRODUCT,
) -> Tuple[bool, str]:
    """Validate the license tuple and return (ok, reason)."""
    try:
        parts = entered_key.split(".")
        if len(parts) != 2:
            return False, "Malformed key"

        payload_bytes = _b64u_decode(parts[0])
        signature_bytes = _b64u_decode(parts[1])

        public_key = load_public_key()
        VerifyKey(public_key).verify(payload_bytes, signature_bytes)

        payload = json.loads(payload_bytes.decode("utf-8"))

        if expected_product and payload.get("product") != expected_product:
            return False, "Wrong product"

        license_name = payload.get("name", "")
        if _normalize_name(entered_name) != _normalize_name(license_name):
            return False, "Name does not match license"

        expiry = payload.get("exp")
        if expiry is not None and int(time.time()) > int(expiry):
            return False, "License expired"

        return True, "OK"
    except BadSignatureError:
        return False, "Invalid signature"
    except Exception as exc:  # pragma: no cover - defensive branch
        return False, f"Error: {exc}"

