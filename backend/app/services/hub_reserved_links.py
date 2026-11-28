"""OWNER 0559: immutable HUB identity/order; mutable destination and visibility."""
from __future__ import annotations

from collections.abc import Mapping

RESERVED_HUB_LINKS: dict[str, tuple[str, int]] = {
    "efhc_buy": ("Магазин", 10),
    "vip_getgems": ("EFHC VIP NFT", 20),
    "efhc_ceo": ("CEO EFHC", 30),
    "efhc_admin": ("Админ", 40),
}


def hub_sort_key(link: object) -> tuple[int, int, int]:
    code = str(getattr(link, "code", ""))
    reserved = RESERVED_HUB_LINKS.get(code)
    if reserved is not None:
        return (0, reserved[1], int(getattr(link, "id", 0)))
    return (1, int(getattr(link, "sort_order", 100)), int(getattr(link, "id", 0)))


def is_reserved(code: str) -> bool:
    return str(code or "") in RESERVED_HUB_LINKS
