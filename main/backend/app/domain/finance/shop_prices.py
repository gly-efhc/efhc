"""Каноническая D2-граница ручной внешней цены Shop.

D2 здесь относится только к Admin catalog price TON/USDT. Техническое
исполнение внешнего asset остаётся в native atomic precision (TON 9,
USDT 6) и выполняется через ``external_amounts``.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Final

SHOP_PRICE_QUANTUM: Final = Decimal("0.01")
SHOP_PRICE_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "SHOP_PRICE_INVALID",
        "SHOP_PRICE_MUST_NOT_BE_NEGATIVE",
        "SHOP_PRICE_D2_REQUIRED",
    }
)
SHOP_PRICE_LEGACY_PRECISION_INVALID: Final = (
    "SHOP_PRICE_LEGACY_PRECISION_INVALID"
)


def normalize_shop_external_price_d2(
    value: Decimal | str | int,
) -> Decimal:
    """Проверить Admin Shop price и вернуть каноническое D2-представление.

    Значения с precision, которую нельзя представить ровно в D2,
    отклоняются. Silent ROUND_DOWN/ROUND_HALF_* для Admin price запрещён.
    Ноль разрешён как сохранённая disabled-конфигурация; checkout отдельно
    требует строго положительную цену.
    """
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("SHOP_PRICE_INVALID") from exc
    if not amount.is_finite():
        raise ValueError("SHOP_PRICE_INVALID")
    if amount < 0:
        raise ValueError("SHOP_PRICE_MUST_NOT_BE_NEGATIVE")
    try:
        normalized = amount.quantize(SHOP_PRICE_QUANTUM)
    except InvalidOperation as exc:
        raise ValueError("SHOP_PRICE_INVALID") from exc
    if normalized != amount:
        raise ValueError("SHOP_PRICE_D2_REQUIRED")
    return normalized


def shop_external_price_diagnostic(value: object) -> str | None:
    """Вернуть fail-closed diagnostic для legacy catalog price."""
    if value is None or str(value).strip() == "":
        return None
    try:
        normalize_shop_external_price_d2(str(value))
    except ValueError as exc:
        if str(exc) == "SHOP_PRICE_D2_REQUIRED":
            return SHOP_PRICE_LEGACY_PRECISION_INVALID
        return str(exc)
    return None


__all__ = [
    "SHOP_PRICE_ERROR_CODES",
    "SHOP_PRICE_LEGACY_PRECISION_INVALID",
    "SHOP_PRICE_QUANTUM",
    "normalize_shop_external_price_d2",
    "shop_external_price_diagnostic",
]
