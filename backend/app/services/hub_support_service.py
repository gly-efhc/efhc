from __future__ import annotations

from typing import Any

from app.models.hub_links_models import HubLink
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SUPPORT_LINK_CODE_PREFIX = "support_"


def _public_support_link(link: HubLink) -> dict[str, Any]:
    return {
        "id": int(link.id),
        "title": link.title,
        "subtitle": link.subtitle,
        "url": link.url,
        "open_mode": link.open_mode,
        "icon_key": link.icon_key,
    }


async def list_active_support_links(
    db: AsyncSession,
) -> list[dict[str, Any]]:
    stmt = (
        select(HubLink)
        .where(
            HubLink.code.like(f"{SUPPORT_LINK_CODE_PREFIX}%"),
            HubLink.is_active.is_(True),
        )
        .order_by(HubLink.sort_order, HubLink.id)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_public_support_link(row) for row in rows]
