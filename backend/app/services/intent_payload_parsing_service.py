from __future__ import annotations

import re
from typing import Any

from app.domain.finance.external_amounts import atomic_decimals

_OWNER = r"(?P<owner>G[0-9]{10}|[0-9]{1,20})"
_PURPOSE = r"(?P<purpose>deposit_efhc|shop_external)"
_RE_V2_EXACT = re.compile(
    rf"^EFHC2:{_PURPOSE}:(?P<intent_id>[0-9]{{1,20}}):{_OWNER}:"
    r"(?P<asset>TON|USDT):(?P<atomic>[0-9]+)$"
)
_RE_V2_SUBSTR = re.compile(
    rf"EFHC2:{_PURPOSE}:(?P<intent_id>[0-9]{{1,20}}):{_OWNER}:"
    r"(?P<asset>TON|USDT):(?P<atomic>[0-9]+)"
)
_RE_INTENT_EXACT = re.compile(
    rf"^EFHC:{_PURPOSE}:(?P<intent_id>[0-9]{{1,20}}):{_OWNER}$"
)
_RE_INTENT_SUBSTR = re.compile(
    rf"EFHC:{_PURPOSE}:(?P<intent_id>[0-9]{{1,20}}):{_OWNER}"
)


def _result(match: re.Match[str], payload: str, *, version: int) -> dict[str, Any]:
    owner = str(match.group("owner"))
    result: dict[str, Any] = {
        "purpose": str(match.group("purpose")),
        "intent_id": int(match.group("intent_id")),
        "payload": payload,
        "payload_version": int(version),
    }
    if owner.startswith("G"):
        result["global_id"] = owner[1:]
        result["tg_id"] = None
    else:
        result["tg_id"] = int(owner)
        result["global_id"] = None
    if version >= 2:
        asset = str(match.group("asset")).upper()
        result["asset"] = asset
        result["external_amount_atomic"] = int(match.group("atomic"))
        result["external_decimals"] = atomic_decimals(asset)
    return result


def parse_intent_payload(memo: str) -> dict[str, Any] | None:
    """Разобрать legacy EFHC v1 или atomic EFHC2 PaymentIntent payload."""
    memo = (memo or "").strip()
    for regex, version in (
        (_RE_V2_EXACT, 2),
        (_RE_INTENT_EXACT, 1),
    ):
        match = regex.match(memo)
        if match:
            return _result(match, memo, version=version)
    for regex, version in (
        (_RE_V2_SUBSTR, 2),
        (_RE_INTENT_SUBSTR, 1),
    ):
        match = regex.search(memo)
        if match:
            return _result(match, str(match.group(0)), version=version)
    return None
