from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.crud.admin.admin_hub_links_crud import (
    add_hub_link,
    get_hub_link_by_code,
    get_hub_link_by_id,
    list_hub_links,
    save_hub_link,
)
from app.models.hub_links_models import HubLink
from sqlalchemy.ext.asyncio import AsyncSession

SUPPORT_LINK_CODE_PREFIX = "support_"
SUPPORT_LINK_ALLOWED_SCHEMES = frozenset({"https", "tg", "mailto", "tel"})


class HubLinkAdminError(ValueError):
    """Validation/domain error for admin Hub links manager."""


def _is_support_code(code: str) -> bool:
    return str(code or "").strip().lower().startswith(
        SUPPORT_LINK_CODE_PREFIX
    )


def _reject_reserved_support_link(link: HubLink) -> None:
    if _is_support_code(link.code):
        raise HubLinkAdminError(
            "support links must use dedicated support endpoints"
        )


def _to_dict(link: HubLink) -> dict[str, Any]:
    return {
        "id": int(link.id),
        "code": link.code,
        "title": link.title,
        "subtitle": link.subtitle,
        "url": link.url,
        "target_kind": link.target_kind,
        "open_mode": link.open_mode,
        "sort_order": int(link.sort_order),
        "is_active": bool(link.is_active),
        "icon_key": link.icon_key,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    }


