# ======================================================================
# КАНОН MEMO для входящих платежей TON/USDT/EFHC.
#
# Canonical provider-neutral форматы:
# 1) Прямой deposit: EFHC:GID:<global_id_10>
# 2) Историческая маршрутизация пакета: BUY:EFHC:<qty>:GID:<global_id_10>[:OID:<id>]
#    ВАЖНО: qty из этого MEMO не является settlement/reward authority.
#    Автодоставка package разрешена только через PaymentIntent reconciliation.
# 3) NFT-заявка: SKU:NFT_VIP|Q:<qty>|GID:<global_id_10>
#
# Telegram compatibility форматы допустимы, пока financial
# writes остаются legacy-authoritative:
# - Legacy deposit формат: EFHC:<global_id> / EFHC<global_id>
# - Legacy purchase формат: BUY:EFHC:<qty>:TG:<global_id>[:OID:<id>]
# - Legacy package формат: SKU:EFHC|Q:<qty>|TG:<global_id>
# - Legacy NFT формат: SKU:NFT_VIP|Q:<qty>|TG:<global_id>
# ======================================================================

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_GLOBAL_ID_RE = r"(?P<global_id>[0-9]{10})"
_RE_DEPOSIT_GLOBAL = re.compile(rf"^EFHC:GID:{_GLOBAL_ID_RE}$")
_RE_DEPOSIT = re.compile(r"^EFHC:(?P<tg_id>\d{3,20})$")
_RE_DEPOSIT_LEGACY = re.compile(r"^EFHC(?P<tg_id>\d{1,20})$")

_RE_BUY_PACK_GLOBAL = re.compile(
    rf"^BUY:EFHC:(?P<qty>[1-9]\d*):GID:{_GLOBAL_ID_RE}"
    r"(?::OID:(?P<oid>[A-Za-z0-9\-_]{1,64}))?$"
)
_RE_BUY_PACK = re.compile(
    r"^BUY:EFHC:(?P<qty>[1-9]\d*):TG:(?P<tg_id>\d{3,20})"
    r"(?::OID:(?P<oid>[A-Za-z0-9\-_]{1,64}))?$"
)
_RE_SKU_EFHC_GLOBAL = re.compile(
    rf"^SKU:EFHC\|Q:(?P<qty>\d{{1,12}})\|GID:{_GLOBAL_ID_RE}$"
)
_RE_SKU_NFT_GLOBAL = re.compile(
    rf"^SKU:NFT_VIP\|Q:(?P<qty>\d{{1,12}})\|GID:{_GLOBAL_ID_RE}$"
)
_RE_SKU_EFHC_LEGACY = re.compile(
    r"^SKU:EFHC\|Q:(?P<qty>\d{1,12})\|TG:(?P<tg_id>\d{1,20})$"
)
_RE_SKU_NFT_LEGACY = re.compile(
    r"^SKU:NFT_VIP\|Q:(?P<qty>\d{1,12})\|TG:(?P<tg_id>\d{1,20})$"
)


@dataclass(frozen=True)
class MemoDepositEFHC:
    """Direct EFHC deposit memo через Telegram compatibility."""

    tg_id: int
    legacy: bool = False


@dataclass(frozen=True)
class MemoDepositEFHCGlobal:
    """Provider-neutral direct deposit memo."""

    global_id: str


@dataclass(frozen=True)
class MemoBuyEFHCPack:
    """Historical package routing через Telegram compatibility."""

    tg_id: int
    qty_efhc: int
    order_id: str | None = None
    legacy: bool = False


@dataclass(frozen=True)
class MemoBuyEFHCPackGlobal:
    """Historical provider-neutral package routing memo."""

    global_id: str
    qty_efhc: int
    order_id: str | None = None


@dataclass(frozen=True)
class MemoSkuNFT:
    """Legacy Telegram NFT SKU memo. Delivery remains manual only."""

    tg_id: int
    qty: int
    legacy: bool = True


@dataclass(frozen=True)
class MemoSkuNFTGlobal:
    """Provider-neutral NFT SKU memo. Delivery remains manual only."""

    global_id: str
    qty: int


MemoParsed = (
    MemoDepositEFHC
    | MemoDepositEFHCGlobal
    | MemoBuyEFHCPack
    | MemoBuyEFHCPackGlobal
    | MemoSkuNFT
    | MemoSkuNFTGlobal
)
WatcherMemoKind = Literal[
    "simple_efhc",
    "sku_efhc",
    "sku_nft",
    "bad",
]


def _validated_global_id(value: str) -> str:
    text_value = str(value)
    if (
        len(text_value) != 10
        or not text_value.isascii()
        or not text_value.isdecimal()
        or text_value == "0000000000"
    ):
        raise ValueError("global_id must be 10 ASCII digits")
    return text_value


def _global_id_text(value: str) -> str:
    return _validated_global_id(value)


def _parsed_global_id(match: re.Match[str]) -> str | None:
    try:
        return _validated_global_id(match.group("global_id"))
    except ValueError:
        return None


