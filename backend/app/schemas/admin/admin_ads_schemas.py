from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from app.schemas.admin.admin_schemas import (
    AdminActor,
    AdminBurnIn,
    AdminBurnOut,
    AdminEmitIn,
    AdminEmitOut,
    AdminForceCreditUserFromBankIn,
    AdminForceCreditUserFromBankOut,
    AdminForceDebitUserToBankIn,
    AdminForceDebitUserToBankOut,
    AdminNftRequestModerateIn,
    AdminNftRequestModerateOut,
    AdminReportsOut,
    AdminReportsQueryIn,
    AdminShopItemOut,
    AdminShopItemUpsertIn,
    AdminTaskOut,
    AdminTaskUpsertIn,
    AdminTonReconcileIn,
    AdminTonReconcileOut,
    AdminWithdrawModerateIn,
    AdminWithdrawModerateOut,
    ModerationAction,
    ShopItemType,
    TaskType,
    TonInboxLogRow,
    TonInboxPage,
    WithdrawPage,
    WithdrawRow,
)

__all__ = [
    "AdminActor",
    "AdminBurnIn",
    "AdminBurnOut",
    "AdminEmitIn",
    "AdminEmitOut",
    "AdminForceCreditUserFromBankIn",
    "AdminForceCreditUserFromBankOut",
    "AdminForceDebitUserToBankIn",
    "AdminForceDebitUserToBankOut",
    "AdminNftRequestModerateIn",
    "AdminNftRequestModerateOut",
    "AdminReportsOut",
    "AdminReportsQueryIn",
    "AdminShopItemOut",
    "AdminShopItemUpsertIn",
    "AdminTaskOut",
    "AdminTaskUpsertIn",
    "AdminTonReconcileIn",
    "AdminTonReconcileOut",
    "AdminWithdrawModerateIn",
    "AdminWithdrawModerateOut",
    "ModerationAction",
    "ShopItemType",
    "TaskType",
    "TonInboxLogRow",
    "TonInboxPage",
    "WithdrawPage",
    "WithdrawRow",
]


class ProviderSaveIn(BaseModel):
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0)
    miniapp_enabled: bool | None = None
    bot_enabled: bool | None = None
    rewarded_enabled: bool | None = None
    public_config: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    countries_allow: list[str] | None = None
    countries_block: list[str] | None = None
    languages_allow: list[str] | None = None
    languages_block: list[str] | None = None
    moderation_status: str | None = Field(default=None, max_length=32)


class SecretReplaceIn(BaseModel):
    field: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=8192)


class SecretDeleteIn(BaseModel):
    field: str = Field(min_length=1, max_length=64)


class ProviderTestIn(BaseModel):
    mode: str = Field(default="configuration", pattern="^(configuration|sdk|request)$")


class RevenueOptimizerApplyIn(BaseModel):
    period: str = Field(default="30d", pattern="^(24h|7d|30d)$")
    min_requests: int = Field(default=20, ge=1, le=1_000_000)