async def admin_list_hub_links(
    db: AsyncSession,
    *,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    rows = await list_hub_links(db, active_only=active_only)
    return [
        _to_dict(row)
        for row in rows
        if not _is_support_code(row.code)
    ]


async def admin_seed_hub_link_if_missing(
    db: AsyncSession,
    *,
    code: str,
    title: str,
    subtitle: str | None,
    url: str,
    target_kind: str,
    open_mode: str,
    sort_order: int,
    is_active: bool = True,
    icon_key: str | None = None,
) -> dict[str, Any]:
    existing = await get_hub_link_by_code(db, code=code)
    if existing is not None:
        return _to_dict(existing)

    created = await add_hub_link(
        db,
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
    return _to_dict(created)


async def admin_create_hub_link(
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
) -> dict[str, Any]:
    if _is_support_code(code):
        raise HubLinkAdminError(
            "support_ code namespace is reserved for support endpoints"
        )
    existing = await get_hub_link_by_code(db, code=code)
    if existing is not None:
        raise HubLinkAdminError(f"hub link code already exists: {code}")
    created = await add_hub_link(
        db,
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
    return _to_dict(created)


async def admin_update_hub_link(
    db: AsyncSession,
    *,
    link_id: int,
    title: str,
    subtitle: str | None,
    url: str,
    target_kind: str,
    open_mode: str,
    sort_order: int,
    is_active: bool,
    icon_key: str | None,
) -> dict[str, Any]:
    link = await get_hub_link_by_id(db, link_id=link_id)
    if link is None:
        raise HubLinkAdminError(f"hub link not found: {link_id}")
    _reject_reserved_support_link(link)
    link.title = title
    link.subtitle = subtitle
    link.url = url
    link.target_kind = target_kind
    link.open_mode = open_mode
    link.sort_order = int(sort_order)
    link.is_active = bool(is_active)
    link.icon_key = icon_key
    saved = await save_hub_link(db, link=link)
    return _to_dict(saved)


async def admin_toggle_hub_link(
    db: AsyncSession,
    *,
    link_id: int,
    is_active: bool,
) -> dict[str, Any]:
    link = await get_hub_link_by_id(db, link_id=link_id)
    if link is None:
        raise HubLinkAdminError(f"hub link not found: {link_id}")
    _reject_reserved_support_link(link)
    link.is_active = bool(is_active)
    saved = await save_hub_link(db, link=link)
    return _to_dict(saved)


async def admin_reorder_hub_links(
    db: AsyncSession,
    *,
    items: list[dict[str, int]],
) -> list[dict[str, Any]]:
    changed: list[HubLink] = []
    for item in items:
        link = await get_hub_link_by_id(db, link_id=int(item["id"]))
        if link is None:
            raise HubLinkAdminError(f"hub link not found: {item['id']}")
        _reject_reserved_support_link(link)
        link.sort_order = int(item["sort_order"])
        changed.append(link)
    for link in changed:
        await save_hub_link(db, link=link)
    rows = await list_hub_links(db, active_only=False)
    return [
        _to_dict(row)
        for row in rows
        if not _is_support_code(row.code)
    ]


def _require_support_code(code: str) -> str:
    normalized = str(code or "").strip().lower()
    if not normalized.startswith(SUPPORT_LINK_CODE_PREFIX):
        raise HubLinkAdminError(
            "support link code must start with support_"
        )
    return normalized


def _validate_support_url(url: str) -> str:
    normalized = str(url or "").strip()
    scheme = urlsplit(normalized).scheme.lower()
    if scheme not in SUPPORT_LINK_ALLOWED_SCHEMES:
        raise HubLinkAdminError(
            "support link URL scheme is not allowed"
        )
    return normalized


def _require_support_link(link: HubLink) -> None:
    _require_support_code(link.code)


async def admin_list_support_links(
    db: AsyncSession,
    *,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    rows = await list_hub_links(db, active_only=active_only)
    return [
        _to_dict(row)
        for row in rows
        if row.code.startswith(SUPPORT_LINK_CODE_PREFIX)
    ]


async def admin_create_support_link(
    db: AsyncSession,
    *,
    code: str,
    title: str,
    subtitle: str | None,
    url: str,
    sort_order: int,
    is_active: bool,
    icon_key: str | None,
) -> dict[str, Any]:
    normalized_code = _require_support_code(code)
    normalized_url = _validate_support_url(url)
    existing = await get_hub_link_by_code(db, code=normalized_code)
    if existing is not None:
        raise HubLinkAdminError(
            f"support link code already exists: {normalized_code}"
        )
    created = await add_hub_link(
        db,
        code=normalized_code,
        title=title,
        subtitle=subtitle,
        url=normalized_url,
        target_kind="external_url",
        open_mode="external_browser",
        sort_order=sort_order,
        is_active=is_active,
        icon_key=icon_key,
    )
    return _to_dict(created)


async def admin_update_support_link(
    db: AsyncSession,
    *,
    link_id: int,
    title: str,
    subtitle: str | None,
    url: str,
    sort_order: int,
    is_active: bool,
    icon_key: str | None,
) -> dict[str, Any]:
    link = await get_hub_link_by_id(db, link_id=link_id)
    if link is None:
        raise HubLinkAdminError(f"support link not found: {link_id}")
    _require_support_link(link)
    link.title = title
    link.subtitle = subtitle
    link.url = _validate_support_url(url)
    link.target_kind = "external_url"
    link.open_mode = "external_browser"
    link.sort_order = int(sort_order)
    link.is_active = bool(is_active)
    link.icon_key = icon_key
    saved = await save_hub_link(db, link=link)
    return _to_dict(saved)


async def admin_toggle_support_link(
    db: AsyncSession,
    *,
    link_id: int,
    is_active: bool,
) -> dict[str, Any]:
    link = await get_hub_link_by_id(db, link_id=link_id)
    if link is None:
        raise HubLinkAdminError(f"support link not found: {link_id}")
    _require_support_link(link)
    link.is_active = bool(is_active)
    saved = await save_hub_link(db, link=link)
    return _to_dict(saved)


async def admin_reorder_support_links(
    db: AsyncSession,
    *,
    items: list[dict[str, int]],
) -> list[dict[str, Any]]:
    changed: list[HubLink] = []
    for item in items:
        link = await get_hub_link_by_id(db, link_id=int(item["id"]))
        if link is None:
            raise HubLinkAdminError(
                f"support link not found: {item['id']}"
            )
        _require_support_link(link)
        link.sort_order = int(item["sort_order"])
        changed.append(link)
    for link in changed:
        await save_hub_link(db, link=link)
    return await admin_list_support_links(db, active_only=False)

