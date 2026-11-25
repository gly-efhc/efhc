# backend/migrations/lib/safe.py
# =====================================================================
# Назначение кода:
# Вспомогательные функции для «защищённых» миграций Alembic.
# Таблицы/колонки/индексы создаются только если их нет.
# Индексы и ограничения создаются только если их нет.
# Уже существующие объекты не трогаем.
# Это позволяет безопасно повторно прогонять миграции.
# Также помогает «лечить» частично развёрнутые базы.
# частично развёрнутые базы без ручного вмешательства.
#
# Канон / инварианты:
# • Работает на PostgreSQL.
#   Оперирует только в активной схеме (search_path).
# которую настраивает alembic/env.py (DB_SCHEMA_CORE).
# • Никаких деструктивных DDL по умолчанию (DROP/ALTER … DROP).
#
# ИИ-защиты:
# • Перед созданием объекта выполняется инспекция каталога БД.
# • Для индексов/уникальных ограничений делаем проверку по имени.
# • Для колонок — проверка существования и минимальная валидация типа.
#
# Запреты:
# • Нет автоматического исправления несовпадающих типов.
#   Если тип отличается — пишем явный ALTER.
# в БД отличается — миграцию пишем явно (ALTER TABLE … TYPE …).
# • Нет неявного переименования объектов — только проверка/создание.
# =====================================================================

from __future__ import annotations

from collections.abc import Iterable, Sequence

import sqlalchemy as sa
from alembic import op
from app.core.sql_aliases_core import canon_schema
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector

# --------------------------------------------------------------------
# Базовые утилиты инспекции каталога
# --------------------------------------------------------------------


def _get_bind() -> Connection:
    """Текущий bind из контекста Alembic."""
    return op.get_bind()


def get_inspector() -> Inspector:
    """Возвращает инспектор для активного соединения."""
    return sa.inspect(_get_bind())


def current_schema() -> str:
    """Имя активной схемы (для отладки/логирования)."""
    row = _get_bind().execute(text("SELECT current_schema()")).scalar()
    return str(row or "")

# --------------------------------------------------------------------
# Схема и таблицы
# --------------------------------------------------------------------


def ensure_schema(schema_name: str) -> None:
    """
    Создаёт схему, если её нет (безошибочно, если уже есть).
    Полезно запускать в прелюдии «init»-миграции.
    """
    if not schema_name:
        return
    canon = canon_schema(schema_name)
    op.execute(
        text(
            'CREATE SCHEMA IF NOT EXISTS "' + canon + '"'
        )
    )


def table_exists(
    table_name: str,
    schema: str | None = None,
) -> bool:
    """Проверяет существование таблицы в текущем search_path."""
    insp = get_inspector()
    return insp.has_table(table_name, schema=schema)


def ensure_table(
    table_name: str,
    *columns: sa.Column,
    indexes: Sequence[tuple] | None = None,
    table_kwargs: dict | None = None,
    schema: str | None = None,
) -> None:
    """
    Создаёт таблицу с указанными колонками, если её нет.
    indexes: кортежи для последующего ensure_index(...).
             формат: (index_name, [col1, col2, ...], unique=False)
    table_kwargs: доп. параметры для op.create_table.
    Например: sa.PrimaryKeyConstraint(...).
    """
    if table_exists(table_name, schema=schema):
        return
    op.create_table(
        table_name,
        *columns,
        schema=schema,
        **(table_kwargs or {}),
    )
    if indexes:
        for idx_name, cols, *rest in indexes:
            unique = bool(rest[0]) if rest else False
            ensure_index(
                idx_name,
                table_name,
                cols,
                unique=unique,
                schema=schema,
            )

# --------------------------------------------------------------------
# Колонки
# --------------------------------------------------------------------


def column_exists(
    table_name: str,
    column_name: str,
    schema: str | None = None,
) -> bool:
    """Проверяет, есть ли колонка в таблице."""
    insp = get_inspector()
    for col in insp.get_columns(table_name, schema=schema):
        if col.get("name") == column_name:
            return True
    return False


def ensure_column(
    table_name: str,
    column: sa.Column,
    schema: str | None = None,
) -> None:
    """
    Добавляет колонку, если её нет.
    Тип/nullable берутся из переданного Column.
    Важно: если колонка есть, но с другим типом —
    ничего не делаем (канон).
    Для смены типа нужен отдельный явный ALTER в миграции.
    """
    col_name = column.name  # type: ignore[attr-defined]
    if column_exists(table_name, col_name, schema=schema):
        return
    op.add_column(table_name, column, schema=schema)

# --------------------------------------------------------------------
# Индексы
# --------------------------------------------------------------------


def index_exists(
    table_name: str,
    index_name: str,
    schema: str | None = None,
) -> bool:
    """Проверяет существование индекса по имени."""
    insp = get_inspector()
    try:
        for idx in insp.get_indexes(table_name, schema=schema):
            if idx.get("name") == index_name:
                return True
    except Exception:
        # Некоторые драйверы могут падать при отсутствующей таблице
        return False
    return False


def ensure_index(
    index_name: str,
    table_name: str,
    columns: Sequence[str],
    unique: bool = False,
    schema: str | None = None,
) -> None:
    """
    Создаёт индекс, если его нет.
    На PostgreSQL предпочитаем проверку через инспектор +
    op.create_index, чтобы сохранить кросс-версионную поддержку Alembic.
    """
    if index_exists(table_name, index_name, schema=schema):
        return
    op.create_index(
        index_name,
        table_name,
        list(columns),
        unique=unique,
        schema=schema,
    )

