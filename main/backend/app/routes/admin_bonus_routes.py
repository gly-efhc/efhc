"""Admin API раздела «Бонусы и начисления».

Раздел только читает активные журналы бонусов. Ручное начисление выполняется
через единый денежный маршрут ``POST /admin/transfer`` и не дублируется здесь.
"""

from __future__ import annotations

from datetime import datetime

from app.deps import get_db, require_admin
from app.identity.api_contract import ApiExternalGlobalId
from app.services.admin.admin_bonus_service import (
    AdminBonusActivity,
    AdminBonusesService,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin/bonuses", tags=["admin:bonuses"])


@router.get("", response_model=AdminBonusActivity)
async def admin_bonus_activity(
    source: str = Query(default="all", max_length=32),
    global_id: ApiExternalGlobalId | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _auth=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminBonusActivity:
    """Показать реальные бонусы из заданий, рефералов и ручных начислений."""

    try:
        return await AdminBonusesService.list_activity(
            db,
            source=source,
            global_id=(int(global_id) if global_id is not None else None),
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


__all__ = ["router"]
