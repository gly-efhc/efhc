"""Полная PostgreSQL-квалификация frozen release schema ``0001``.

Тесты создают отдельную чистую БД, выполняют реальный ``alembic upgrade head``
и сверяют physical catalog с замороженным ``RELEASE_METADATA``. Это не smoke:
проверяются таблицы, колонки, PK, UNIQUE, FK, CHECK, indexes, BIGINT/identity
инварианты и повторный upgrade как noop.
"""

from __future__ import annotations

import importlib
import os
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.models.base import Base
from app.release.database_contract import (
    EXPECTED_TABLE_COUNT,
    expected_tables,
    load_all_models,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url

psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[2]
RETIRED_TABLES = {
    "panels_archive",
    "ranks_snapshots",
    "ranks_top_cache",
    "ranks_user_snapshots",
}
RETIRED_USER_COLUMNS = {"id", "user_id", "tg_id", "ton_wallet"}
REQUIRED_BIGINT_COLUMNS = {
    ("efhc_admin", "efhc_sale_packages", "id"),
    ("efhc_core", "app_settings", "id"),
    ("efhc_core", "efhc_transfers_log", "id"),
    ("efhc_core", "payment_intents", "package_id"),
    ("efhc_core", "referral_links", "id"),
    ("efhc_core", "scheduler_task_log", "id"),
    ("efhc_core", "shop_items", "id"),
    ("efhc_core", "shop_orders", "id"),
    ("efhc_core", "user_cosmetics", "id"),
    ("efhc_core", "user_skins", "id"),
    ("efhc_core", "users", "global_id"),
    ("efhc_core", "wallet_bindings", "id"),
    ("efhc_core", "wallet_proof_token_uses", "id"),
}


def _frozen_release_metadata() -> sa.MetaData:
    module = importlib.import_module(
        "migrations.versions.0001_initial_release_schema"
    )
    metadata = getattr(module, "RELEASE_METADATA", None)
    if not isinstance(metadata, sa.MetaData):
        raise AssertionError("0001 RELEASE_METADATA отсутствует")
    return metadata


def _compiled_type(value: sa.types.TypeEngine[Any]) -> str:
    return " ".join(
        str(value.compile(dialect=postgresql.dialect())).upper().split()
    )


def _assert_physical_matches_frozen_metadata(sqlalchemy_url: str) -> None:
    metadata = _frozen_release_metadata()
    engine = sa.create_engine(sqlalchemy_url)
    try:
        inspector = sa.inspect(engine)
        actual_tables = {
            (schema, table)
            for schema in ("efhc_core", "efhc_admin")
            for table in inspector.get_table_names(schema=schema)
            if table != "alembic_version"
        }
        expected_tables_local = {
            (str(table.schema or ""), str(table.name))
            for table in metadata.sorted_tables
            if table.schema in {"efhc_core", "efhc_admin"}
        }
        assert actual_tables == expected_tables_local

        expected_native_enums: dict[tuple[str, str], tuple[str, ...]] = {}
        for table in metadata.sorted_tables:
            for column in table.columns:
                if not isinstance(column.type, sa.Enum):
                    continue
                if not bool(column.type.native_enum) or not column.type.name:
                    continue
                enum_schema = str(column.type.schema or table.schema or "")
                expected_native_enums[(enum_schema, str(column.type.name))] = (
                    tuple(str(value) for value in column.type.enums)
                )

        actual_native_enums: dict[tuple[str, str], tuple[str, ...]] = {}
        for enum_schema in {"efhc_core", "efhc_admin"}:
            for item in inspector.get_enums(schema=enum_schema):
                enum_name = str(item.get("name") or "")
                labels = tuple(str(value) for value in item.get("labels") or ())
                actual_native_enums[(enum_schema, enum_name)] = labels

        for enum_key, expected_labels in expected_native_enums.items():
            assert enum_key in actual_native_enums, (*enum_key, "enum_missing")
            assert actual_native_enums[enum_key] == expected_labels, (
                *enum_key,
                "enum_labels",
            )

        for table in metadata.sorted_tables:
            schema = str(table.schema or "")
            if schema not in {"efhc_core", "efhc_admin"}:
                continue
            name = str(table.name)

            actual_columns = {
                str(column["name"]): column
                for column in inspector.get_columns(name, schema=schema)
            }
            assert set(actual_columns) == set(table.c.keys()), (schema, name)
            for column in table.columns:
                actual = actual_columns[column.name]
                assert bool(actual["nullable"]) == bool(column.nullable), (
                    schema,
                    name,
                    column.name,
                    "nullable",
                )
                assert _compiled_type(actual["type"]) == _compiled_type(
                    column.type
                ), (schema, name, column.name, actual["type"], column.type)

            actual_pk = inspector.get_pk_constraint(name, schema=schema)
            expected_pk_columns = tuple(
                column.name for column in table.primary_key.columns
            )
            assert tuple(actual_pk.get("constrained_columns") or ()) == (
                expected_pk_columns
            ), (schema, name, "pk_columns")
            if table.primary_key.name:
                assert actual_pk.get("name") == table.primary_key.name

            expected_unique_constraints = [
                constraint
                for constraint in table.constraints
                if isinstance(constraint, sa.UniqueConstraint)
                and tuple(column.name for column in constraint.columns)
                != expected_pk_columns
            ]
            actual_unique_items = inspector.get_unique_constraints(
                name, schema=schema
            )
            expected_unique_columns = {
                tuple(column.name for column in constraint.columns)
                for constraint in expected_unique_constraints
            }
            actual_unique_columns = {
                tuple(item.get("column_names") or ())
                for item in actual_unique_items
            }
            assert actual_unique_columns == expected_unique_columns, (
                schema,
                name,
                "unique_columns",
            )
            actual_unique_names = {
                str(item.get("name"))
                for item in actual_unique_items
                if item.get("name")
            }
            assert {
                str(constraint.name)
                for constraint in expected_unique_constraints
                if constraint.name
            } <= actual_unique_names

            expected_fk_constraints = list(table.foreign_key_constraints)
            actual_fk_items = inspector.get_foreign_keys(name, schema=schema)
            expected_fk_logical = {
                (
                    tuple(column.name for column in constraint.columns),
                    tuple(
                        (
                            str(element.column.table.schema or schema),
                            str(element.column.table.name),
                            str(element.column.name),
                        )
                        for element in constraint.elements
                    ),
                )
                for constraint in expected_fk_constraints
            }
            actual_fk_logical = {
                (
                    tuple(item.get("constrained_columns") or ()),
                    tuple(
                        (
                            str(item.get("referred_schema") or schema),
                            str(item.get("referred_table") or ""),
                            str(column),
                        )
                        for column in (item.get("referred_columns") or ())
                    ),
                )
                for item in actual_fk_items
            }
            assert actual_fk_logical == expected_fk_logical, (
                schema,
                name,
                "foreign_keys",
            )
            actual_fk_names = {
                str(item.get("name"))
                for item in actual_fk_items
                if item.get("name")
            }
            assert {
                str(constraint.name)
                for constraint in expected_fk_constraints
                if constraint.name
            } <= actual_fk_names

            expected_check_constraints = [
                constraint
                for constraint in table.constraints
                if isinstance(constraint, sa.CheckConstraint)
                and not (
                    bool(getattr(constraint, "_type_bound", False))
                    and any(
                        isinstance(column.type, sa.Enum)
                        and bool(column.type.native_enum)
                        for column in constraint.columns
                    )
                )
            ]
            actual_check_items = inspector.get_check_constraints(
                name, schema=schema
            )
            assert len(actual_check_items) == len(expected_check_constraints), (
                schema,
                name,
                "check_count",
            )
            actual_check_names = {
                str(item.get("name"))
                for item in actual_check_items
                if item.get("name")
            }
            assert {
                str(constraint.name)
                for constraint in expected_check_constraints
                if constraint.name
            } <= actual_check_names

            expected_indexes = {
                (index.name, bool(index.unique))
                for index in table.indexes
                if index.name
            }
            actual_indexes = {
                (item.get("name"), bool(item.get("unique")))
                for item in inspector.get_indexes(name, schema=schema)
                if item.get("name") and not item.get("duplicates_constraint")
            }
            assert actual_indexes == expected_indexes, (schema, name, "indexes")
    finally:
        engine.dispose()


def _base_url_or_skip() -> str:
    url = os.getenv("SYNC_DATABASE_URL") or os.getenv("DATABASE_URL")
    if url and str(url).startswith("postgresql"):
        return str(url)
    message = "Тест требует реальный PostgreSQL"
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        pytest.fail(message)
    pytest.skip(message)


def _to_psycopg(url: str) -> str:
    return (
        url.replace("postgresql+psycopg://", "postgresql://")
        .replace("postgresql+psycopg2://", "postgresql://")
        .replace("postgresql+asyncpg://", "postgresql://")
    )


def _config(url: str) -> Config:
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _urls(base_url: str, database: str) -> tuple[str, str, str]:
    parsed = make_url(base_url)
    admin = parsed.set(database="postgres")
    target = parsed.set(database=database)
    sqlalchemy_url = target.render_as_string(hide_password=False)
    return (
        _to_psycopg(admin.render_as_string(hide_password=False)),
        sqlalchemy_url,
        _to_psycopg(sqlalchemy_url),
    )


def _create_database(admin_url: str, database: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{database}"')


def _drop_database(admin_url: str, database: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (database,),
        )
        connection.execute(f'DROP DATABASE IF EXISTS "{database}"')


def _expected_fk_count() -> int:
    load_all_models()
    return sum(
        1
        for table in Base.metadata.tables.values()
        for constraint in table.foreign_key_constraints
        if any(
            element.target_fullname == "efhc_core.users.global_id"
            for element in constraint.elements
        )
    )


def _fk_count(connection: object) -> int:
    return int(
        connection.execute(  # type: ignore[attr-defined]
            """
            SELECT count(*)
            FROM pg_constraint c
            JOIN pg_attribute a
              ON a.attrelid = c.confrelid
             AND a.attnum = ANY(c.confkey)
            WHERE c.contype='f'
              AND c.confrelid='efhc_core.users'::regclass
              AND a.attname='global_id'
            """
        ).fetchone()[0]
    )


def _physical_tables(connection: object) -> set[tuple[str, str]]:
    rows = connection.execute(  # type: ignore[attr-defined]
        """
        SELECT table_schema, table_name
          FROM information_schema.tables
         WHERE table_schema IN ('efhc_core', 'efhc_admin')
           AND table_type='BASE TABLE'
           AND table_name <> 'alembic_version'
        """
    ).fetchall()
    return {(str(schema), str(table)) for schema, table in rows}


def test_0001_создаёт_exact_greenfield_schema() -> None:
    base = _base_url_or_skip()
    database = f"efhc_clean_{uuid.uuid4().hex[:12]}"
    admin_url, sqlalchemy_url, psycopg_url = _urls(base, database)
    _create_database(admin_url, database)
    try:
        command.upgrade(_config(sqlalchemy_url), "head")
        _assert_physical_matches_frozen_metadata(sqlalchemy_url)
        with psycopg.connect(psycopg_url) as connection:
            revision = connection.execute(
                "SELECT version_num FROM efhc_core.alembic_version"
            ).fetchone()[0]
            assert revision == "0001"

            physical = _physical_tables(connection)
            assert len(physical) == EXPECTED_TABLE_COUNT
            assert physical == expected_tables()
            assert not {
                table
                for schema, table in physical
                if schema == "efhc_core" and table in RETIRED_TABLES
            }

            user_columns = {
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT column_name
                      FROM information_schema.columns
                     WHERE table_schema='efhc_core'
                       AND table_name='users'
                    """
                ).fetchall()
            }
            assert "global_id" in user_columns
            assert not (RETIRED_USER_COLUMNS & user_columns)
            assert {
                "rank_position",
                "rank_score_kwh",
                "rank_calculated_at",
            } <= user_columns

            primary_columns = {
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT kcu.column_name
                      FROM information_schema.table_constraints tc
                      JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name=kcu.constraint_name
                       AND tc.table_schema=kcu.table_schema
                     WHERE tc.table_schema='efhc_core'
                       AND tc.table_name='users'
                       AND tc.constraint_type='PRIMARY KEY'
                    """
                ).fetchall()
            }
            assert primary_columns == {"global_id"}

            bigint_columns = {
                (str(schema), str(table), str(column))
                for schema, table, column in connection.execute(
                    """
                    SELECT table_schema, table_name, column_name
                      FROM information_schema.columns
                     WHERE data_type='bigint'
                       AND table_schema IN ('efhc_core', 'efhc_admin')
                    """
                ).fetchall()
            }
            assert bigint_columns >= REQUIRED_BIGINT_COLUMNS
            assert _fk_count(connection) == _expected_fk_count()
    finally:
        _drop_database(admin_url, database)


def test_0001_second_upgrade_остаётся_idempotent_noop() -> None:
    base = _base_url_or_skip()
    database = f"efhc_repeat_{uuid.uuid4().hex[:12]}"
    admin_url, sqlalchemy_url, psycopg_url = _urls(base, database)
    _create_database(admin_url, database)
    try:
        config = _config(sqlalchemy_url)
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with psycopg.connect(psycopg_url) as connection:
            assert _physical_tables(connection) == expected_tables()
            revision = connection.execute(
                "SELECT version_num FROM efhc_core.alembic_version"
            ).fetchone()[0]
            assert revision == "0001"
    finally:
        _drop_database(admin_url, database)
