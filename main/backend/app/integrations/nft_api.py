# backend/app/integrations/nft_api.py
# ======================================================================
# EFHC Bot — интеграция с NFT (TON): проверка наличия NFT в коллекции
# ----------------------------------------------------------------------
# Что даёт модуль:
# • Унифицированные функции:
# wallet_has_nft_in_collection(wallet, collection) -> bool
# fetch_wallet_nfts_in_collection(wallet, collection, limit=100) ->
# List[NFTItem]
# batch_wallets_has_nft_in_collection(wallets, collection)
# -> Dict[wallet, bool]
# • Провайдеры и fallback:
# 1) TonAPI (https://tonapi.io/v2) — основной
# 2) Getgems API (https://api.getgems.io) — резервный
# • ИИ-устойчивость:
# — асинхронные HTTP-вызовы с таймаутами
# — экспоненциальные ретраи с джиттером
# — мягкая нормализация разных структур ответов
#
# Важно:
# • Этот модуль только ЧИТАЕТ внешние API.
#   Никакой бизнес-логики тут нет.
# • Вся бизнес-логика VIP/статусов — в services/nft_check_service.py.
# • Адрес/коллекция сравниваются как строки без пробелов (нормализуем).
# ======================================================================

from __future__ import annotations

import asyncio
import json
import os
import secrets
from dataclasses import dataclass
from typing import Any, cast

try:
    import httpx  # асинхронный HTTP-клиент
except Exception:  # pragma: no cover
    httpx = cast(Any, None)

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.integrations.ton_api_urls import ton_api_base_url

logger = get_logger(__name__)

_SYSRAND = secrets.SystemRandom()
settings = get_settings()

# --- Конфигурация ---

TON_API_URL = ton_api_base_url(
    getattr(settings, "TON_API_BASE_URL", "https://tonapi.io")
)
TON_API_KEY: str = getattr(
    settings, "TON_API_KEY", ""
) or os.environ.get("TON_API_KEY", "")

GETGEMS_API_URL: str = (
    getattr(settings, "GETGEMS_API_URL", "") or "https://api.getgems.io"
)

NETWORK_TIMEOUT_SEC: float = float(
    getattr(settings, "NETWORK_TIMEOUT_SEC", 20) or 20
)

# Можно заранее задать адрес коллекции в конфиге.
DEFAULT_NFT_COLLECTION: str | None = getattr(
    settings, "TON_NFT_COLLECTION", None
) or getattr(settings, "GETGEMS_COLLECTION", None)


# --- Модель ответа ---


@dataclass
class NFTItem:
    """Унифицированное описание NFT (минимально нужные поля)."""

    address: str  # адрес NFT
    collection: str  # адрес коллекции
    owner: str | None  # текущий владелец (если доступно)
    metadata: dict[str, Any]  # любые поля (name, attributes и т.д.)


# --- Утилиты и backoff ---


def _norm_addr(addr: str | None) -> str:
    """Нормализация адреса: trim, без конвертации форматов."""
    if not addr:
        return ""
    return addr.strip()


async def _with_backoff(
    coro_factory,
    *,
    tries: int = 3,
    base: float = 0.4,
    factor: float = 2.0,
    max_sleep: float = 5.0,
):
    """
    Выполняет coro_factory() с экспоненциальным бэкоффом и джиттером.
    coro_factory — функция без аргументов, возвращающая coroutine.
    """
    attempt = 0
    while True:
        try:
            return await coro_factory()
        except Exception as e:
            attempt += 1
            if attempt >= tries:
                raise
            delay = min(max_sleep, base * (factor ** (attempt - 1)))
            delay = delay * (0.7 + _SYSRAND.random() * 0.6)  # ±30%
            logger.warning(
                "nft integration: attempt %s failed: %s; sleep %.2fs",
                attempt,
                e,
                delay,
            )
            await asyncio.sleep(delay)


async def _http_get_json(
    base_url: str,
    path: str,
    *,
    headers: dict[str, str],
    params: dict[str, Any],
) -> dict[str, Any]:
    """GET JSON с таймаутом. Возвращаем dict (может быть пустым)."""
    if httpx is None:  # pragma: no cover
        raise RuntimeError("httpx is required for network calls")
    url = f"{base_url.rstrip('/')}{path}"
    timeout = httpx.Timeout(
        NETWORK_TIMEOUT_SEC,
        read=NETWORK_TIMEOUT_SEC,
    )
    async with httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
    ) as client:
        r = await client.get(url, params=params, follow_redirects=True)
        r.raise_for_status()
        try:
            return cast(dict[str, Any], r.json())
        except Exception:
            return cast(dict[str, Any], json.loads(r.text or "{}"))


# --- TonAPI (primary) ---


def _tonapi_headers() -> dict[str, str]:
    """HTTP headers для TonAPI."""
    h = {"Accept": "application/json"}
    if TON_API_KEY:
        h["Authorization"] = f"Bearer {TON_API_KEY}"
    return h


