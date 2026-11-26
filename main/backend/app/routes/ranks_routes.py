# backend/app/routes/ranks_routes.py
"""Публичные routes рейтингов с provider-neutral владельцем ``global_id``."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from typing import Any

from app.core.logging_core import get_logger
from app.deps import d8, get_db
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.services.ranks_service import (
    get_my_plus_top,
    get_user_rank_context,
    list_top_page,
)
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/ranks", tags=["ranks"])


class RankItemOut(BaseModel):
    global_id: str = Field(pattern=r"^[0-9]{10}$")
    username: str | None = None
    total_generated_kwh: str
    rank_pos: int
    is_vip: bool
    active_referrals: int | None = None


class MyPlusTopOut(BaseModel):
    snapshot_at: str
    me: RankItemOut
    top: list[RankItemOut]
    next_cursor: str | None


class TopPageOut(BaseModel):
    snapshot_at: str
    items: list[RankItemOut]
    next_cursor: str | None


def _build_etag(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _rank_item_from_service(item: Any) -> RankItemOut:
    return RankItemOut(
        global_id=f"{int(item.global_id):010d}",
        username=item.username,
        total_generated_kwh=str(d8(item.total_kwh)),
        rank_pos=int(item.rank),
        is_vip=bool(item.is_vip),
    )


async def _kwh_my_plus_top_payload(
    *,
    db: AsyncSession,
    owner: NonFinancialReadOwner,
    limit: int,
    cursor: str | None,
    force_refresh: bool,
    max_age_minutes: int,
) -> MyPlusTopOut:
    me, top, meta, next_cursor = await get_my_plus_top(
        db,
        global_id=int(owner.global_id),
        limit=int(limit),
        cursor=cursor,
        force_refresh=bool(force_refresh),
        max_age_minutes=int(max_age_minutes),
    )
    me_out = (
        _rank_item_from_service(me)
        if me is not None
        else RankItemOut(
            global_id=f"{int(owner.global_id):010d}",
            username=None,
            total_generated_kwh="0.00000000",
            rank_pos=0,
            is_vip=False,
        )
    )
    return MyPlusTopOut(
        snapshot_at=meta.snapshot_at.astimezone(UTC).isoformat(),
        me=me_out,
        top=[_rank_item_from_service(item) for item in top],
        next_cursor=next_cursor,
    )


async def _kwh_top_payload(
    *,
    db: AsyncSession,
    limit: int,
    cursor: str | None,
    exclude_global_id: int | None,
    around_me: bool,
    force_refresh: bool,
    max_age_minutes: int,
) -> TopPageOut:
    if around_me and exclude_global_id is not None:
        items, meta = await get_user_rank_context(
            db,
            global_id=int(exclude_global_id),
            radius=2,
            force_refresh=bool(force_refresh),
            max_age_minutes=int(max_age_minutes),
        )
        next_cursor = None
    else:
        items, meta, next_cursor = await list_top_page(
            db,
            limit=int(limit),
            cursor=cursor,
            force_refresh=bool(force_refresh),
            max_age_minutes=int(max_age_minutes),
            global_read=True,
        )
        if exclude_global_id is not None:
            items = [
                item
                for item in items
                if int(item.global_id) != int(exclude_global_id)
            ]
    return TopPageOut(
        snapshot_at=meta.snapshot_at.astimezone(UTC).isoformat(),
        items=[_rank_item_from_service(item) for item in items],
        next_cursor=next_cursor,
    )


def _etag_or_304(
    *,
    response: Response,
    if_none_match: str | None,
    payload: BaseModel,
    scope: str,
) -> None:
    raw = payload.model_dump()
    raw["scope"] = scope
    etag = _build_etag(raw)
    if if_none_match and if_none_match.strip() == etag:
        raise HTTPException(
            status_code=status.HTTP_304_NOT_MODIFIED,
            detail="Not Modified",
        )
    response.headers["ETag"] = etag


@router.get("/my-plus-top/me", response_model=MyPlusTopOut)
async def get_my_kwh_rank_me(
    response: Response,
    limit: int = 100,
    cursor: str | None = None,
    force_refresh: bool = False,
    max_age_minutes: int = 10,
    if_none_match: str | None = Header(None, convert_underscores=True),
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db: AsyncSession = Depends(get_db),
) -> MyPlusTopOut:
    out = await _kwh_my_plus_top_payload(
        db=db,
        owner=owner,
        limit=limit,
        cursor=cursor,
        force_refresh=force_refresh,
        max_age_minutes=max_age_minutes,
    )
    _etag_or_304(
        response=response,
        if_none_match=if_none_match,
        payload=out,
        scope="ranks_kwh_me",
    )
    return out


@router.get("/top/me", response_model=TopPageOut)
async def get_kwh_top_me(
    response: Response,
    limit: int = 100,
    cursor: str | None = None,
    around_me: bool = False,
    force_refresh: bool = False,
    max_age_minutes: int = 10,
    if_none_match: str | None = Header(None, convert_underscores=True),
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db: AsyncSession = Depends(get_db),
) -> TopPageOut:
    out = await _kwh_top_payload(
        db=db,
        limit=limit,
        cursor=cursor,
        exclude_global_id=int(owner.global_id),
        around_me=around_me,
        force_refresh=force_refresh,
        max_age_minutes=max_age_minutes,
    )
    _etag_or_304(
        response=response,
        if_none_match=if_none_match,
        payload=out,
        scope="ranks_kwh_top_me",
    )
    return out
