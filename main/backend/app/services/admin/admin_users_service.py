"""Административный контур аккаунтов с owner ``global_id``.

Все просмотры, фильтры, DTO и финансовые действия используют canonical
``global_id``. Telegram provider subject не входит в административные
business DTO и сохраняется только в provider/delivery boundary.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.sql_aliases_core import canon_schema
from app.core.utils_core import format_decimal_str, quantize_decimal
from app.identity.api_contract import PydanticGlobalId
from app.models.referral_models import ReferralLink
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

from .admin_bank_service import BankService, BankUserTransferRequest
from .admin_rbac import RBAC, AdminRole, AdminUser

logger = get_logger(__name__)
S = get_settings()
SCHEMA_CORE = canon_schema(
    getattr(S, "DB_SCHEMA_CORE", "efhc_core") or "efhc_core"
)
EFHC_DECIMALS = int(getattr(S, "EFHC_DECIMALS", 8) or 8)


class UserBalanceSnapshot(BaseModel):
    """Балансы и энергия canonical EFHC account."""

    global_id: str
    is_vip: bool
    main_balance: str
    bonus_balance: str
    available_kwh: str
    total_generated_kwh: str
    created_at: str | None = None
    updated_at: str | None = None


class UserPanelsProgress(BaseModel):
    total_panels: int
    active_panels: int
    expired_panels: int
    total_panel_generated_kwh: str


class UserReferralsBrief(BaseModel):
    total_invited: int
    active_invited: int


class UserProgressSnapshot(BaseModel):
    user: UserBalanceSnapshot
    panels: UserPanelsProgress
    referrals: UserReferralsBrief


class AdjustUserBalanceRequest(BaseModel):
    """Ручная операция Банк↔аккаунт по strict external global_id."""

    global_id: PydanticGlobalId
    direction: Literal["credit", "debit"]
    balance_type: Literal["MAIN", "BONUS"]
    amount: Decimal = Field(..., gt=Decimal("0"))
    reason: str = Field(..., min_length=1, max_length=120)
    idempotency_key: str = Field(..., min_length=8, max_length=128)

    @field_validator("amount", mode="before")
    @classmethod
    def _validate_amount(cls, value: Any) -> Decimal:
        amount = Decimal(
            str(quantize_decimal(value, EFHC_DECIMALS, "DOWN"))
        )
        if amount <= 0:
            raise ValueError("Сумма должна быть больше 0")
        return amount


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def _get_user_row(
    db: AsyncSession,
    global_id: int,
) -> Any | None:
    result: Result = await db.execute(
        text(
            """
            SELECT global_id,
                   COALESCE(is_vip, FALSE) AS is_vip,
                   COALESCE(main_balance, 0) AS main_balance,
                   COALESCE(bonus_balance, 0) AS bonus_balance,
                   COALESCE(available_kwh, 0) AS available_kwh,
                   COALESCE(total_generated_kwh, 0)
                       AS total_generated_kwh,
                   created_at, updated_at
              FROM efhc_core.users
             WHERE global_id = :global_id
             LIMIT 1
            """
        ),
        {"global_id": int(global_id)},
    )
    return result.fetchone()


async def _get_panels_progress(
    db: AsyncSession,
    global_id: int,
) -> UserPanelsProgress:
    result: Result = await db.execute(
        text(
            """
            SELECT COUNT(1) AS total_panels,
                   SUM(CASE WHEN is_active THEN 1 ELSE 0 END)
                       AS active_panels,
                   SUM(CASE WHEN is_active THEN 0 ELSE 1 END)
                       AS expired_panels,
                   COALESCE(SUM(COALESCE(generated_kwh, 0)), 0)
                       AS total_gen
              FROM efhc_core.panels
             WHERE global_id = :global_id
               AND COALESCE(meta ->> 'protectively_voided', 'false') <> 'true'
            """
        ),
        {"global_id": int(global_id)},
    )
    row = result.fetchone()
    return UserPanelsProgress(
        total_panels=int(getattr(row, "total_panels", 0) or 0),
        active_panels=int(getattr(row, "active_panels", 0) or 0),
        expired_panels=int(getattr(row, "expired_panels", 0) or 0),
        total_panel_generated_kwh=format_decimal_str(
            getattr(row, "total_gen", 0) or 0,
            EFHC_DECIMALS,
        ),
    )


async def _get_referrals_brief(
    db: AsyncSession,
    global_id: int,
) -> UserReferralsBrief:
    total = await db.scalar(
        select(func.count(ReferralLink.id)).where(
            ReferralLink.inviter_global_id == int(global_id)
        )
    )
    active = await db.scalar(
        select(func.count(ReferralLink.id)).where(
            ReferralLink.inviter_global_id == int(global_id),
            ReferralLink.activated_at.isnot(None),
        )
    )
    return UserReferralsBrief(
        total_invited=int(total or 0),
        active_invited=int(active or 0),
    )


class AdminUsersService:
    """Account administration without Telegram ownership."""

    @staticmethod
    async def get_user_snapshot(
        db: AsyncSession,
        global_id: int,
    ) -> UserBalanceSnapshot:
        row = await _get_user_row(db, global_id)
        if row is None:
            raise ValueError("Пользователь не найден")
        return UserBalanceSnapshot(
            global_id=f"{int(row.global_id):010d}",
            is_vip=bool(row.is_vip),
            main_balance=format_decimal_str(
                row.main_balance, EFHC_DECIMALS
            ),
            bonus_balance=format_decimal_str(
                row.bonus_balance, EFHC_DECIMALS
            ),
            available_kwh=format_decimal_str(
                row.available_kwh, EFHC_DECIMALS
            ),
            total_generated_kwh=format_decimal_str(
                row.total_generated_kwh, EFHC_DECIMALS
            ),
            created_at=_iso(row.created_at),
            updated_at=_iso(row.updated_at),
        )

    @staticmethod
    async def get_user_progress(
        db: AsyncSession,
        global_id: int,
    ) -> UserProgressSnapshot:
        return UserProgressSnapshot(
            user=await AdminUsersService.get_user_snapshot(
                db, global_id
            ),
            panels=await _get_panels_progress(db, global_id),
            referrals=await _get_referrals_brief(db, global_id),
        )

    @staticmethod
    async def search_users_by_global_prefix(
        db: AsyncSession,
        *,
        global_prefix: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        prefix = global_prefix.strip()
        if not prefix or not prefix.isascii() or not prefix.isdigit():
            raise ValueError(
                "Префикс global_id должен состоять из цифр"
            )
        result: Result = await db.execute(
            text(
                """
                SELECT global_id,
                       COALESCE(is_vip, FALSE) AS is_vip,
                       COALESCE(main_balance, 0) AS main_balance,
                       COALESCE(bonus_balance, 0) AS bonus_balance
                  FROM efhc_core.users
                 WHERE CAST(global_id AS TEXT) LIKE :prefix
                 ORDER BY global_id
                 LIMIT :limit
                """
            ),
            {
                "prefix": f"{prefix}%",
                "limit": max(1, min(int(limit), 100)),
            },
        )
        return [
            {
                "global_id": f"{int(row.global_id):010d}",
                "is_vip": bool(row.is_vip),
                "main_balance": format_decimal_str(
                    row.main_balance, EFHC_DECIMALS
                ),
                "bonus_balance": format_decimal_str(
                    row.bonus_balance, EFHC_DECIMALS
                ),
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def adjust_user_balance_via_bank(
        db: AsyncSession,
        req: AdjustUserBalanceRequest,
        admin: AdminUser,
    ) -> dict[str, Any]:
        RBAC.require_role(admin, AdminRole.MODERATOR)
        global_id = int(req.global_id)
        if await _get_user_row(db, global_id) is None:
            raise ValueError("Пользователь не найден")
        amount = req.amount
        idem = req.idempotency_key.strip()
        await BankService.manual_bank_user_transfer(
            db,
            req=BankUserTransferRequest(
                global_id=f"{global_id:010d}",
                amount=amount,
                direction=req.direction,
                balance_type=(
                    "REGULAR" if req.balance_type == "MAIN" else "BONUS"
                ),
                reason=req.reason,
                idempotency_key=idem,
            ),
            admin=admin,
        )
        row = await _get_user_row(db, global_id)
        if row is None:
            raise ValueError("Пользователь не найден после операции")
        main = row.main_balance
        bonus = row.bonus_balance
        return {
            "ok": True,
            "global_id": f"{global_id:010d}",
            "direction": req.direction,
            "balance_type": req.balance_type,
            "amount": format_decimal_str(amount, EFHC_DECIMALS),
            "idempotency_key": idem,
            "new__main__balance": format_decimal_str(
                main, EFHC_DECIMALS
            ),
            "new_bonus_balance": format_decimal_str(
                bonus, EFHC_DECIMALS
            ),
        }

    @staticmethod
    async def credit_bonus_efhc(
        db: AsyncSession,
        global_id: int,
        amount: Decimal,
        *,
        reason: str = "ADMIN",
        idempotency_key: str,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """Compatibility entrypoint: делегирует BONUS в единый BankService."""
        return await AdminUsersService.adjust_user_balance_via_bank(
            db,
            AdjustUserBalanceRequest(
                global_id=f"{int(global_id):010d}",
                direction="credit",
                balance_type="BONUS",
                amount=amount,
                reason=reason,
                idempotency_key=idempotency_key,
            ),
            admin,
        )

    @staticmethod
    async def credit_regular_efhc(
        db: AsyncSession,
        global_id: int,
        amount: Decimal,
        *,
        reason: str = "ADMIN",
        idempotency_key: str,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """Compatibility entrypoint: делегирует MAIN в единый BankService."""
        return await AdminUsersService.adjust_user_balance_via_bank(
            db,
            AdjustUserBalanceRequest(
                global_id=f"{int(global_id):010d}",
                direction="credit",
                balance_type="MAIN",
                amount=amount,
                reason=reason,
                idempotency_key=idempotency_key,
            ),
            admin,
        )


__all__ = [
    "UserBalanceSnapshot",
    "UserPanelsProgress",
    "UserReferralsBrief",
    "UserProgressSnapshot",
    "AdjustUserBalanceRequest",
    "AdminUsersService",
]