async def _tonapi_list_wallet_nfts(
    wallet: str,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    TonAPI: список NFT кошелька.
    Варианты путей (по состоянию API): /nft/items?owner=<addr>
                                      или /accounts/{addr}/nfts
    Попробуем наиболее распространённый:
    /blockchain/accounts/{addr}/nfts
    """
    path = f"/blockchain/accounts/{wallet}/nfts"
    params = {"limit": int(max(1, min(limit, 1000)))}
    data = await _with_backoff(
        lambda: _http_get_json(
            TON_API_URL,
            path,
            headers=_tonapi_headers(),
            params=params,
        )
    )
    items = (
        data.get("nft_items")
        or data.get("items")
        or data.get("nfts")
        or []
    )
    if not isinstance(items, list):
        items = []
    return items


def _tonapi_normalize_items(
    raw_items: list[dict[str, Any]],
) -> list[NFTItem]:
    """Нормализуем TonAPI объекты к NFTItem."""
    out: list[NFTItem] = []
    for it in raw_items:
        addr = _norm_addr(
            it.get("address")
            or it.get("nft_item_address")
            or it.get("id")
        )
        coll = _norm_addr(
            it.get("collection_address")
            or (it.get("collection") or {}).get("address")
        )
        ownr = _norm_addr(
            it.get("owner") or (it.get("owner") or {}).get("address")
        )
        meta = it.get("metadata") or it.get("content") or {}
        out.append(
            NFTItem(
                address=addr,
                collection=coll,
                owner=ownr,
                metadata=meta if isinstance(meta, dict) else {},
            )
        )
    return out


# --- Getgems (fallback) ---


def _getgems_headers() -> dict[str, str]:
    """HTTP headers для Getgems."""
    return {"Accept": "application/json"}


async def _getgems_list_wallet_nfts(
    wallet: str,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    Getgems API: список NFT кошелька.
    Часто встречается путь вида: /nft/account/{addr}?limit=...
    """
    path = f"/nft/account/{wallet}"
    params = {"limit": int(max(1, min(limit, 1000)))}
    data = await _with_backoff(
        lambda: _http_get_json(
            GETGEMS_API_URL,
            path,
            headers=_getgems_headers(),
            params=params,
        )
    )
    items = (
        data.get("nft_items")
        or data.get("items")
        or data.get("nfts")
        or data.get("result")
        or []
    )
    if not isinstance(items, list):
        items = []
    return items


def _getgems_normalize_items(
    raw_items: list[dict[str, Any]],
) -> list[NFTItem]:
    """Нормализуем Getgems объекты к NFTItem."""
    out: list[NFTItem] = []
    for it in raw_items:
        addr = _norm_addr(
            it.get("address") or it.get("nft_address") or it.get("id")
        )
        coll = _norm_addr(
            it.get("collection") or it.get("collection_address")
        )
        ownr = _norm_addr(
            it.get("owner") or (it.get("owner") or {}).get("address")
        )
        meta = it.get("metadata") or it.get("meta") or {}
        out.append(
            NFTItem(
                address=addr,
                collection=coll,
                owner=ownr,
                metadata=meta if isinstance(meta, dict) else {},
            )
        )
    return out


# --- Агрегатор ---


async def fetch_wallet_nfts_in_collection(
    wallet: str,
    collection: str | None,
    *,
    limit: int = 200,
) -> list[NFTItem]:
    """
    Вернуть NFT пользователя, отфильтрованные по коллекции,
    если она задана.
    Алгоритм:
      1) TonAPI: /blockchain/accounts/{wallet}/nfts → normalize → filter
      2) Если TonAPI упал/дал мало, пробуем Getgems
      3) Объединяем, дедуп по адресу NFT
    """
    wallet = _norm_addr(wallet)
    collection = _norm_addr(collection or DEFAULT_NFT_COLLECTION)

    items_all: list[NFTItem] = []

    # Primary: TonAPI
    try:
        raw = await _tonapi_list_wallet_nfts(wallet, limit=limit)
        items = _tonapi_normalize_items(raw)
        if collection:
            items = [
                it
                for it in items
                if _norm_addr(it.collection) == collection
            ]
        items_all.extend(items)
    except Exception as e:
        logger.warning("nft tonapi wallet_nfts failed: %s", e)

    # Fallback: Getgems — если TonAPI ничего не дал
    need_fallback = len(items_all) < 1
    if need_fallback:
        try:
            raw2 = await _getgems_list_wallet_nfts(wallet, limit=limit)
            items2 = _getgems_normalize_items(raw2)
            if collection:
                items2 = [
                    it
                    for it in items2
                    if _norm_addr(it.collection) == collection
                ]
            items_all.extend(items2)
        except Exception as e:
            logger.warning("nft getgems wallet_nfts failed: %s", e)

    # Дедуп по адресу NFT
    dedup: dict[str, NFTItem] = {}
    for it in items_all:
        if it.address:
            dedup[it.address] = it
    result = list(dedup.values())
    logger.info(
        "nft integration: wallet=%s, collection=%s -> %s item(s)",
        wallet,
        collection or "-",
        len(result),
    )
    return result


async def wallet_has_nft_in_collection(
    wallet: str,
    collection: str | None = None,
) -> bool:
    """
    True, если у кошелька есть хотя бы один NFT из коллекции.
    """
    items = await fetch_wallet_nfts_in_collection(
        wallet,
        collection,
        limit=200,
    )
    return len(items) > 0


async def batch_wallets_has_nft_in_collection(
    wallets: list[str],
    collection: str | None = None,
) -> dict[str, bool]:
    """
    Пакетная проверка нескольких кошельков.
    Выполняется последовательно (чтобы не перегружать API).
    оптимизировать на батчи с контролем параллелизма.
    """
    out: dict[str, bool] = {}
    for w in wallets:
        try:
            out[_norm_addr(w)] = await wallet_has_nft_in_collection(
                w,
                collection,
            )
        except Exception as e:
            logger.warning("nft batch check failed for %s: %s", w, e)
            out[_norm_addr(w)] = False
    return out
