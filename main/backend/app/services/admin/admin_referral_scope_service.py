from __future__ import annotations

from typing import Any

from app.deps import d8, decode_cursor_or_400
from app.models.referral_models import ReferralLink
from app.models.transactions_models import EfhcTransferLog
from app.utils.cursor_codec import encode_cursor
from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _normalize_selected_global_id(value: str | int) -> int:
    raw = str(value).strip()
    if len(raw) != 10 or not raw.isascii() or not raw.isdigit() or raw == "0000000000":
        raise HTTPException(
            status_code=400,
            detail="Global ID должен содержать ровно 10 цифр",
        )
    return int(raw)


def _selected_summary_stats_statement(global_id: int):
    return select(
        func.count()
        .filter(ReferralLink.activated_at.is_not(None))
        .label("active_count"),
        func.count()
        .filter(ReferralLink.activated_at.is_(None))
        .label("inactive_count"),
        func.max(ReferralLink.created_at).label("last_invited_at"),
    ).where(ReferralLink.inviter_global_id == int(global_id))


def _selected_bonus_statement(global_id: int):
    """Preserve admin_summary bonus semantics, but scope to one owner in SQL."""

    return select(func.coalesce(func.sum(EfhcTransferLog.amount), 0)).where(
        EfhcTransferLog.global_id == int(global_id),
        EfhcTransferLog.direction == "credit",
        EfhcTransferLog.balance_type == "bonus",
        EfhcTransferLog.reason.in_(
            ["referral_active_unit", "referral_level_bonus"]
        ),
    )


async def selected_referral_summary(
    db: AsyncSession,
    *,
    global_id: str | int,
) -> dict[str, Any]:
    """Return zero or one exact-owner summary row without all-user fallback."""

    owner = _normalize_selected_global_id(global_id)
    row = (await db.execute(_selected_summary_stats_statement(owner))).one()
    active_count = int(row.active_count or 0)
    inactive_count = int(row.inactive_count or 0)
    if active_count + inactive_count == 0:
        return {"items": [], "next_after": None}

    total_bonus = (
        await db.execute(_selected_bonus_statement(owner))
    ).scalar() or 0
    return {
        "items": [
            {
                "inviter_global_id": f"{owner:010d}",
                "active_count": active_count,
                "inactive_count": inactive_count,
                "total_bonus_efhc": str(d8(total_bonus)),
                "last_invited_at": row.last_invited_at,
            }
        ],
        "next_after": None,
    }


def _selected_logs_statement(
    global_id: int,
    *,
    after_id: int | None,
    limit: int,
):
    stmt = select(
        ReferralLink.id,
        ReferralLink.invitee_global_id,
        ReferralLink.created_at,
        ReferralLink.activated_at,
        ReferralLink.unit_reward_no,
    ).where(ReferralLink.inviter_global_id == int(global_id))
    if after_id is not None:
        stmt = stmt.where(ReferralLink.id < int(after_id))
    return stmt.order_by(desc(ReferralLink.id)).limit(int(limit) + 1)


async def selected_referral_logs(
    db: AsyncSession,
    *,
    global_id: str | int,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Return detailed referral rows belonging only to one selected inviter."""

    owner = _normalize_selected_global_id(global_id)
    row_limit = max(1, min(200, int(limit)))
    after_id: int | None = None
    if cursor:
        payload = decode_cursor_or_400(cursor)
        raw_after_id = payload.get("after_id")
        if raw_after_id is None:
            raise HTTPException(
                status_code=400,
                detail="cursor payload missing after_id",
            )
        try:
            after_id = int(raw_after_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail="cursor payload invalid after_id",
            ) from exc

    rows = (
        await db.execute(
            _selected_logs_statement(
                owner,
                after_id=after_id,
                limit=row_limit,
            )
        )
    ).all()

    has_more = len(rows) > row_limit
    selected = rows[:row_limit]
    next_cursor = (
        encode_cursor({"after_id": int(selected[-1].id)})
        if has_more and selected
        else None
    )

    items: list[dict[str, Any]] = []
    for row in selected:
        items.append(
            {
                "inviter_global_id": f"{owner:010d}",
                "invitee_global_id": f"{int(row.invitee_global_id):010d}",
                "status": (
                    "active" if row.activated_at is not None else "inactive"
                ),
                "invited_at": row.created_at.isoformat(),
                "activated_at": (
                    row.activated_at.isoformat()
                    if row.activated_at is not None
                    else None
                ),
                "reward_recorded": row.unit_reward_no is not None,
            }
        )

    return {
        "global_id": f"{owner:010d}",
        "items": items,
        "next_cursor": next_cursor,
    }