def build_deposit_global_memo(global_id: str) -> str:
    """Build provider-neutral direct deposit memo."""

    return f"EFHC:GID:{_global_id_text(global_id)}"


def build_buy_pack_global_memo(
    global_id: str,
    qty_efhc: int,
    order_id: str | None = None,
) -> str:
    """Build provider-neutral package purchase memo."""

    if qty_efhc < 1:
        raise ValueError("qty_efhc must be >= 1")
    base = f"BUY:EFHC:{qty_efhc}:GID:{_global_id_text(global_id)}"
    if order_id:
        return f"{base}:OID:{order_id}"
    return base


def build_deposit_memo(tg_id: int) -> str:
    """Build Telegram compatibility direct deposit memo."""

    if tg_id <= 0:
        raise ValueError("tg_id must be positive")
    return f"EFHC:{tg_id}"


def build_buy_pack_memo(
    tg_id: int,
    qty_efhc: int,
    order_id: str | None = None,
) -> str:
    """Build Telegram compatibility package purchase memo."""

    if tg_id <= 0:
        raise ValueError("tg_id must be positive")
    if qty_efhc < 1:
        raise ValueError("qty_efhc must be >= 1")
    base = f"BUY:EFHC:{qty_efhc}:TG:{tg_id}"
    if order_id:
        return f"{base}:OID:{order_id}"
    return base


def parse_memo(memo: str | None) -> MemoParsed | None:
    """Разобрать provider-neutral canon и Telegram compatibility."""

    if memo is None:
        return None
    text_value = memo.strip()

    match = _RE_DEPOSIT_GLOBAL.match(text_value)
    if match:
        global_id = _parsed_global_id(match)
        return (
            MemoDepositEFHCGlobal(global_id=global_id)
            if global_id is not None
            else None
        )

    match = _RE_DEPOSIT.match(text_value)
    if match:
        return MemoDepositEFHC(tg_id=int(match.group("tg_id")))

    match = _RE_DEPOSIT_LEGACY.match(text_value)
    if match:
        return MemoDepositEFHC(
            tg_id=int(match.group("tg_id")),
            legacy=True,
        )

    match = _RE_BUY_PACK_GLOBAL.match(text_value)
    if match:
        global_id = _parsed_global_id(match)
        if global_id is None:
            return None
        return MemoBuyEFHCPackGlobal(
            global_id=global_id,
            qty_efhc=int(match.group("qty")),
            order_id=match.group("oid"),
        )

    match = _RE_BUY_PACK.match(text_value)
    if match:
        return MemoBuyEFHCPack(
            tg_id=int(match.group("tg_id")),
            qty_efhc=int(match.group("qty")),
            order_id=match.group("oid"),
        )

    match = _RE_SKU_EFHC_GLOBAL.match(text_value)
    if match:
        global_id = _parsed_global_id(match)
        if global_id is None:
            return None
        return MemoBuyEFHCPackGlobal(
            global_id=global_id,
            qty_efhc=int(match.group("qty")),
        )

    match = _RE_SKU_EFHC_LEGACY.match(text_value)
    if match:
        return MemoBuyEFHCPack(
            tg_id=int(match.group("tg_id")),
            qty_efhc=int(match.group("qty")),
            legacy=True,
        )

    match = _RE_SKU_NFT_GLOBAL.match(text_value)
    if match:
        global_id = _parsed_global_id(match)
        if global_id is None:
            return None
        return MemoSkuNFTGlobal(
            global_id=global_id,
            qty=int(match.group("qty")),
        )

    match = _RE_SKU_NFT_LEGACY.match(text_value)
    if match:
        return MemoSkuNFT(
            tg_id=int(match.group("tg_id")),
            qty=int(match.group("qty")),
        )

    return None


def parse_memo_for_watcher(
    memo: str | None,
) -> tuple[WatcherMemoKind, dict[str, int | str]]:
    """Watcher adapter over the memo SSOT parser."""

    parsed = parse_memo(memo)
    if isinstance(parsed, MemoDepositEFHCGlobal):
        return "simple_efhc", {"global_id": parsed.global_id}
    if isinstance(parsed, MemoDepositEFHC):
        return "simple_efhc", {"tg_id": parsed.tg_id}
    if isinstance(parsed, MemoBuyEFHCPackGlobal):
        return "sku_efhc", {
            "global_id": parsed.global_id,
            "qty": parsed.qty_efhc,
        }
    if isinstance(parsed, MemoBuyEFHCPack):
        return "sku_efhc", {
            "tg_id": parsed.tg_id,
            "qty": parsed.qty_efhc,
        }
    if isinstance(parsed, MemoSkuNFTGlobal):
        return "sku_nft", {
            "global_id": parsed.global_id,
            "qty": parsed.qty,
        }
    if isinstance(parsed, MemoSkuNFT):
        return "sku_nft", {
            "tg_id": parsed.tg_id,
            "qty": parsed.qty,
        }
    return "bad", {}
