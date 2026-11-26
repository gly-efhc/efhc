"""Общие provider-adapter helpers без business/reward логики."""

from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal, InvalidOperation
from typing import Any

from app.integrations.ads.base import AdContext
from app.services.ads.config_service import ProviderRuntimeConfig


def basic_eligibility(
    config: ProviderRuntimeConfig,
    context: AdContext,
    *,
    surface: str,
) -> tuple[bool, str | None]:
    if not config.enabled:
        return False, "DISABLED"
    if not config.is_configured():
        return False, "NOT_CONFIGURED"
    if surface == "miniapp" and not config.miniapp_enabled:
        return False, "NOT_SUPPORTED"
    if surface == "bot" and not config.bot_enabled:
        return False, "NOT_SUPPORTED"
    if not config.rewarded_enabled and surface == "miniapp":
        return False, "NOT_SUPPORTED"
    if not config.language_allowed(context.app_language):
        return False, "LANG_NOT_SUPPORTED"
    if not config.country_allowed(context.country_code):
        return False, "GEO_NOT_SUPPORTED"
    if config.health_status == "circuit_open":
        return False, "PROVIDER_ERROR"
    return True, None


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalized_provider_error(error: object) -> str:
    raw = str(error or "").lower()
    if "no fill" in raw or "nofill" in raw or "no_feed" in raw or "no feed" in raw:
        return "NO_FILL"
    if "timeout" in raw:
        return "TIMEOUT"
    if "sdk" in raw and ("load" in raw or "not loaded" in raw):
        return "SDK_LOAD_FAILED"
    if "skip" in raw or "closed" in raw:
        return "USER_SKIPPED"
    return "PROVIDER_ERROR"


def make_signed_correlation(session_id: str, secret: str) -> str:
    """Создать opaque correlation без передачи provider secret в URL/log."""

    sid = str(session_id).strip()
    key = str(secret or "").encode("utf-8")
    if not sid or not key:
        raise ValueError("NOT_CONFIGURED")
    digest = hmac.new(key, sid.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{sid}.{digest}"


def verify_signed_correlation(value: object, session_id: str, secret: str) -> bool:
    candidate = str(value or "")
    try:
        expected = make_signed_correlation(session_id, secret)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, expected)


def correlation_session_id(value: object) -> str | None:
    raw = str(value or "").strip()
    if "." not in raw:
        return None
    session_id, _sig = raw.split(".", 1)
    return session_id or None
