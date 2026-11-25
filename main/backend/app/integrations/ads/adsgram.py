"""AdsGram Mini App Rewarded adapter по официальному ``Adsgram.init/show``."""

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


class AdsGramAdapter:
    code = "adsgram"

    def is_configured(self, config: ProviderRuntimeConfig) -> bool:
        return bool(config.is_configured())

    def is_eligible(
        self,
        config: ProviderRuntimeConfig,
        context: AdContext,
        *,
        surface: str = "miniapp",
    ) -> tuple[bool, str | None]:
        eligible, reason = basic_eligibility(config, context, surface=surface)
        return bool(eligible), str(reason) if reason is not None else None

    async def prepare(
        self,
        config: ProviderRuntimeConfig,
        context: AdContext,
        *,
        session_id: str,
        task_code: str,
        placement: str | None = None,
        required_format: str = "rewarded",
    ) -> ProviderPreparation:
        _ = context, task_code, required_format
        return ProviderPreparation(
            provider=self.code,
            provider_ref=session_id,
            public_config={
                "adapter": "adsgram",
                "format": "rewarded",
                "block_id": str(placement or config.public["reward_block_id"]),
                "debug": bool(context.test_mode),
            },
        )

    async def verify_callback(
        self,
        config: ProviderRuntimeConfig,
        payload: dict[str, Any],
        *,
        session_id: str,
    ) -> ProviderVerification:
        _ = config
        # AdsGram Rewarded SDK разрешает reward после resolved show(). Это
        # LEVEL C: завершение SDK + серверное доказательство EFHC ad_session и владельца.
        completed = bool(payload.get("done", False)) and not bool(payload.get("error", False))
        event_id = str(payload.get("event_id") or f"adsgram-client:{session_id}")
        return ProviderVerification(
            provider=self.code,
            provider_event_id=event_id,
            verified=completed,
            completed=completed,
            valued=None,
            metadata={"source": "sdk_completion"},
        )

    def normalize_error(self, error: object) -> str:
        return str(normalized_provider_error(error))
