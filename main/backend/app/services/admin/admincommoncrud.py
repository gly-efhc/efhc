# backend/app/services/admin/admincommoncrud.py
# =====================================================================
# EFHC Bot — Admin Common CRUD
#
# Цель:
# • Сократить дублирование однотипных CRUD-операций в admin сервисах.
# • Дать единые утилиты пагинации/сортировки на SQL text().
#
# Канон:
# • Здесь нет бизнес-логики денег/банка.
# • Пользовательский идентификатор — только global_id.
# • Секреты/ключи не логируются.
# =====================================================================

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class Page:
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class AdminCommonCrud:
    """Базовые CRUD-хелперы для админ-сервисов."""

    @staticmethod
    async def fetch_one(
        db: AsyncSession,
        *,
        sql: str,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        r: Result = await db.execute(text(sql), dict(params or {}))
        row = r.mappings().first()
        return dict(row) if row else None

    @staticmethod
    async def fetch_all(
        db: AsyncSession,
        *,
        sql: str,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        r: Result = await db.execute(text(sql), dict(params or {}))
        return [dict(m) for m in r.mappings().all()]

    @staticmethod
    async def fetch_page(
        db: AsyncSession,
        *,
        items_sql: str,
        count_sql: str,
        params: Mapping[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page:
        p = dict(params or {})
        p.update({"limit": int(limit), "offset": int(offset)})

        total_r: Result = await db.execute(text(count_sql), p)
        total = int(total_r.scalar_one() or 0)

        items_r: Result = await db.execute(text(items_sql), p)
        items = [dict(m) for m in items_r.mappings().all()]

        return Page(
            items=items,
            total=total,
            limit=int(limit),
            offset=int(offset),
        )
