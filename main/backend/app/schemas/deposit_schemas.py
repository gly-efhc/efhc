# backend/app/schemas/deposit_schemas.py
# ----------------------------------------------------------------------
# Deposit EFHC (on-chain) — схемы для A+B контура.
# ----------------------------------------------------------------------

from __future__ import annotations

from typing import Any, Literal

from app.schemas.common_schemas import EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import ConfigDict, Field


class DepositPackageOut(EfhcBaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ApiLifetimeId
    title: str
    asset: str
    price_asset_d8: str
    efhc_amount_d8: str
    is_active: bool


class DepositPackagesOut(EfhcBaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DepositPackageOut]


class DepositEFHCIn(EfhcBaseModel):
    """Запрос на создание deposit-intent EFHC (on-chain)."""

    model_config = ConfigDict(extra="forbid")

    package_id: ApiLifetimeId = Field(..., ge=1)


class TonConnectTxOut(EfhcBaseModel):
    model_config = ConfigDict(extra="allow")

    validUntil: int
    messages: list[dict[str, Any]]


class DepositEFHCOut(EfhcBaseModel):
    """Ответ deposit-intent + TonConnect tx."""

    model_config = ConfigDict(extra="forbid")

    purpose: Literal["deposit_efhc"] = "deposit_efhc"
    status: Literal["PENDING"] = "PENDING"
    intent_id: ApiLifetimeId
    asset: str
    amount_asset_d8: str
    external_amount_atomic: str
    external_decimals: int
    external_amount_display: str
    efhc_amount_d8: str
    payload: str
    tonconnect_tx: TonConnectTxOut
    tonconnect_transport_kind: str | None = None
    jetton_master_address: str | None = None
    jetton_decimals: int | None = None
    forward_payload_text: str | None = None
    fee_message_ton_amount: str | None = None
    forward_ton_amount: str | None = None
    recipient_strategy: str | None = None
    usdt_checkout_mode: str | None = None


class DirectDepositOpenOut(EfhcBaseModel):
    """Direct EFHC jetton deposit transfer metadata.

    This contract never describes a native TON payment or shop purchase.
    The frontend uses the fields to build a TEP-74 EFHC jetton transfer.
    """

    model_config = ConfigDict(extra="forbid")

    purpose: Literal["direct_efhc_jetton_deposit"] = (
        "direct_efhc_jetton_deposit"
    )
    asset: Literal["EFHC"] = "EFHC"
    receiver_owner_address: str
    jetton_master_address: str
    jetton_decimals: int = 8
    forward_payload_text: str
    fee_message_ton_amount: str
    forward_ton_amount: str
    memo_binding: Literal["global_id"] = "global_id"
