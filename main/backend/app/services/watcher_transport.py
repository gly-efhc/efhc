from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domain.finance.external_amounts import (
    external_amount_from_atomic,
    external_amount_from_display,
)
from app.lib.ton_address import TonAddressError, canonicalize_ton_address


@dataclass(frozen=True)
class WatcherTransportDecision:
    transport_kind: str
    confirm_asset: str
    amount_atomic: int
    atomic_decimals: int
    amount_display: Decimal


@dataclass(frozen=True)
class WatcherIntentTransportCheck:
    ok: bool
    reason: str | None


def _norm_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _canonical_master(value: Any) -> str:
    """Compare raw and friendly TON master addresses by the same chain identity."""
    address = str(value or "").strip()
    if not address:
        return ""
    try:
        return canonicalize_ton_address(address)
    except TonAddressError:
        # Preserve historical non-address test fixture identity semantics.
        return _norm_upper(address)


def _raw_units(value: Any) -> int:
    try:
        raw = Decimal(str(value or 0))
    except Exception as exc:
        raise ValueError("JETTON_AMOUNT_INVALID") from exc
    if not raw.is_finite() or raw != raw.to_integral_value() or raw < 0:
        raise ValueError("JETTON_AMOUNT_INVALID")
    return int(raw)


def classify_watcher_transport(
    *,
    asset: Any,
    amount: Any,
    amount_asset: Any,
    jetton_master: Any,
    efhc_master: str,
    usdt_master: str,
    efhc_decimals: int = 8,
    usdt_decimals: int = 6,
) -> WatcherTransportDecision:
    asset_u = _norm_upper(asset) or "TON"
    master_u = _canonical_master(jetton_master)
    efhc_master_u = _canonical_master(efhc_master)
    usdt_master_u = _canonical_master(usdt_master)

    if asset_u == "JETTON" and master_u and master_u == efhc_master_u:
        atomic = _raw_units(amount_asset)
        decimals = int(efhc_decimals)
        return WatcherTransportDecision(
            transport_kind="efhc_jetton",
            confirm_asset="EFHCJ",
            amount_atomic=atomic,
            atomic_decimals=decimals,
            amount_display=Decimal(atomic) / (Decimal(10) ** decimals),
        )

    if asset_u == "JETTON" and master_u and master_u == usdt_master_u:
        atomic = _raw_units(amount_asset)
        external = external_amount_from_atomic("USDT", atomic)
        if int(usdt_decimals) != external.decimals:
            raise ValueError("USDT_DECIMALS_MISMATCH")
        return WatcherTransportDecision(
            transport_kind="jetton_transfer",
            confirm_asset="USDT",
            amount_atomic=external.atomic,
            atomic_decimals=external.decimals,
            amount_display=external.display,
        )

    if asset_u == "JETTON":
        return WatcherTransportDecision(
            transport_kind="unknown_jetton",
            confirm_asset="JETTON_UNKNOWN",
            amount_atomic=0,
            atomic_decimals=0,
            amount_display=Decimal("0"),
        )

    external = external_amount_from_display("TON", amount or 0)
    return WatcherTransportDecision(
        transport_kind="native_ton",
        confirm_asset="TON",
        amount_atomic=external.atomic,
        atomic_decimals=external.decimals,
        amount_display=external.display,
    )


def validate_payment_intent_transport(
    decision: WatcherTransportDecision,
) -> WatcherIntentTransportCheck:
    if decision.transport_kind in {"native_ton", "jetton_transfer"}:
        return WatcherIntentTransportCheck(ok=True, reason=None)
    if decision.transport_kind == "efhc_jetton":
        return WatcherIntentTransportCheck(
            ok=False,
            reason="EFHC_JETTON_NOT_ALLOWED_FOR_PAYMENT_INTENT",
        )
    if decision.transport_kind == "unknown_jetton":
        return WatcherIntentTransportCheck(
            ok=False,
            reason="UNKNOWN_JETTON_MASTER",
        )
    return WatcherIntentTransportCheck(
        ok=False,
        reason="UNSUPPORTED_TRANSPORT_KIND",
    )
