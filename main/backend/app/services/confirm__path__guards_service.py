from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any


@dataclass(frozen=True)
class ConfirmGuardResult:
    ok: bool
    reason: str | None = None


def d8(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(
        Decimal("0.00000001"),
        rounding=ROUND_DOWN,
    )


def _decimal_text(value: Any) -> str:
    return format(Decimal(str(value or 0)), "f")


def _fractional_scale(value: Any) -> int:
    txt = _decimal_text(value)
    if "." not in txt:
        return 0
    return len(txt.split(".", 1)[1])


def guard_amount_exact_d8(
    *,
    amount_asset: Any,
    expected_d8: Any,
) -> ConfirmGuardResult:
    scale = _fractional_scale(amount_asset)
    if scale > 8:
        return ConfirmGuardResult(
            ok=False,
            reason="AMOUNT_SCALE_OVERFLOW_D8",
        )
    got = d8(amount_asset)
    exp = d8(expected_d8)
    if got != exp:
        return ConfirmGuardResult(
            ok=False,
            reason="AMOUNT_EXACT_MISMATCH_D8",
        )
    return ConfirmGuardResult(ok=True, reason=None)


def guard_destination_exact(
    *,
    to_address: str,
    expected_to: str,
) -> ConfirmGuardResult:
    got = str(to_address or "").replace(" ", "")
    exp = str(expected_to or "").replace(" ", "")
    if exp and got != exp:
        return ConfirmGuardResult(False, "DESTINATION_MISMATCH")
    return ConfirmGuardResult(True, None)


def guard_asset_exact(
    *,
    asset: str,
    expected_asset: str,
) -> ConfirmGuardResult:
    got = str(asset or "TON").upper()
    exp = str(expected_asset or "TON").upper()
    if got != exp:
        return ConfirmGuardResult(False, "ASSET_MISMATCH")
    return ConfirmGuardResult(True, None)