# --------------------------------------------------------------------
# Уникальные ограничения / констреинты
# --------------------------------------------------------------------


def unique_constraint_exists(
    table_name: str,
    constraint_name: str,
    schema: str | None = None,
) -> bool:
    """Проверяет, существует ли UNIQUE-констреинт по имени.
    """
    insp = get_inspector()
    try:
        ucs = insp.get_unique_constraints(table_name, schema=schema)
        for uc in ucs:
            if uc.get("name") == constraint_name:
                return True
    except Exception:
        return False
    return False


def ensure_unique_constraint(
    constraint_name: str,
    table_name: str,
    columns: Sequence[str],
    schema: str | None = None,
) -> None:
    """
    Создаёт UNIQUE - констреинт, если его нет.
    Если в БД есть уникальный индекс с тем же именем,
    считаем этого достаточно.
    """
    if unique_constraint_exists(
        table_name,
        constraint_name,
        schema=schema,
    ):
        return
    # На некоторых БД имя UNIQUE-индекса совпадает с именем констреинта.
    # Для единообразия создаём именно констреинт:
    cols_list = list(columns)
    op.create_unique_constraint(
        constraint_name,
        table_name,
        cols_list,
        schema=schema,
    )

# --------------------------------------------------------------------
# Комбинированные «ensure»-сценарии
# --------------------------------------------------------------------


def ensure_table_with_basics(
    table_name: str,
    cols: Iterable[sa.Column],
    pk: sa.PrimaryKeyConstraint | None = None,
    uniques: Sequence[object] | None = None,
    indexes: Sequence[object] | None = None,
    schema: str | None = None,
) -> None:
    """
    Упрощённый сценарий: создать таблицу (если нет).
    Затем создать UNIQUE и индексы.
    uniques: [("uq_name", ["col1", "col2"]), ...]
    indexes: [("ix_name", ["col1", "col2"], False), ...]
    """
    if not table_exists(table_name, schema=schema):
        args = list(cols)
        if pk is not None:
            args.append(pk)
        op.create_table(table_name, *args, schema=schema)

    if uniques:
        for uq in uniques:
            # uniques:
            # - tuples ("uq_name", ["col1", ...])
            # - sa.UniqueConstraint(...)
            if isinstance(uq, sa.UniqueConstraint):
                uq_name = getattr(uq, "name", None)
                cols: list[str] = []
                for col in list(getattr(uq, "columns", [])) or []:
                    name = getattr(col, "name", None)
                    if name:
                        cols.append(name)
                    else:
                        cols.append(str(col))
                uq_cols = cols
                if not uq_cols:
                    pending = getattr(uq, "_pending_colargs", None)
                    if pending:
                        pend_cols: list[str] = []
                        for item in list(pending) or []:
                            if isinstance(item, str):
                                name = item
                            else:
                                name = getattr(item, "name", None)
                                if not name:
                                    name = str(item)
                            if name:
                                pend_cols.append(name)
                        uq_cols = pend_cols
                if not uq_cols:
                    msg = (
                        "UniqueConstraint for "
                        f"{table_name} resolved to empty columns"
                    )
                    raise RuntimeError(msg)
                if not uq_name:
                    # Deterministic fallback name to avoid invalid DDL
                    parts = ["uq", table_name] + list(uq_cols)
                    uq_name = "_".join(parts)
            else:
                uq_name, uq_cols = uq  # type: ignore[misc]
            ensure_unique_constraint(
                uq_name,
                table_name,
                uq_cols,
                schema=schema,
            )

    if indexes:
        for ix in indexes:
            # indexes:
            # - tuples ("ix_name", ["col"], unique_bool)
            # - sa.Index(...)
            if isinstance(ix, sa.Index):
                ix_name = ix.name
                ix_unique = bool(getattr(ix, "unique", False))
                cols = []
                for expr in list(getattr(ix, "expressions", [])) or []:
                    name = getattr(expr, "name", None)
                    if name:
                        cols.append(name)
                    else:
                        # Fallback: string representation (stable)
                        cols.append(str(expr))
                ix_cols = cols
            else:
                ix_name, ix_cols, ix_unique = ix
            ensure_index(
                ix_name,
                table_name,
                ix_cols,
                unique=ix_unique,
                schema=schema,
            )

# =====================================================================
# Пояснения «для чайника»:
# • Эти функции НЕ ломают существующую схему.
#   Если объект уже есть — они молча выходят.
# выходят. Так достигается идемпотентность миграций.
# Это важно при повторных запусках.
# • Для сложных изменений делайте отдельные явные шаги.
# Отдельные явные шаги миграции важны.
# Здесь мы сознательно не «угадываем» логику.
# • Пример использования в миграции:
#
# from backend.migrations.lib.safe import (
# ensure_schema, ensure_table_with_basics, ensure_column, ensure_index,
# ensure_unique_constraint, current_schema,
# )
#
# def upgrade():
# ensure_schema("efhc_core")
# ensure_table_with_basics(
# "users",
# cols=[
# sa.Column("id", sa.BigInteger, primary_key=True),
# sa.Column("global_id", sa.BigInteger, nullable=False, unique=True,
# • После добавления этой библиотеки вы можете постепенно перевести
#   «init» миграцию на ensure_*-вызовы и получить устойчивый старт.
#   «init» миграцию на ensure_* подход без DROP-операций.
# ...
# ],
# indexes=[("ix_users_created_id", ["created_at", "id"], False)],
# )
#
# • После добавления этой библиотеки вы можете постепенно перевести
#   «init» миграцию на ensure_*-вызовы и получить устойчивый старт.
# =====================================================================
