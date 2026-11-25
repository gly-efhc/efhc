"""Общий контракт provider-adapter рекламного mediation EFHC.

Provider-specific код живёт только в ``app.integrations.ads``. AdManager знает
контракт адаптера, но не SDK/API конкретной рекламной сети.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from app.services.ads.config_service import ProviderRuntimeConfig


@dataclass(frozen=True, slots=True)
class AdContext:
    """Безопасный provider context одной рекламной сессии."""

    app_language: str
    country_code: str | None = None
    platform: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None
    provider_tg_id: int | None = None
    telegram_premium: bool | None = None
    test_mode: bool = False


@dataclass(slots=True)
class ProviderPreparation:
    """Только публичные данные, которые допустимо вернуть Mini App."""

    provider: str
    public_config: dict[str, Any]
    provider_ref: str | None = None
    estimated_revenue_usd: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderVerification:
    """Нормализованный результат provider event/callback."""

    provider: str
    provider_event_id: str
    verified: bool
    completed: bool
    valued: bool | None = None
    estimated_revenue_usd: Decimal | None = None
    actual_revenue_usd: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderAdapter(Protocol):
    code: str

    def is_configured(self, config: ProviderRuntimeConfig) -> bool: ...

    def is_eligible(
        self,
        config: ProviderRuntimeConfig,
        context: AdContext,
        *,
        surface: str = "miniapp",
    ) -> tuple[bool, str | None]: ...

    async def prepare(
        self,
        config: ProviderRuntimeConfig,
        context: AdContext,
        *,
        session_id: str,
        task_code: str,
        placement: str | None = None,
        required_format: str = "rewarded",
    ) -> ProviderPreparation: ...

    async def verify_callback(
        self,
        config: ProviderRuntimeConfig,
        payload: dict[str, Any],
        *,
        session_id: str,
    ) -> ProviderVerification: ...

    def normalize_error(self, error: object) -> str: ...
