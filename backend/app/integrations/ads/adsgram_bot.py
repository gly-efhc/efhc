"""AdsGram Bot API adapter на реальной Telegram provider boundary.

Этот adapter показывает provider-native рекламное сообщение в боте, но сам
не выдаёт EFHCb. EFHC rewarded accounting остаётся только в server-owned
AdManager/Task flow.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from app.core.config_core import get_settings
from app.services.ads.config_service import ProviderRuntimeConfig

settings = get_settings()


@dataclass(frozen=True, slots=True)
class AdsGramBotCreative:
    text_html: str
    click_url: str | None
    button_name: str | None
    image_url: str | None
    button_reward_name: str | None
    reward_url: str | None


async def fetch_adsgram_bot_ad(
    config: ProviderRuntimeConfig,
    *,
    provider_tg_id: int,
    language: str,
) -> AdsGramBotCreative | None:
    block_id = str(config.public.get("bot_block_id") or "").strip()
    token = str(config.secret.get("bot_token") or "").strip()
    if not config.enabled or not config.bot_enabled or not block_id or not token:
        return None
    # AdsGram требует числовую часть идентификатора без префикса bot-.
    numeric_block = block_id.removeprefix("bot-").strip()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(float(settings.ADS_PROVIDER_TIMEOUT_SEC))
    ) as client:
        response = await client.get(
            "https://api.adsgram.ai/advbot",
            params={
                "tgid": int(provider_tg_id),
                "blockid": numeric_block,
                "language": str(language or "en")[:16],
                "token": token,
            },
        )
        if response.status_code in {204, 404}:
            return None
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict) or not str(data.get("text_html") or "").strip():
        return None
    return AdsGramBotCreative(
        text_html=str(data["text_html"]),
        click_url=str(data.get("click_url") or "").strip() or None,
        button_name=str(data.get("button_name") or "").strip() or None,
        image_url=str(data.get("image_url") or "").strip() or None,
        button_reward_name=str(data.get("button_reward_name") or "").strip() or None,
        reward_url=str(data.get("reward_url") or "").strip() or None,
    )


__all__ = ["AdsGramBotCreative", "fetch_adsgram_bot_ad"]
