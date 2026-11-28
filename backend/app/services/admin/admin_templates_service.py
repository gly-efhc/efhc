from __future__ import annotations

from typing import Any

from app.models.system_templates_models import SystemTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get__all__templates(
    db: AsyncSession,
) -> list[dict[str, Any]]:
    rows = (
        (
            await db.execute(
                select(SystemTemplate).order_by(
                    SystemTemplate.key.asc()
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "key": row.key,
            "content": row.content,
            "description": row.description,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


async def update_template(
    db: AsyncSession,
    *,
    key: str,
    content: str | None,
) -> dict[str, Any] | None:
    row = await db.get(SystemTemplate, str(key))
    if row is None:
        return None
    row.content = content if content not in {"", None} else None
    await db.commit()
    await db.refresh(row)
    return {
        "key": row.key,
        "content": row.content,
        "description": row.description,
        "updated_at": row.updated_at,
    }
