# backend/app/utils/cursor_codec.py
# ----------------------------------------------------------------------
# Единый кодек курсора пагинации (SSOT).
# Формат: base64url(json) без padding.
# ----------------------------------------------------------------------

from __future__ import annotations

import base64
import json
from typing import Any


def encode_cursor(payload: dict[str, Any]) -> str:
    """Кодирует payload в base64url(json) без padding."""
    if not isinstance(payload, dict):
        raise TypeError("cursor payload must be a dict")

    data = dict(payload)
    data.setdefault("v", 1)

    raw = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    b64 = base64.urlsafe_b64encode(raw).decode("ascii")
    return b64.rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Декодирует base64url(json) cursor в dict payload."""
    if cursor is None:
        raise ValueError("cursor is required")

    s = str(cursor).strip()
    if not s:
        raise ValueError("cursor is empty")

    pad_len = (-len(s)) % 4
    padded = s + ("=" * pad_len)

    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        obj = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ValueError("invalid cursor") from e

    if not isinstance(obj, dict):
        raise ValueError("cursor payload must be a dict")

    return obj
