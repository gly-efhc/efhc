"""CRUD provider-neutral реферального домена EFHC."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import cast

from app.deps import d8, decode_cursor, encode_cursor
from app.lib.time import utcnow
from app.models.referral_models import ReferralBonusLedger, ReferralLink
from app.models.transactions_models import EfhcTransferLog
from app.models.user_models import User
from app.schemas.referral_schemas import BonusRecordCreate
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_referral_link_by_invitee(
    db: AsyncSession,
    *,
    invitee_global_id: int,
) -> ReferralLink | None:
    stmt = (
        select(ReferralLink)
        .where(ReferralLink.invitee_global_id == int(invitee_global_id))
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def get_referrals_by_inviter(
    db: AsyncSession,
    *,
    inviter_global_id: int,
) -> list[ReferralLink]:
    stmt = (
        select(ReferralLink)
        .where(ReferralLink.inviter_global_id == int(inviter_global_id))
        .order_by(ReferralLink.id.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


@dataclass(frozen=True)
class ReferralActivationResult:
    link: ReferralLink | None
    activated_now: bool


async def activate_referral(
    db: AsyncSession,
    *,
    invitee_global_id: int,
    activation_dt: datetime | None = None,
) -> ReferralActivationResult:
    """Атомарно выполнить единственный ``NULL -> activated_at``."""
    stmt = (
        select(ReferralLink)
        .where(ReferralLink.invitee_global_id == int(invitee_global_id))
        .limit(1)
        .with_for_update()
    )
    link = (await db.execute(stmt)).scalars().first()
    if link is None:
        return ReferralActivationResult(link=None, activated_now=False)
    if link.activated_at is not None:
        return ReferralActivationResult(link=link, activated_now=False)
    link.activated_at = activation_dt or utcnow()
    db.add(link)
    await db.flush()
    return ReferralActivationResult(link=link, activated_now=True)


async def _list_refs_cursor(
    db: AsyncSession,
    *,
    inviter_global_id: int,
    limit: int,
    next_cursor: str | None,
    want_active: bool,
) -> tuple[list[ReferralLink], str | None]:
    safe_limit = max(1, min(int(limit), 200))
    cursor_ts: datetime | None = None
    cursor_gid: int | None = None
    if next_cursor:
        payload = decode_cursor(next_cursor)
        raw_ts = payload.get("invited_at")
        raw_gid = payload.get("invitee_global_id")
        if raw_ts is not None and raw_gid is not None:
            cursor_ts = datetime.fromisoformat(str(raw_ts))
            cursor_gid = int(raw_gid)

    activity_clause = (
        ReferralLink.activated_at.isnot(None)
        if want_active
        else ReferralLink.activated_at.is_(None)
    )
    stmt = select(ReferralLink).where(
        ReferralLink.inviter_global_id == int(inviter_global_id),
        activity_clause,
    )
    if cursor_ts is not None and cursor_gid is not None:
        stmt = stmt.where(
            or_(
                ReferralLink.created_at < cursor_ts,
                and_(
                    ReferralLink.created_at == cursor_ts,
                    ReferralLink.invitee_global_id < cursor_gid,
                ),
            )
        )
    stmt = stmt.order_by(
        ReferralLink.created_at.desc(),
        ReferralLink.invitee_global_id.desc(),
    ).limit(safe_limit + 1)
    items = list((await db.execute(stmt)).scalars().all())
    has_more = len(items) > safe_limit
    items = items[:safe_limit]
    next_value: str | None = None
    if has_more and items:
        last = items[-1]
        next_value = encode_cursor(
            {
                "invited_at": last.created_at.isoformat(),
                "invitee_global_id": int(last.invitee_global_id),
            }
        )
    return items, next_value


async def list_active_refs_cursor(
    db: AsyncSession,
    *,
    inviter_global_id: int,
    limit: int = 50,
    next_cursor: str | None = None,
) -> tuple[list[ReferralLink], str | None]:
    return await _list_refs_cursor(
        db,
        inviter_global_id=int(inviter_global_id),
        limit=int(limit),
        next_cursor=next_cursor,
        want_active=True,
    )


async def list_inactive_refs_cursor(
    db: AsyncSession,
    *,
    inviter_global_id: int,
    limit: int = 50,
    next_cursor: str | None = None,
) -> tuple[list[ReferralLink], str | None]:
    return await _list_refs_cursor(
        db,
        inviter_global_id=int(inviter_global_id),
        limit=int(limit),
        next_cursor=next_cursor,
        want_active=False,
    )


async def count_total_and_active(
    db: AsyncSession,
    *,
    inviter_global_id: int,
) -> tuple[int, int]:
    selector = ReferralLink.inviter_global_id == int(inviter_global_id)
    total_stmt = select(func.count(ReferralLink.id)).where(selector)
    active_stmt = select(func.count(ReferralLink.id)).where(
        selector,
        ReferralLink.activated_at.isnot(None),
    )
    total = int((await db.execute(total_stmt)).scalar_one() or 0)
    active = int((await db.execute(active_stmt)).scalar_one() or 0)
    return total, active


async def add_bonus_record(
    db: AsyncSession,
    *,
    payload: BonusRecordCreate,
) -> ReferralBonusLedger:
    rec = ReferralBonusLedger(
        global_id=int(payload.global_id),
        amount_efhc=d8(payload.amount_efhc),
        kind=str(payload.kind),
        meta=(str(payload.meta) if payload.meta is not None else None),
        created_at=utcnow(),
    )
    db.add(rec)
    await db.flush()
    return rec


async def sum_bonus_for_user(
    db: AsyncSession,
    *,
    global_id: int,
) -> Decimal:
    stmt = select(
        func.coalesce(func.sum(ReferralBonusLedger.amount_efhc), 0)
    ).where(ReferralBonusLedger.global_id == int(global_id))
    value = (await db.execute(stmt)).scalar_one()
    result: Decimal = d8(value)
    return result


async def has_rank_bonus_paid(
    db: AsyncSession,
    *,
    global_id: int,
    rank: int,
) -> bool:
    stmt = select(ReferralBonusLedger.id).where(
        ReferralBonusLedger.global_id == int(global_id),
        ReferralBonusLedger.kind == f"rank:{int(rank)}",
    )
    row = (await db.execute(stmt.limit(1))).scalar_one_or_none()
    return row is not None


async def admin_top_inviters(
    db: AsyncSession,
    *,
    limit: int = 50,
) -> Sequence[object]:
    active_subq = (
        select(
            ReferralLink.inviter_global_id.label("global_id"),
            func.count(ReferralLink.id).label("active_count"),
        )
        .where(ReferralLink.activated_at.isnot(None))
        .group_by(ReferralLink.inviter_global_id)
        .subquery()
    )
    bonus_subq = (
        select(
            EfhcTransferLog.global_id.label("global_id"),
            func.coalesce(
                func.sum(EfhcTransferLog.amount),
                0,
            ).label("bonus_sum"),
        )
        .where(
            EfhcTransferLog.direction == "credit",
            EfhcTransferLog.balance_type == "bonus",
            EfhcTransferLog.reason.in_(
                ["referral_active_unit", "referral_level_bonus"]
            ),
        )
        .group_by(EfhcTransferLog.global_id)
        .subquery()
    )
    stmt = (
        select(
            User.global_id.label("inviter_global_id"),
            User.username,
            func.count(ReferralLink.id).label("total_invited"),
            func.coalesce(
                active_subq.c.active_count,
                0,
            ).label("active_invited"),
            func.coalesce(
                bonus_subq.c.bonus_sum,
                0,
            ).label("total_bonus_efhc"),
        )
        .join(
            ReferralLink,
            ReferralLink.inviter_global_id == User.global_id,
            isouter=True,
        )
        .join(
            active_subq,
            active_subq.c.global_id == User.global_id,
            isouter=True,
        )
        .join(
            bonus_subq,
            bonus_subq.c.global_id == User.global_id,
            isouter=True,
        )
        .group_by(
            User.global_id,
            User.username,
            active_subq.c.active_count,
            bonus_subq.c.bonus_sum,
        )
        .order_by(
            func.coalesce(active_subq.c.active_count, 0).desc(),
            func.coalesce(bonus_subq.c.bonus_sum, 0).desc(),
        )
        .limit(max(1, min(int(limit), 100)))
    )
    return cast(Sequence[object], (await db.execute(stmt)).all())


__all__ = [
    "ReferralActivationResult",
    "activate_referral",
    "add_bonus_record",
    "admin_top_inviters",
    "count_total_and_active",
    "get_referral_link_by_invitee",
    "get_referrals_by_inviter",
    "has_rank_bonus_paid",
    "list_active_refs_cursor",
    "list_inactive_refs_cursor",
    "sum_bonus_for_user",
]
