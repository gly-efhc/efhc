from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.common_schemas import EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId
from app.schemas.outcome_schemas import (
    WithdrawOutcomeBundleSchema,
)
from app.schemas.payment_intents_schemas import (
    PaymentIntentFlowTruthOut,
    PaymentIntentStatusOut,
)
from app.schemas.shop_schemas import ShopOrderViewOut
from app.schemas.wallet_schemas import WalletItemOut
from pydantic import Field


class HubLinkOut(EfhcBaseModel):
    id: ApiLifetimeId
    code: str
    title: str
    subtitle: str | None = None
    url: str
    target_kind: str
    open_mode: str
    sort_order: int
    is_active: bool
    icon_key: str | None = None


class HubSupportLinkOut(EfhcBaseModel):
    id: ApiLifetimeId
    title: str
    subtitle: str | None = None
    url: str
    open_mode: str
    icon_key: str | None = None


class HubEfhcHandoffOut(EfhcBaseModel):
    """Ответ Hub handoff для внешнего контура покупки EFHC."""

    redirect_url: str = Field(
        ...,
        description="Signed external URL for EFHC buy-flow",
    )
    expires_at: datetime = Field(
        ...,
        description="UTC expiration timestamp for handoff token",
    )
    transport: Literal["external_url"] = "external_url"
    mode: Literal["signed_token"] = "signed_token"


class BrowserShopActiveIntentOut(EfhcBaseModel):
    intent_id: ApiLifetimeId
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
    order_id: ApiLifetimeId | None = None
    order_status: str | None = None
    created_at: datetime
    expires_at: datetime
    flow_truth: PaymentIntentFlowTruthOut | None = None


class BrowserShopFlowTruthOut(EfhcBaseModel):
    handoff_configured: bool
    handoff_mode: Literal["connected", "missing_config"]
    wallet_linked: bool
    wallet_sync_required: bool
    wallet_ready: bool
    wallet_blocked: bool
    action_allowed: bool
    action_denied: bool
    readiness_state: str
    primary_cta: str
    active_intent: BrowserShopActiveIntentOut | None = None
    active_order_id: ApiLifetimeId | None = None
    active_order_status: str | None = None
    product_state: str
    next_action: str
    return_path: str
    canonical_center: str = "web_profile"
    next_step: Literal[
        "connect_handoff",
        "sync_wallet",
        "resume_intent",
        "create_intent",
    ]
    blocker_codes: list[str] = Field(default_factory=list)
    browser_shop_path: str = "/browser-shop"
    truth_label: Literal["shop_hub_truth_layer"] = (
        "shop_hub_truth_layer"
    )


class BrowserShopBootstrapOut(EfhcBaseModel):
    """Bootstrap contract for the external browser-shop shell."""

    mode: Literal["guest", "handoff_bound"] = Field(
        ...,
        description=(
            "Guest browser entry or signed handoff-bound entry."
        ),
    )
    tg_linked: bool = Field(
        ...,
        description=(
            "Whether Telegram identity is already bound at entry."
        ),
    )
    global_id: str | None = Field(
        default=None,
        pattern=r"^[0-9]{10}$",
        description="Canonical EFHC account identifier.",
    )
    wallet_linked: bool = Field(
        ...,
        description="Whether an active wallet binding already exists.",
    )
    active_wallet_address: str | None = Field(
        default=None,
        description="Current active wallet address if available.",
    )
    wallets: list[WalletItemOut] = Field(
        default_factory=list,
        description="Preloaded bound wallets for storefront bootstrap.",
    )
    wallet_sync_required: bool = Field(
        ...,
        description="Whether wallet sync action may still be required.",
    )
    bot_open_url: str | None = Field(
        default=None,
        description="Simple bot-open URL if configured.",
    )
    telegram_sync_url: str | None = Field(
        default=None,
        description="Telegram sync entry URL if configured.",
    )
    wallet_sync_url: str | None = Field(
        default=None,
        description="Wallet sync entry URL if configured.",
    )
    storefront_mode: Literal["browser_shop_mvp"] = "browser_shop_mvp"
    access_mode: Literal["telegram_handoff"] = "telegram_handoff"
    future_game_entry_enabled: bool = False
    available_modules: list[str] = Field(
        default_factory=lambda: ["storefront", "wallets"],
        description=(
            "Modules currently available in the external portal."
        ),
    )
    usdt_checkout_mode: str = "disabled"
    flow_truth: BrowserShopFlowTruthOut | None = None
    active_payment: PaymentIntentStatusOut | None = None
    intent_history: list[PaymentIntentStatusOut] = Field(
        default_factory=list,
    )
    latest_withdraw_request_id: ApiLifetimeId | None = None
    latest_withdraw_status: str | None = None
    latest_withdraw_outcome: WithdrawOutcomeBundleSchema | None = None


