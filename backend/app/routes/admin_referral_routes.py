# backend/app/routes/admin_referral_routes.py
# ======================================================================
# Admin: referrals
# ======================================================================

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.logging_core import get_logger
from app.deps import (
    d8,
    decode_cursor,
    encode_cursor,
    get_db,
    make_etag,
    require_admin,
)
from app.identity.api_contract import ApiExternalGlobalId
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
router = APIRouter(
    prefix="/admin/referrals",
    tags=["admin:referrals"],
)

# Soft import: роутер не должен падать, если сервис ещё не готов.
try:
    from app.services.referral_service import admin_summary

    _REF_SVC_AVAILABLE = True
except Exception:
    admin_summary = None
    _REF_SVC_AVAILABLE = False


class SummaryItem(BaseModel):
    inviter_global_id: str = Field(
        ..., description="Canonical global_id инвайтера"
    )
    active_count: int = Field(..., ge=0, description="Активные")
    inactive_count: int = Field(..., ge=0, description="Неактивные")
    total_bonus_efhc: str = Field(..., description="Сумма бонусов d8")
    last_invited_at: datetime | None = Field(
        None, description="Последнее приглашение"
    )


class SummaryResponse(BaseModel):
    items: list[SummaryItem]
    next_cursor: str | None = None


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    response: Response,
    global_id: ApiExternalGlobalId | None = None,
    limit: int = 50,
    cursor: str | None = None,
    _admin: Any = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    """Агрегированная сводка по инвайтерам (cursor + ETag)."""
    if not _REF_SVC_AVAILABLE or admin_summary is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="referral_service недоступен",
        )

    after: dict[str, Any] = {}
    if global_id is None and cursor:
        try:
            after = decode_cursor(cursor)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректный cursor",
            ) from None

    try:
        if global_id is not None:
            from app.services.admin.admin_referral_scope_service import (
                selected_referral_summary,
            )

            data: dict[str, Any] = await selected_referral_summary(
                db,
                global_id=global_id,
            )
        else:
            data = await admin_summary(
                db,
                limit=int(limit),
                after=after,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("admin_summary failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Временная ошибка сводки",
        ) from e

    items_in: list[dict[str, Any]] = list(data.get("items") or [])
    items: list[SummaryItem] = []
    for it in items_in:
        items.append(
            SummaryItem(
                inviter_global_id=(
                    f"{int(it['inviter_global_id']):010d}"
                ),
                active_count=int(it.get("active_count", 0)),
                inactive_count=int(it.get("inactive_count", 0)),
                total_bonus_efhc=str(
                    d8(it.get("total_bonus_efhc", "0"))
                ),
                last_invited_at=it.get("last_invited_at"),
            )
        )

    next_after: dict[str, Any] | None = data.get("next_after")
    next_cursor: str | None = None
    if next_after:
        next_cursor = encode_cursor(next_after)

    body = SummaryResponse(items=items, next_cursor=next_cursor)
    try:
        response.headers["ETag"] = make_etag(body.model_dump())
    except Exception:
        logger.warning("ETag compute failed", exc_info=True)

    return body


@router.get("/logs")
async def get_selected_referral_logs(
    global_id: ApiExternalGlobalId,
    limit: int = 50,
    cursor: str | None = None,
    _admin: Any = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Detailed referral log for one exact selected Global ID only."""

    from app.services.admin.admin_referral_scope_service import (
        selected_referral_logs,
    )

    try:
        return await selected_referral_logs(
            db,
            global_id=global_id,
            limit=limit,
            cursor=cursor,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("selected_referral_logs failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Временная ошибка журнала рефералов",
        ) from exc
