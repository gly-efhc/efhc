from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from app.core.config_core import get_settings
from app.services.watcher_transport import (
    WatcherIntentTransportCheck,
    WatcherTransportDecision,
    classify_watcher_transport,
    validate_payment_intent_transport,
)

_RE_FORWARD_PAYLOAD = re.compile(
    r"^(?:JETTON_TRANSFER|JETTON_TRANSFER_NOTIFICATION)"
    r"\|FORWARD_PAYLOAD=(?P<payload>"
    r"(?:EFHC:(?:deposit_efhc|shop_external):\d{1,20}:(?:G\d{10}|\d{1,20})"
    r"|EFHC2:(?:deposit_efhc|shop_external):\d{1,20}:G\d{10}:"
    r"(?:TON|USDT):\d+))$"
)


@dataclass(frozen=True)
class JettonIntentParseResult:
    decision: WatcherTransportDecision
    check: WatcherIntentTransportCheck


@dataclass(frozen=True)
class JettonEnvelopeParseResult:
    ok: bool
    reason: str | None
    forward_payload: str | None
    envelope_kind: str | None


def _env(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw not in {None, ""}:
        return str(raw).strip()
    settings = get_settings()
    return str(getattr(settings, name, default) or "").strip()


def parse_payment_intent_transport_from_tx(
    *,
    tx: Any,
) -> JettonIntentParseResult:
    decision = classify_watcher_transport(
        asset=getattr(tx, "asset", "TON"),
        amount=getattr(tx, "amount", 0),
        amount_asset=getattr(tx, "amount_asset", 0),
        jetton_master=getattr(tx, "jetton_master", ""),
        efhc_master=_env("EFHC_JETTON_MASTER_ADDRESS"),
        usdt_master=_env("USDT_JETTON_MASTER_ADDRESS"),
        efhc_decimals=int(_env("EFHC_JETTON_DECIMALS", "8") or "8"),
        usdt_decimals=6,
    )
    check = validate_payment_intent_transport(decision)
    return JettonIntentParseResult(decision=decision, check=check)


def is_strict_usdt_master(*, jetton_master: Any) -> bool:
    expected = _env("USDT_JETTON_MASTER_ADDRESS").upper()
    got = str(jetton_master or "").strip().upper()
    return bool(expected) and got == expected


def parse_jetton_payload_envelope(
    *,
    memo: str,
    jetton_master: Any,
) -> JettonEnvelopeParseResult:
    if not is_strict_usdt_master(jetton_master=jetton_master):
        return JettonEnvelopeParseResult(
            ok=False,
            reason="JETTON_MASTER_NOT_ALLOWED",
            forward_payload=None,
            envelope_kind=None,
        )

    memo_norm = (memo or "").strip()
    if not memo_norm:
        return JettonEnvelopeParseResult(
            ok=False,
            reason="JETTON_ENVELOPE_EMPTY",
            forward_payload=None,
            envelope_kind=None,
        )

    if "EXCESSES" in memo_norm.upper():
        return JettonEnvelopeParseResult(
            ok=False,
            reason="JETTON_EXCESSES_NOT_ALLOWED",
            forward_payload=None,
            envelope_kind="excesses",
        )

    m = _RE_FORWARD_PAYLOAD.match(memo_norm)
    if not m:
        return JettonEnvelopeParseResult(
            ok=False,
            reason="JETTON_ENVELOPE_INVALID",
            forward_payload=None,
            envelope_kind=None,
        )

    if memo_norm.startswith("JETTON_TRANSFER_NOTIFICATION|"):
        kind = "transfer_notification"
    else:
        kind = "transfer"

    return JettonEnvelopeParseResult(
        ok=True,
        reason=None,
        forward_payload=str(m.group("payload")),
        envelope_kind=kind,
    )
