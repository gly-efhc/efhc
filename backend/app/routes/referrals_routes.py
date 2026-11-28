"""Referral API для текущего канонического владельца аккаунта."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from typing import Any, Literal

from app.deps import d8, get_db
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.services.referral_service import (
    get_counters_global,
    get_referrals_page_stats_global,
    list_active_referrals_global,
    list_inactive_referrals_global,
)
from fastapi import (
    APIRouter,
    Depends,
    Header,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/referrals", tags=["referrals"])
_DATASET_VERSION = "referrals-v2"


class ReferralItemOut(BaseModel):
    child_global_id: str
    global_id: str
    username: str | None = None
    joined_at: str = Field(..., description="ISO8601 UTC")
    is_active: bool
    total_generated_kwh: str = Field(
        ...,
        description="Decimal d8 string",
    )
    panels_count: int
    invited_at: str = Field(..., description="ISO8601 UTC")
    activated_at: str | None = Field(None, description="ISO8601 UTC")


class ReferralsPageOut(BaseModel):
    items: list[ReferralItemOut]
    next_cursor: str | None = None


class ReferralCountersOut(BaseModel):
    total: int
    active: int
    inactive: int


class ReferralLevelStepOut(BaseModel):
    level: int
    required_active: int
    level_bonus: str
    direct_bonus_total: str
    cumulative_level_bonus: str
    cumulative_total_reward: str


class ReferralsStatsOut(BaseModel):
    bonus_balance: str
    referrals_bonus_total: str
    total_referrals: int
    active_referrals: int
    inactive_referrals: int
    level: int
    current_level_min: int
    next_level: int | None = None
    next_level_min: int | None = None
    refs_to_next: int
    progress: float
    unit_bonus_per_active: str
    max_active_for_unit_bonus: int
    bonus_asset: str = Field(
        ...,
        description="Canonical bonus asset: EFHCb",
    )
    full_cycle_direct_bonus: str
    full_cycle_level_bonus: str
    full_cycle_total_bonus: str
    level_steps: list[ReferralLevelStepOut]
    referral_code: str
    referral_link: str | None = None


def _build_etag(payload: dict[str, Any]) -> str:
    """Build a strong ETag without secrets or internal DB values."""
    raw = json.dumps(
        {"dataset_version": _DATASET_VERSION, **payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f'"{hashlib.sha256(raw).hexdigest()}"'


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    candidates = {part.strip() for part in if_none_match.split(",")}
    return "*" in candidates or etag in candidates


def _not_modified(etag: str) -> Response:
    return Response(
        status_code=status.HTTP_304_NOT_MODIFIED,
        headers={"ETag": etag},
    )


def _item_payload(item: Any) -> dict[str, Any]:
    return {
        "child_global_id": f"{int(item.child_global_id):010d}",
        "global_id": f"{int(item.global_id):010d}",
        "username": item.username,
        "joined_at": item.joined_at.astimezone(UTC).isoformat(),
        "is_active": bool(item.is_active),
        "total_generated_kwh": format(d8(item.total_generated_kwh), "f"),
        "panels_count": int(item.panels_count),
        "invited_at": item.invited_at.astimezone(UTC).isoformat(),
        "activated_at": (
            item.activated_at.astimezone(UTC).isoformat()
            if item.activated_at is not None
            else None
        ),
    }


async def _stats_response(
    *,
    owner: NonFinancialReadOwner,
    response: Response,
    if_none_match: str | None,
    db: AsyncSession,
) -> ReferralsStatsOut | Response:
    stats = await get_referrals_page_stats_global(
        db,
        inviter_global_id=int(owner.global_id),
    )
    payload = {
        "owner_global_id": f"{int(owner.global_id):010d}",
        "bonus_balance": format(d8(stats.bonus_balance), "f"),
        "referrals_bonus_total": format(d8(stats.referrals_bonus_total), "f"),
        "total_referrals": int(stats.total_referrals),
        "active_referrals": int(stats.active_referrals),
        "inactive_referrals": int(stats.inactive_referrals),
        "level": int(stats.level),
        "current_level_min": int(stats.current_level_min),
        "next_level": stats.next_level,
        "next_level_min": stats.next_level_min,
        "refs_to_next": int(stats.refs_to_next),
        "progress": float(stats.progress),
        "unit_bonus_per_active": format(d8(stats.unit_bonus_per_active), "f"),
        "max_active_for_unit_bonus": int(
            stats.max_active_for_unit_bonus
        ),
        "bonus_asset": stats.bonus_asset,
        "full_cycle_direct_bonus": format(d8(stats.full_cycle_direct_bonus), "f"),
        "full_cycle_level_bonus": format(d8(stats.full_cycle_level_bonus), "f"),
        "full_cycle_total_bonus": format(d8(stats.full_cycle_total_bonus), "f"),
        "level_steps": [
            {
                "level": int(step.level),
                "required_active": int(step.required_active),
                "level_bonus": format(d8(step.level_bonus), "f"),
                "direct_bonus_total": format(d8(step.direct_bonus_total), "f"),
                "cumulative_level_bonus": format(d8(step.cumulative_level_bonus), "f"),
                "cumulative_total_reward": format(d8(step.cumulative_total_reward), "f"),
            }
            for step in stats.level_steps
        ],
        "referral_code": str(stats.referral_code),
        "referral_link": stats.referral_link,
    }
    etag = _build_etag(payload)
    if _etag_matches(if_none_match, etag):
        return _not_modified(etag)
    response.headers["ETag"] = etag
    return ReferralsStatsOut.model_validate(payload)


async def _counters_response(
    *,
    owner: NonFinancialReadOwner,
    if_none_match: str | None,
    db: AsyncSession,
) -> Response:
    counters = await get_counters_global(
        db,
        parent_global_id=int(owner.global_id),
    )
    payload = {
        "owner_global_id": f"{int(owner.global_id):010d}",
        "total": int(counters.total),
        "active": int(counters.active),
        "inactive": int(counters.inactive),
    }
    etag = _build_etag(payload)
    if _etag_matches(if_none_match, etag):
        return _not_modified(etag)
    out = ReferralCountersOut(
        total=counters.total,
        active=counters.active,
        inactive=counters.inactive,
    )
    return Response(
        content=out.model_dump_json(),
        status_code=status.HTTP_200_OK,
        media_type="application/json",
        headers={"ETag": etag},
    )


async def _page_response(
    *,
    owner: NonFinancialReadOwner,
    tab: Literal["active", "inactive"],
    response: Response,
    limit: int,
    cursor: str | None,
    if_none_match: str | None,
    db: AsyncSession,
) -> ReferralsPageOut | Response:
    if tab == "active":
        page = await list_active_referrals_global(
            db,
            parent_global_id=int(owner.global_id),
            limit=int(limit),
            cursor=cursor,
        )
    else:
        page = await list_inactive_referrals_global(
            db,
            parent_global_id=int(owner.global_id),
            limit=int(limit),
            cursor=cursor,
        )
    items = [_item_payload(item) for item in page.items]
    payload = {
        "owner_global_id": f"{int(owner.global_id):010d}",
        "tab": tab,
        "cursor": cursor,
        "limit": max(1, min(int(limit), 200)),
        "items": items,
        "next_cursor": page.next_cursor,
    }
    etag = _build_etag(payload)
    if _etag_matches(if_none_match, etag):
        return _not_modified(etag)
    response.headers["ETag"] = etag
    return ReferralsPageOut.model_validate(
        {"items": items, "next_cursor": page.next_cursor}
    )


@router.get("/stats/me", response_model=ReferralsStatsOut)
async def get_my_referrals_stats(
    response: Response,
    if_none_match: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
) -> ReferralsStatsOut | Response:
    return await _stats_response(
        owner=owner,
        response=response,
        if_none_match=if_none_match,
        db=db,
    )


@router.get("/counters/me", response_model=ReferralCountersOut)
async def get_my_referral_counters(
    if_none_match: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
) -> Response:
    return await _counters_response(
        owner=owner,
        if_none_match=if_none_match,
        db=db,
    )


@router.get("/active/me", response_model=ReferralsPageOut)
async def get_my_referrals_active(
    response: Response,
    limit: int = 100,
    cursor: str | None = None,
    if_none_match: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
) -> ReferralsPageOut | Response:
    return await _page_response(
        owner=owner,
        tab="active",
        response=response,
        limit=limit,
        cursor=cursor,
        if_none_match=if_none_match,
        db=db,
    )


@router.get("/inactive/me", response_model=ReferralsPageOut)
async def get_my_referrals_inactive(
    response: Response,
    limit: int = 100,
    cursor: str | None = None,
    if_none_match: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
) -> ReferralsPageOut | Response:
    return await _page_response(
        owner=owner,
        tab="inactive",
        response=response,
        limit=limit,
        cursor=cursor,
        if_none_match=if_none_match,
        db=db,
    )
