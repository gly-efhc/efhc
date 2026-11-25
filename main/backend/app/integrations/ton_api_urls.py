"""Canonical TonAPI URL construction."""

from __future__ import annotations


def ton_api_root(value: str) -> str:
    """Return HTTPS TonAPI origin without a trailing ``/v2``."""
    root = str(value or "https://tonapi.io").strip().rstrip("/")
    if root.endswith("/v2"):
        root = root[:-3].rstrip("/")
    return root


def ton_api_base_url(value: str) -> str:
    """Return exactly one ``/v2`` suffix."""
    return ton_api_root(value) + "/v2"
