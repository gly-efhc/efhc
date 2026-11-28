from __future__ import annotations

from datetime import datetime

from app.deps import get_db, require_admin, require_admin_write
from app.services.admin.admin_templates_service import (
    get__all__templates,
    update_template,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/admin/templates",
    tags=["admin:templates"],
)


class TemplateOut(BaseModel):
    key: str
    content: str | None = None
    description: str
    updated_at: datetime


class TemplateUpdateIn(BaseModel):
    content: str | None = Field(default=None)


@router.get(
    "",
    response_model=list[TemplateOut],
    dependencies=[Depends(require_admin)],
)
async def list_templates_admin(
    db: AsyncSession = Depends(get_db),
) -> list[TemplateOut]:
    rows = await get__all__templates(db)
    return [TemplateOut(**row) for row in rows]


@router.put(
    "/{key}",
    response_model=TemplateOut,
    dependencies=[Depends(require_admin_write)],
)
async def update_template_admin(
    key: str,
    payload: TemplateUpdateIn,
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    row = await update_template(
        db,
        key=str(key),
        content=payload.content,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Шаблон не найден",
        )
    return TemplateOut(**row)
