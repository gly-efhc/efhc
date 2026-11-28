"""backend/app/services/skins_service.py

Домен «Skins»: каталог progression-only и активация.

Важно:
- Каталог строится автоматически по наличию файлов
  (см. standards/skins_catalog.py) — без ручного кода
  на каждую картинку.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.errors_core import EFHCError
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.models.skins_models import UserCosmetics, UserSkin
from app.models.user_models import User
from app.standards.skins_catalog import build_catalog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_LEVEL_THRESHOLDS: tuple[tuple[int, Decimal], ...] = (
    (1, Decimal("0")),
    (2, Decimal("100")),
    (3, Decimal("300")),
    (4, Decimal("600")),
    (5, Decimal("1000")),
    (6, Decimal("2000")),
    (7, Decimal("3500")),
    (8, Decimal("5000")),
    (9, Decimal("7500")),
    (10, Decimal("10000")),
    (11, Decimal("15000")),
    (12, Decimal("20000")),
)


def _d8(x: str | Decimal) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.00000001"))


def _level_from_total(total_generated_kwh: str | Decimal) -> int:
    total = Decimal(str(total_generated_kwh or "0"))
    best = 1
    for level, min_kwh in _LEVEL_THRESHOLDS:
        if total >= min_kwh:
            best = level
    return int(best)


def _available_skin_ids_for_level(level: int) -> list[int]:
    clamped = min(max(int(level), 1), 12)
    return list(range(1, clamped + 1))


async def _current_level(
    db: AsyncSession,
    *,
    owner: NonFinancialReadOwner,
) -> int:
    selector = User.global_id == int(owner.global_id)
    res = await db.execute(
        select(User.total_generated_kwh).where(selector)
    )
    total = res.scalar_one_or_none() or "0"
    return _level_from_total(str(total))


async def _read_cosmetics_row(
    db: AsyncSession,
    *,
    owner: NonFinancialReadOwner,
) -> UserCosmetics | None:
    selector = UserCosmetics.global_id == int(owner.global_id)
    res = await db.execute(select(UserCosmetics).where(selector))
    return res.scalar_one_or_none()


async def _sync_active_skin_id(
    db: AsyncSession,
    *,
    owner: NonFinancialReadOwner,
    available_skin_ids: list[int],
) -> int:
    fallback_skin_id = (
        int(available_skin_ids[-1]) if available_skin_ids else 1
    )
    row = await _read_cosmetics_row(db, owner=owner)
    current_skin_id = (
        int(row.active_skin_id) if row else fallback_skin_id
    )

    if current_skin_id in available_skin_ids and row is not None:
        return current_skin_id

    synced_skin_id = (
        current_skin_id
        if current_skin_id in available_skin_ids
        else fallback_skin_id
    )

    if row is None:
        db.add(
            UserCosmetics(
                global_id=int(owner.global_id),
                tg_id=owner.provider_tg_id,
                active_skin_id=int(synced_skin_id),
            )
        )
    else:
        row.active_skin_id = int(synced_skin_id)

    await db.commit()
    return int(synced_skin_id)


def get_catalog() -> list[dict[str, Any]]:
    # без кэша: каталог должен подхватывать новые файлы
    return [i.__dict__ for i in build_catalog()]


async def get_my(
    db: AsyncSession,
    *,
    owner: NonFinancialReadOwner,
) -> dict[str, Any]:
    level = await _current_level(db, owner=owner)
    available_skin_ids = _available_skin_ids_for_level(level)
    active_skin_id = await _sync_active_skin_id(
        db,
        owner=owner,
        available_skin_ids=available_skin_ids,
    )

    selector = UserSkin.global_id == int(owner.global_id)
    res = await db.execute(
        select(UserSkin)
        .where(selector)
        .order_by(UserSkin.skin_id.asc())
    )
    owned_rows = res.scalars().all()
    owned = [
        {"skin_id": int(r.skin_id), "purchased_at": r.purchased_at}
        for r in owned_rows
    ]
    return {"active_skin_id": int(active_skin_id), "owned": owned}


async def get_switcher(
    db: AsyncSession,
    *,
    owner: NonFinancialReadOwner,
) -> dict[str, Any]:
    level = await _current_level(db, owner=owner)
    available_skin_ids = _available_skin_ids_for_level(level)
    active_skin_id = await _sync_active_skin_id(
        db,
        owner=owner,
        available_skin_ids=available_skin_ids,
    )
    catalog = sorted(
        [i for i in get_catalog() if 1 <= int(i["skin_id"]) <= 12],
        key=lambda item: int(item["skin_id"]),
    )
    items = []
    for item in catalog:
        sid = int(item["skin_id"])
        items.append(
            {
                "skin_id": sid,
                "title": str(item["title"]),
                "asset_path": str(item["asset_path"]),
                "is_unlocked": sid in available_skin_ids,
                "is_active": sid == int(active_skin_id),
            }
        )
    return {
        "current_level": int(level),
        "available_skin_ids": [int(sid) for sid in available_skin_ids],
        "active_skin_id": int(active_skin_id),
        "items": items,
    }


async def buy_skin(
    db: AsyncSession,
    *,
    global_id: int,
    skin_id: int,
    idempotency_key: str,
) -> None:
    """Compatibility facade: current release запрещает skin commerce."""

    _ = (db, global_id, skin_id, idempotency_key)
    raise EFHCError(
        "SKIN_COMMERCE_DISABLED",
        detail="Current skin availability is progression-only",
    )


async def _ensure_owned(
    db: AsyncSession,
    *,
    global_id: int,
    skin_id: int,
) -> None:
    canonical_owner = int(global_id)
    res = await db.execute(
        select(UserSkin).where(
            UserSkin.global_id == canonical_owner,
            UserSkin.skin_id == int(skin_id),
        )
    )
    if res.scalar_one_or_none():
        return
    db.add(
        UserSkin(
            global_id=canonical_owner,
            tg_id=None,
            skin_id=int(skin_id),
        )
    )


async def activate_skin(
    db: AsyncSession,
    *,
    owner: NonFinancialReadOwner,
    skin_id: int,
) -> None:
    sid = int(skin_id)
    if sid < 1:
        raise EFHCError(
            "SKIN_NOT_FOUND",
            detail="Skin id is out of range",
        )

    level = await _current_level(db, owner=owner)
    available_skin_ids = _available_skin_ids_for_level(level)
    if sid not in available_skin_ids:
        raise EFHCError(
            "SKIN_NOT_UNLOCKED",
            detail="Skin not unlocked by progression",
        )

    row = await _read_cosmetics_row(db, owner=owner)
    if row is None:
        db.add(
            UserCosmetics(
                global_id=int(owner.global_id),
                tg_id=owner.provider_tg_id,
                active_skin_id=sid,
            )
        )
    else:
        row.active_skin_id = sid
    await db.commit()

