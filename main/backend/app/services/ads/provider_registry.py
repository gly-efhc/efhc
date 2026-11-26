"""Расширяемый реестр рекламных провайдеров EFHC.

Tasks и публичные страницы не знают provider-specific SDK/API. Реестр хранит
только описание capability/config schema; runtime adapter выбирает AdManager.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    code: str
    display_name: str
    capabilities: frozenset[str]
    public_fields: tuple[str, ...]
    secret_fields: tuple[str, ...]
    env_fields: dict[str, str]
    verification_level: str
    verification_mode: str
    official_contract_status: str
    note: str
    required_public_fields: tuple[str, ...] = ()
    required_secret_fields: tuple[str, ...] = ()

    def schema(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for name in self.public_fields:
            rows.append({
                "name": name,
                "secret": False,  # nosec B105
                "required": name in self.required_public_fields,
            })
        for name in self.secret_fields:
            rows.append({
                "name": name,
                "secret": True,  # nosec B105
                "required": name in self.required_secret_fields,
            })
        return rows


PROVIDER_DESCRIPTORS: Final[dict[str, ProviderDescriptor]] = {
    "adsgram": ProviderDescriptor(
        code="adsgram",
        display_name="AdsGram",
        capabilities=frozenset({"miniapp", "bot", "rewarded", "interstitial"}),
        public_fields=("reward_block_id", "bot_block_id"),
        secret_fields=("bot_token",),
        env_fields={
            "enabled": "ADSGRAM_ENABLED",
            "reward_block_id": "ADSGRAM_REWARD_BLOCK_ID",
            "bot_enabled": "ADSGRAM_BOT_ENABLED",
            "bot_block_id": "ADSGRAM_BOT_BLOCK_ID",
            "bot_token": "ADSGRAM_BOT_TOKEN",  # nosec B105
        },
        verification_level="C",
        verification_mode="sdk_completion_plus_session",
        required_public_fields=("reward_block_id",),
        required_secret_fields=(),
        official_contract_status="VERIFIED_2026_08",
        note="Mini App Reward/Interstitial через официальный AdsGram SDK; bot API отдельно.",
    ),
    "monetag": ProviderDescriptor(
        code="monetag",
        display_name="Monetag",
        capabilities=frozenset({"miniapp", "rewarded", "postback", "preload", "revenue"}),
        public_fields=("rewarded_zone_id", "sdk_src"),
        secret_fields=("postback_secret",),
        env_fields={
            "enabled": "MONETAG_ENABLED",
            "rewarded_zone_id": "MONETAG_REWARDED_ZONE_ID",
            "postback_secret": "MONETAG_POSTBACK_SECRET",  # nosec B105
            "sdk_src": "MONETAG_SDK_SRC",
        },
        verification_level="B",
        verification_mode="server_postback_ymid",
        required_public_fields=("rewarded_zone_id", "sdk_src"),
        required_secret_fields=("postback_secret",),
        official_contract_status="VERIFIED_2026_08",
        note="Rewarded Interstitial/Popup; ymid связывает SDK call с server postback.",
    ),
    "richads": ProviderDescriptor(
        code="richads",
        display_name="RichAds",
        capabilities=frozenset({"miniapp", "rewarded", "server_bid", "revenue"}),
        public_fields=("ssp_id", "publisher_id", "widget_id", "bid_floor"),
        secret_fields=(),
        env_fields={
            "enabled": "RICHADS_ENABLED",
            "ssp_id": "RICHADS_SSP_ID",
            "publisher_id": "RICHADS_PUBLISHER_ID",
            "widget_id": "RICHADS_WIDGET_ID",
            "bid_floor": "RICHADS_BID_FLOOR",
        },
        verification_level="C",
        verification_mode="server_bid_plus_client_completion",
        required_public_fields=("ssp_id", "publisher_id"),
        required_secret_fields=(),
        official_contract_status="VERIFIED_2026_08",
        note="Telegram SSP interstitial video; motivated=true для rewarded flow.",
    ),
    "admaven": ProviderDescriptor(
        code="admaven",
        display_name="AdMaven",
        capabilities=frozenset({"miniapp", "rewarded", "postback"}),
        public_fields=("script_src",),
        secret_fields=("api_key", "postback_secret"),
        env_fields={
            "enabled": "ADMAVEN_ENABLED",
            "api_key": "ADMAVEN_API_KEY",
            "postback_secret": "ADMAVEN_POSTBACK_SECRET",  # nosec B105
            "script_src": "ADMAVEN_SCRIPT_SRC",
        },
        verification_level="B",
        verification_mode="server_postback_click_id",
        required_public_fields=("script_src",),
        required_secret_fields=("postback_secret",),
        official_contract_status="VERIFIED_PARTIAL_2026_08",
        note="TMA task integration; CLICK_ID/postback correlation. Account-specific script is runtime config.",
    ),
    "adexium": ProviderDescriptor(
        code="adexium",
        display_name="Adexium",
        capabilities=frozenset({"miniapp", "rewarded", "interstitial", "provider_check"}),
        public_fields=("widget_id", "sdk_src"),
        secret_fields=(),
        env_fields={
            "enabled": "ADEXIUM_ENABLED",
            "widget_id": "ADEXIUM_WIDGET_ID",
            "sdk_src": "ADEXIUM_SDK_SRC",
        },
        verification_level="C",
        verification_mode="sdk_completion_plus_server_task_check",
        required_public_fields=("widget_id", "sdk_src"),
        required_secret_fields=(),
        official_contract_status="VERIFIED_2026_08",
        note="Manual widget mode + adPlaybackCompleted; backend task/check повышает доверие.",
    ),
    "tads": ProviderDescriptor(
        code="tads",
        display_name="TADS",
        capabilities=frozenset({"miniapp", "rewarded"}),
        public_fields=("widget_id", "sdk_src"),
        secret_fields=(),
        env_fields={
            "enabled": "TADS_ENABLED",
            "widget_id": "TADS_WIDGET_ID",
            "sdk_src": "TADS_SDK_SRC",
        },
        verification_level="D",
        verification_mode="publisher_contract_required",
        required_public_fields=("widget_id", "sdk_src"),
        required_secret_fields=(),
        official_contract_status="CABINET_CONTRACT_REQUIRED",
        note="Rewarded publisher adapter подготовлен; точный SDK/callback задаётся после выдачи кабинетом.",
    ),
    "mybid": ProviderDescriptor(
        code="mybid",
        display_name="MyBid",
        capabilities=frozenset({"miniapp", "rewarded"}),
        public_fields=("widget_id", "sdk_src"),
        secret_fields=(),
        env_fields={
            "enabled": "MYBID_ENABLED",
            "widget_id": "MYBID_WIDGET_ID",
            "sdk_src": "MYBID_SDK_SRC",
        },
        verification_level="D",
        verification_mode="publisher_contract_required",
        required_public_fields=("widget_id", "sdk_src"),
        required_secret_fields=(),
        official_contract_status="CABINET_CONTRACT_REQUIRED",
        note="Rewarded Video capability подтверждена; точный runtime contract не выдумывается до кабинета.",
    ),
    "builtin_timer": ProviderDescriptor(
        code="builtin_timer",
        display_name="Технический таймер EFHC",
        capabilities=frozenset({"diagnostics"}),
        public_fields=("min_view_sec",),
        secret_fields=("secret",),
        env_fields={
            "enabled": "ADS_BUILTIN_TIMER_ENABLED",
            "secret": "ADS_BUILTIN_SECRET",  # nosec B105
            "min_view_sec": "ADS_BUILTIN_MIN_VIEW_SEC",
        },
        verification_level="D",
        verification_mode="dev_hmac_timer",
        required_public_fields=("min_view_sec",),
        required_secret_fields=("secret",),
        official_contract_status="DEV_CI_ONLY",
        note="Не рекламная сеть; запрещён в production mediation и production EFHCb reward.",
    ),
}

PRODUCTION_PROVIDER_CODES: Final[tuple[str, ...]] = (
    "monetag", "adsgram", "richads", "tads", "mybid", "admaven", "adexium"
)


def get_descriptor(code: str) -> ProviderDescriptor:
    key = str(code or "").strip().lower()
    try:
        return PROVIDER_DESCRIPTORS[key]
    except KeyError as exc:
        raise ValueError("UNKNOWN_PROVIDER") from exc
