"""Технический builtin timer adapter. Не production monetization provider."""

from __future__ import annotations

from typing import Any

from app.integrations.ads.base import (
    AdContext,
    ProviderPreparation,
    ProviderVerification,
)
from app.integrations.ads.common import (
    basic_eligibility,
    normalized_provider_error,
)
from app.services.ads.config_service import ProviderRuntimeConfig


class BuiltinTimerAdapter:
    code = "builtin_timer"

    def is_configured(self, config: ProviderRuntimeConfig) -> bool:
        return bool(config.is_configured())

    def is_eligible(self, config: ProviderRuntimeConfig, context: AdContext, *, surface: str = "miniapp") -> tuple[bool, str | None]:
        if not context.test_mode:
            return False, "NOT_SUPPORTED"
        eligible, reason = basic_eligibility(config, context, surface=surface)
        return bool(eligible), str(reason) if reason is not None else None

    async def prepare(self, config: ProviderRuntimeConfig, context: AdContext, *, session_id: str, task_code: str, placement: str | None = None, required_format: str = "rewarded") -> ProviderPreparation:
        _ = context, task_code, placement, required_format
        return ProviderPreparation(
            provider=self.code,
            provider_ref=session_id,
            public_config={
                "adapter": "builtin_timer",
                "diagnostic_only": True,
                "min_view_sec": int(config.public.get("min_view_sec") or 20),
            },
        )

    async def verify_callback(self, config: ProviderRuntimeConfig, payload: dict[str, Any], *, session_id: str) -> ProviderVerification:
        _ = config
        completed = bool(payload.get("diagnostic_completed", False))
        # Даже successful diagnostic не разрешает production EFHCb reward;
        # AdManager отдельно запрещает reward для test_mode/builtin_timer.
        return ProviderVerification(self.code, f"builtin:{session_id}", completed, completed)

    def normalize_error(self, error: object) -> str:
        return str(normalized_provider_error(error))
