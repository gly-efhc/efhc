"""Канонический тип внешних TON/USDT сумм в native atomic units.

Этот модуль намеренно не импортирует EFHC ``d8``: TON и USDT являются
внешними payment rails и не относятся к внутренней D8-модели EFHC/kWh.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class ExternalAsset(StrEnum):
    TON = "TON"
    USDT = "USDT"


_ATOMIC_DECIMALS: dict[ExternalAsset, int] = {
    ExternalAsset.TON: 9,
    ExternalAsset.USDT: 6,
}


@dataclass(frozen=True)
class ExternalAmount:
    asset: ExternalAsset
    atomic: int
    decimals: int

    @property
    def display(self) -> Decimal:
        return Decimal(self.atomic) / (Decimal(10) ** self.decimals)

    @property
    def display_text(self) -> str:
        return format(self.display, f".{self.decimals}f")


def _asset(value: str | ExternalAsset) -> ExternalAsset:
    try:
        return ExternalAsset(str(value or "").strip().upper())
    except ValueError as exc:
        raise ValueError("ASSET_NOT_SUPPORTED") from exc


def atomic_decimals(asset: str | ExternalAsset) -> int:
    return _ATOMIC_DECIMALS[_asset(asset)]


def external_amount_from_atomic(
    asset: str | ExternalAsset,
    atomic: int | str,
    *,
    require_positive: bool = False,
) -> ExternalAmount:
    asset_v = _asset(asset)
    try:
        atomic_i = int(str(atomic).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("EXTERNAL_AMOUNT_ATOMIC_INVALID") from exc
    if atomic_i < 0 or (require_positive and atomic_i <= 0):
        raise ValueError("EXTERNAL_AMOUNT_MUST_BE_POSITIVE")
    return ExternalAmount(
        asset=asset_v,
        atomic=atomic_i,
        decimals=_ATOMIC_DECIMALS[asset_v],
    )


def external_amount_from_display(
    asset: str | ExternalAsset,
    value: Decimal | str | int,
    *,
    require_positive: bool = False,
) -> ExternalAmount:
    asset_v = _asset(asset)
    decimals = _ATOMIC_DECIMALS[asset_v]
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("EXTERNAL_AMOUNT_INVALID") from exc
    if not amount.is_finite():
        raise ValueError("EXTERNAL_AMOUNT_INVALID")
    scale = Decimal(10) ** decimals
    scaled = amount * scale
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError("EXTERNAL_AMOUNT_PRECISION_INVALID")
    return external_amount_from_atomic(
        asset_v,
        int(integral),
        require_positive=require_positive,
    )


__all__ = [
    "ExternalAmount",
    "ExternalAsset",
    "atomic_decimals",
    "external_amount_from_atomic",
    "external_amount_from_display",
]
