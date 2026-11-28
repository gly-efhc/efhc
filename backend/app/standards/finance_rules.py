"""backend/app/standards/finance_rules.py

SSOT финансовых правил EFHC.

Канон:
- Любые траты/покупки: сначала BONUS, затем MAIN.
- Вывод (withdraw): только MAIN.

Этот модуль не зависит от SQLAlchemy и может
использоваться в unit-тестах.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

ZERO_D8 = Decimal("0.00000000")
EFHC_EXTERNAL_QUANTUM = Decimal("0.01")


def d8(x: Decimal | str) -> Decimal:
    q = Decimal(str(x)).quantize(
        Decimal("0.00000001"),
        rounding=ROUND_DOWN,
    )
    if q == Decimal("0E-8"):
        return ZERO_D8
    return q


def quantize_external_efhc_d2(x: Decimal | str) -> Decimal:
    """Внешний EFHC deposit/withdraw: D2, ROUND_DOWN; internal storage остаётся D8."""
    return Decimal(str(x)).quantize(
        EFHC_EXTERNAL_QUANTUM,
        rounding=ROUND_DOWN,
    )


@dataclass(frozen=True)
class SpendBreakdown:
    bonus_part: Decimal
    main_part: Decimal


def split_bonus_then_main(
    *,
    bonus_balance: Decimal,
    main_balance: Decimal,
    amount: Decimal,
) -> SpendBreakdown:
    """Канон: сначала BONUS, затем MAIN."""
    amt = d8(amount)
    if amt <= Decimal("0"):
        raise ValueError("Amount must be > 0")
    b = d8(bonus_balance)
    m = d8(main_balance)
    if b < Decimal("0") or m < Decimal("0"):
        raise ValueError("Balance must be >= 0")
    if d8(b + m) < amt:
        raise ValueError("Insufficient funds (bonus+main)")
    bonus_part = d8(min(b, amt))
    main_part = d8(amt - bonus_part)
    return SpendBreakdown(bonus_part=bonus_part, main_part=main_part)
