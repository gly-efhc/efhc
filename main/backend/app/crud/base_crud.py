# backend/app/crud/base_crud.py
# =====================================================================
# Назначение кода:
# Базовый CRUD для операций SQLAlchemy (async). Используется
# как строительный блок для доменных CRUD.
#
# Канон/инварианты:
# • CRUD НЕ делает commit()/rollback() — транзакциями управляет сервис.
# • CRUD НЕ содержит денежной логики (балансы/банк/лимиты — сервисы).
# • Списки предпочтительно курсорные (по id), без OFFSET.
# =====================================================================

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, Protocol, TypeVar, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class _HasId(Protocol):
    id: Any


T = TypeVar("T", bound=_HasId)


class BaseCRUD(Generic[T]):
    """Минимальный безопасный CRUD. Доменные CRUD могут расширять."""

    def __init__(self, model: type[T]):
        """Создаёт CRUD-обёртку над моделью."""
        self.model = model

    async def get(self, db: AsyncSession, pk: Any) -> T | None:
        """Возвращает объект по первичному ключу."""
        obj = await db.get(self.model, pk)
        return cast(T | None, obj)

    async def get_many_by_ids(
        self,
        db: AsyncSession,
        ids: Sequence[Any],
    ) -> list[T]:
        """Возвращает список объектов по списку id."""
        if not ids:
            return []
        model_id = self.model.id
        stmt = select(self.model).where(model_id.in_(list(ids)))
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def create(self, db: AsyncSession, obj: T) -> T:
        """Добавляет объект в сессию (без commit)."""
        db.add(obj)
        return obj

    async def delete(self, db: AsyncSession, obj: T) -> None:
        """Удаляет объект из сессии (без commit)."""
        await db.delete(obj)
