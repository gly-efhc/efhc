from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from app.models.hub_links_models import HubLink
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def list_hub_links(
    db: AsyncSession,
    *,
    active_only: bool = False,
) -> Sequence[HubLink]:
    stmt = select(HubLink).order_by(HubLink.sort_order, HubLink.id)
    if active_only:
        stmt = stmt.where(HubLink.is_active.is_(True))
    res = await db.execute(stmt)
    return cast(list[HubLink], res.scalars().all())


async def get_hub_link_by_code(
    db: AsyncSession,
    *,
    code: str,
) -> HubLink | None:
    stmt = select(HubLink).where(HubLink.code == code)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def get_hub_link_by_id(
    db: AsyncSession,
    *,
    link_id: int,
) -> HubLink | None:
    stmt = select(HubLink).where(HubLink.id == int(link_id))
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def add_hub_link(
    db: AsyncSession,
    *,
    code: str,
    title: str,
    subtitle: str | None,
    url: str,
    target_kind: str,
    open_mode: str,
    sort_order: int,
    is_active: bool,
    icon_key: str | None,
) -> HubLink:
    obj = HubLink(
        code=code,
        title=title,
        subtitle=subtitle,
        url=url,
        target_kind=target_kind,
        open_mode=open_mode,
        sort_order=sort_order,
        is_active=is_active,
        icon_key=icon_key,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


async def save_hub_link(
    db: AsyncSession,
    *,
    link: HubLink,
) -> HubLink:
    db.add(link)
    await db.flush()
    await db.refresh(link)
    return link
