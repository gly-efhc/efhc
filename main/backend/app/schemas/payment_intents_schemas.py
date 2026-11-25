# backend/app/schemas/payment_intents_schemas.py
# ---------------------------------------------------------------------
# SSOT schema: Payment Intent status view (owner-only).
# ---------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime

from app.schemas.common_schemas import EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import ConfigDict


class PaymentIntentFlowTruthOut(EfhcBaseModel):
    lifecycle_stage: str
    product_state: str
    lifecycle_terminal: bool
    next_step: str
    next_action: str
    return_path: str
    canonical_center: str
    message_key: str
    watcher_status: str | None = None
    watcher_tx_hash: str | None = None
    watcher_last_error: str | None = None
    order_id: ApiLifetimeId | None = None
    order_status: str | None = None
    payment_error_log: str | None = None


class PaymentIntentStatusOut(EfhcBaseModel):
    id: ApiLifetimeId
    purpose: str
    asset: str
    amount_asset_d8: str
    external_amount_atomic: str | None = None
    external_decimals: int | None = None
    external_amount_display: str | None = None
    efhc_amount_d8: str | None = None
    status: str
    payload: str
    to_address: str
    external_tx_hash: str | None = None
    tonconnect_transport_kind: str | None = None
    jetton_master_address: str | None = None
    jetton_decimals: int | None = None
    forward_payload_text: str | None = None
    fee_message_ton_amount: str | None = None
    forward_ton_amount: str | None = None
    recipient_strategy: str | None = None
    usdt_checkout_mode: str | None = None
    created_at: datetime
    expires_at: datetime
    flow_truth: PaymentIntentFlowTruthOut | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 12,
                "purpose": "deposit_efhc",
                "asset": "TON",
                "amount_asset_d8": "1.00000000",
                "external_amount_atomic": "1000000000",
                "external_decimals": 9,
                "external_amount_display": "1.000000000",
                "efhc_amount_d8": "10.00000000",
                "status": "PENDING",
                "payload": "EFHC2:deposit_efhc:12:G0000009001:TON:1000000000",
                "to_address": "EQ...",
                "external_tx_hash": None,
                "created_at": "2026-02-25T00:00:00Z",
                "expires_at": "2026-02-25T00:15:00Z",
            }
        },
    )
