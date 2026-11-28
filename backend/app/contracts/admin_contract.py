# backend/app/contracts/admin_contract.py
# ======================================================================
# SSOT контракт admin-контура: routes ↔ services.
# Контракт привязан к фасаду:
# app.services.admin.admin_facade.AdminService.
# ======================================================================

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from app.services.admin.admin_facade import (
    AdminUser,
    BankBalance,
    BankUserTransferRequest,
    BonusAwardFilters,
    CoinsStats,
    MintBurnRequest,
    Pagination,
    PanelsStats,
    ReferralsStats,
    ShopStats,
    SystemSetting,
    SystemStats,
    UserProgressSnapshot,
    WithdrawalFilters,
    WithdrawalRecord,
)
from sqlalchemy.ext.asyncio import AsyncSession


class AdminContract(Protocol):
    async def resolve_admin(
        self,
        db: AsyncSession,
        global_id: int,
    ) -> AdminUser: ...

    async def list_admin_logs(
        self,
        db: AsyncSession,
        *,
        pg: Pagination,
        q: str | None = None,
    ) -> list[dict[str, Any]]: ...

    async def get_setting(
        self,
        db: AsyncSession,
        key: str,
    ) -> SystemSetting | None: ...

    async def mget_settings(
        self,
        db: AsyncSession,
        keys: list[str],
    ) -> list[SystemSetting]: ...

    async def set_setting(
        self,
        db: AsyncSession,
        key: str,
        value: str,
        admin: AdminUser,
    ) -> None: ...

    async def mset_settings(
        self,
        db: AsyncSession,
        items: dict[str, str],
        admin: AdminUser,
    ) -> None: ...

    async def get_bank_balance(
        self,
        db: AsyncSession,
    ) -> BankBalance: ...

    async def mint_efhc(
        self,
        db: AsyncSession,
        req: MintBurnRequest,
        admin: AdminUser,
    ) -> dict[str, Any]: ...

    async def burn_efhc(
        self,
        db: AsyncSession,
        req: MintBurnRequest,
        admin: AdminUser,
    ) -> dict[str, Any]: ...
    async def manual_bank_user_transfer(
        self,
        db: AsyncSession,
        req: BankUserTransferRequest,
        admin: AdminUser,
    ) -> dict[str, Any]: ...
    async def get_coins_stats(
        self,
        db: AsyncSession,
    ) -> CoinsStats: ...

    async def get_panels_stats(
        self,
        db: AsyncSession,
    ) -> PanelsStats: ...

    async def get_referrals_stats(
        self,
        db: AsyncSession,
    ) -> ReferralsStats: ...

    async def get_shop_stats(
        self,
        db: AsyncSession,
    ) -> ShopStats: ...

    async def get_system_stats(
        self,
        db: AsyncSession,
    ) -> SystemStats: ...

    async def debug_user_progress(
        self,
        db: AsyncSession,
        global_id: int,
    ) -> UserProgressSnapshot: ...

    async def credit_bonus_efhc(
        self,
        db: AsyncSession,
        global_id: int,
        amount: Decimal,
        *,
        reason: str,
        idempotency_key: str,
        admin: AdminUser,
    ) -> dict[str, Any]: ...

    async def credit_regular_efhc(
        self,
        db: AsyncSession,
        global_id: int,
        amount: Decimal,
        *,
        reason: str,
        idempotency_key: str,
        admin: AdminUser,
    ) -> dict[str, Any]: ...

    async def list_withdraw_requests(
        self,
        db: AsyncSession,
        pg: Pagination,
        filters: WithdrawalFilters,
    ) -> list[WithdrawalRecord]: ...

    async def admin_approve_withdraw(
        self,
        db: AsyncSession,
        withdraw_id: int,
        req: Any,
        admin: AdminUser,
    ) -> Any: ...

    async def admin_reject_withdraw(
        self,
        db: AsyncSession,
        withdraw_id: int,
        reason: str,
        admin: AdminUser,
        *,
        idempotency_key: str,
        comment_override: str | None = None,
        comment_auto_translated: bool = False,
    ) -> Any: ...

    async def admin_mark_withdraw_paid(
        self,
        db: AsyncSession,
        withdraw_id: int,
        tx_hash: str,
        admin: AdminUser,
    ) -> None: ...

    async def list_bonus_payouts(
        self,
        db: AsyncSession,
        pg: Pagination,
        filters: BonusAwardFilters,
    ) -> list[dict[str, Any]]: ...
