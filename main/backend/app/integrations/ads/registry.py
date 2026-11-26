"""Registry реальных adapter instances для backend AdManager."""

from __future__ import annotations

from typing import Final

from app.integrations.ads.adexium import AdexiumAdapter
from app.integrations.ads.admaven import AdMavenAdapter
from app.integrations.ads.adsgram import AdsGramAdapter
from app.integrations.ads.base import ProviderAdapter
from app.integrations.ads.builtin_timer import BuiltinTimerAdapter
from app.integrations.ads.monetag import MonetagAdapter
from app.integrations.ads.mybid import MyBidAdapter
from app.integrations.ads.richads import RichAdsAdapter
from app.integrations.ads.tads import TadsAdapter

ADAPTERS: Final[dict[str, ProviderAdapter]] = {
    "adsgram": AdsGramAdapter(),
    "monetag": MonetagAdapter(),
    "richads": RichAdsAdapter(),
    "admaven": AdMavenAdapter(),
    "adexium": AdexiumAdapter(),
    "tads": TadsAdapter(),
    "mybid": MyBidAdapter(),
    "builtin_timer": BuiltinTimerAdapter(),
}


def get_provider_adapter(code: str) -> ProviderAdapter:
    key = str(code or "").strip().lower()
    try:
        return ADAPTERS[key]
    except KeyError as exc:
        raise ValueError("UNKNOWN_PROVIDER") from exc
