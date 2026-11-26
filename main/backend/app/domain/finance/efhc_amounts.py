"""Единая exact D8 граница EFHC: валидация без округления и потери atomic\
 units."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

EFHC_DECIMALS = 8
EFHC_QUANTUM = Decimal("0.00000001")


def exact_efhc_d8(value: Any) -> Decimal:
    """Принять конечное число с scale <= 8, вернуть ровно D8.

    Даже лишние нулевые дробные знаки на входе отклоняются. Контекст
    локальный: NUMERIC(30,8) не теряет последние units при precision=28.
    """
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("EFHC_AMOUNT_INVALID") from exc
    if not amount.is_finite():
        raise ValueError("EFHC_AMOUNT_INVALID")
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -EFHC_DECIMALS:
        raise ValueError("EFHC_AMOUNT_PRECISION_INVALID")
    with localcontext() as ctx:
        ctx.prec = max(30, len(amount.as_tuple().digits) + EFHC_DECIMALS)
        try:
            return amount.quantize(EFHC_QUANTUM)
        except InvalidOperation as exc:
            raise ValueError("EFHC_AMOUNT_INVALID") from exc


def efhc_from_atomic(value: int | str) -> Decimal:
    """Atomic integer / 10^8 без float и зависимости от Decimal context."""
    text = str(value).strip()
    if not text or not text.lstrip("-").isdigit():
        raise ValueError("EFHC_AMOUNT_ATOMIC_INVALID")
    atomic = int(text)
    digits = tuple(int(digit) for digit in str(abs(atomic)))
    return Decimal((int(atomic < 0), digits, -EFHC_DECIMALS))


def efhc_to_atomic(value: Any) -> int:
    amount = exact_efhc_d8(value)
    parts = amount.as_tuple()
    atomic = int("".join(str(digit) for digit in parts.digits))
    return -atomic if parts.sign else atomic
