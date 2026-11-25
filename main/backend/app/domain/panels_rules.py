"""Чистые D8-правила Панелей, не зависящие от БД.

Прямой канон владельца от 2026-08-20:
- цена активации одной Панели = 100 EFHC;
- оплата EFHCb -> EFHCm;
- ручная защитная деактивация использует агрегатный kWh-алгоритм:
  U=min(G,A), R=G-U, NET=100-R;
- реализованная часть уменьшает возврат сначала по EFHCb, затем по EFHCm;
- R > 100 является аномалией и не создаёт долг.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.standards.finance_rules import SpendBreakdown, d8

PANEL_PRICE_D8 = d8("100")
PROTECTIVELY_VOIDED_META_KEY = "protectively_voided"


@dataclass(frozen=True)
class ProtectiveVoidAmounts:
    """D8-результат аннулирования генерации одной Панели."""

    generated_kwh: Decimal
    available_kwh_before: Decimal
    unused_kwh: Decimal
    realized_kwh: Decimal
    net_refund_efhc: Decimal


def calculate_protective_void_amounts(
    *,
    generated_kwh: Decimal,
    available_kwh: Decimal,
) -> ProtectiveVoidAmounts:
    """Рассчитать U/R/NET по утверждённому агрегатному kWh-алгоритму."""

    generated = d8(generated_kwh)
    available = d8(available_kwh)
    if generated < Decimal("0") or available < Decimal("0"):
        raise ValueError("PANEL_PROTECTIVE_NEGATIVE_INPUT")

    unused = d8(min(generated, available))
    realized = d8(generated - unused)
    if realized < Decimal("0") or realized > PANEL_PRICE_D8:
        raise ValueError("PANEL_PROTECTIVE_REALIZED_OUT_OF_RANGE")

    return ProtectiveVoidAmounts(
        generated_kwh=generated,
        available_kwh_before=available,
        unused_kwh=unused,
        realized_kwh=realized,
        net_refund_efhc=d8(PANEL_PRICE_D8 - realized),
    )


def calculate_protective_refund_split(
    *,
    original_bonus: Decimal,
    original_main: Decimal,
    realized_offset: Decimal,
) -> SpendBreakdown:
    """Уменьшить gross refund 100: сначала EFHCb, затем EFHCm."""

    bonus = d8(original_bonus)
    main = d8(original_main)
    realized = d8(realized_offset)
    if bonus < 0 or main < 0 or d8(bonus + main) != PANEL_PRICE_D8:
        raise ValueError("PANEL_PAYMENT_SPLIT_INVALID")
    if realized < 0 or realized > PANEL_PRICE_D8:
        raise ValueError("PANEL_PROTECTIVE_REALIZED_OUT_OF_RANGE")

    offset_bonus = d8(min(bonus, realized))
    offset_main = d8(realized - offset_bonus)
    refund_bonus = d8(bonus - offset_bonus)
    refund_main = d8(main - offset_main)
    if refund_bonus < 0 or refund_main < 0:
        raise ValueError("PANEL_PROTECTIVE_REFUND_NEGATIVE")
    if d8(refund_bonus + refund_main) != d8(PANEL_PRICE_D8 - realized):
        raise ValueError("PANEL_PROTECTIVE_REFUND_MISMATCH")
    return SpendBreakdown(
        bonus_part=refund_bonus,
        main_part=refund_main,
    )


def allocate_panel_payment_splits(
    *,
    panel_ids: list[int],
    spent_bonus: Decimal,
    spent_main: Decimal,
) -> dict[int, SpendBreakdown]:
    """Разложить batch-платёж на Panel ID в порядке создания.

    Канон оплаты всего batch — EFHCb -> EFHCm. Поэтому та же последовательность
    применяется к Панелям в ``panels_created_ids``: каждая цена 100 EFHC.
    """

    ids = [int(value) for value in panel_ids]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("PANEL_PAYMENT_IDS_INVALID")

    bonus_left = d8(spent_bonus)
    main_left = d8(spent_main)
    expected = d8(PANEL_PRICE_D8 * Decimal(len(ids)))
    if bonus_left < 0 or main_left < 0 or d8(bonus_left + main_left) != expected:
        raise ValueError("PANEL_PAYMENT_TOTAL_MISMATCH")

    result: dict[int, SpendBreakdown] = {}
    for panel_id in ids:
        bonus_part = d8(min(bonus_left, PANEL_PRICE_D8))
        main_part = d8(PANEL_PRICE_D8 - bonus_part)
        if main_part > main_left:
            raise ValueError("PANEL_PAYMENT_ALLOCATION_MISMATCH")
        result[panel_id] = SpendBreakdown(
            bonus_part=bonus_part,
            main_part=main_part,
        )
        bonus_left = d8(bonus_left - bonus_part)
        main_left = d8(main_left - main_part)

    if bonus_left != d8("0") or main_left != d8("0"):
        raise ValueError("PANEL_PAYMENT_ALLOCATION_REMAINDER")
    return result


__all__ = [
    "PANEL_PRICE_D8",
    "PROTECTIVELY_VOIDED_META_KEY",
    "ProtectiveVoidAmounts",
    "allocate_panel_payment_splits",
    "calculate_protective_refund_split",
    "calculate_protective_void_amounts",
]