class BrowserShopCatalogItemOut(EfhcBaseModel):
    sku: str
    title: str
    description: str | None = None
    item_type: str
    ton_enabled: bool = False
    usdt_enabled: bool = False
    methods: dict[str, object] | None = None
    image_url: str | None = None
    category: str = "other"
    badge: str = ""
    status: str = "live"
    action_mode: str = "checkout"
    external_url: str | None = None
    delivery_mode: str = "manual"
    quantity_efhc: str | None = None
    sort_order: int = 0


class BrowserShopCatalogOut(EfhcBaseModel):
    items: list[BrowserShopCatalogItemOut]


class BrowserShopCreateIntentIn(EfhcBaseModel):
    token: str | None = None
    sku: str
    quantity: int = Field(default=1, ge=1)
    pay_method: str = Field(
        ...,
        description="TON or USDT.",
    )
    custom_efhc_amount_d8: str | None = Field(
        default=None,
        description=(
            "Whole EFHCm quantity for EFHC_PACKAGE_CUSTOM. "
            "Required only for the custom product; the server computes "
            "rate snapshot × quantity and never trusts a client total."
        ),
    )
    client_nonce: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )


class BrowserShopCreateIntentOut(EfhcBaseModel):
    global_id: str = Field(..., pattern=r"^[0-9]{10}$")
    intent_id: ApiLifetimeId
    order_id: ApiLifetimeId
    item_type: str
    pay_method: str
    amount: str
    external_amount_atomic: str
    external_decimals: int
    external_amount_display: str
    memo: str
    to_wallet: str
    tonconnect_tx: dict[str, object] | None = None
    tonconnect_transport_kind: str | None = None
    jetton_master_address: str | None = None
    jetton_decimals: int | None = None
    forward_payload_text: str | None = None
    fee_message_ton_amount: str | None = None
    forward_ton_amount: str | None = None
    recipient_strategy: str | None = None
    usdt_checkout_mode: str | None = None
    expires_at: datetime


class BrowserShopProfileOut(EfhcBaseModel):
    global_id: str = Field(..., pattern=r"^[0-9]{10}$")
    wallets: list[WalletItemOut] = Field(default_factory=list)
    orders: list[ShopOrderViewOut] = Field(default_factory=list)
    access_mode: Literal["telegram_handoff"] = "telegram_handoff"
    profile_mode: Literal["web_profile"] = "web_profile"
    bot_open_url: str | None = None
    wallet_sync_url: str | None = None
    telegram_sync_url: str | None = None
    flow_truth: BrowserShopFlowTruthOut | None = None
    active_payment: PaymentIntentStatusOut | None = None
    intent_history: list[PaymentIntentStatusOut] = Field(
        default_factory=list,
    )
    latest_withdraw_request_id: ApiLifetimeId | None = None
    latest_withdraw_status: str | None = None
    latest_withdraw_outcome: WithdrawOutcomeBundleSchema | None = None


class HubShopTruthOut(EfhcBaseModel):
    handoff_configured: bool
    handoff_mode: Literal["connected", "missing_config"]
    wallet_linked: bool
    wallet_sync_required: bool
    active_wallet_address: str | None = None
    bot_open_url: str | None = None
    telegram_sync_url: str | None = None
    wallet_sync_url: str | None = None
    flow_truth: BrowserShopFlowTruthOut
