"""Real PostgreSQL квалификация объединённой release schema 0001."""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.models.base import Base
from app.release.database_contract import load_all_models
from sqlalchemy.engine import make_url

psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[2]
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


def test_clean_release_0001_создаёт_финальную_global_id_schema() -> None:
    base = _base_url_or_skip()
    database = f"efhc_squash_{uuid.uuid4().hex[:12]}"
    admin_url, sqlalchemy_url, psycopg_url = _urls(base, database)
    _create_database(admin_url, database)
    try:
        command.upgrade(_config(sqlalchemy_url), "head")
        with psycopg.connect(psycopg_url) as connection:
            revision = connection.execute(
                "SELECT version_num FROM efhc_core.alembic_version"
            ).fetchone()[0]
            assert revision == "0001"
            columns = {
                row[0]
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='efhc_core' AND table_name='users'"
                ).fetchall()
            }
            assert "global_id" in columns
            assert not {"id", "user_id", "tg_id", "ton_wallet"} & columns
            fk_count = connection.execute(
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
            assert int(fk_count) == _expected_fk_count()
            sequence = connection.execute(
                "SELECT pg_get_serial_sequence('efhc_core.users','global_id')"
            ).fetchone()[0]
            assert sequence == "efhc_core.users_global_id_seq"
            control = connection.execute(
                "SELECT to_regclass('efhc_core.identity_migration_control')"
            ).fetchone()[0]
            assert control is None
            assert connection.execute(
                "SELECT to_regclass('efhc_core.identity_ownership_shadow_telemetry')"
            ).fetchone()[0] is None
            identity_table = connection.execute(
                "SELECT to_regclass('efhc_core.user_identities')"
            ).fetchone()[0]
            assert identity_table is not None
            identity_constraints = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = 'efhc_core.user_identities'::regclass
                    """
                ).fetchall()
            }
            assert {
                "pk_user_identities",
                "fk_user_identities_global_id_users_global_id",
                "uq_user_identities_provider_tenant_subject",
                "ck_user_identities_global_id_range",
            } <= identity_constraints
            identity_fk_target = connection.execute(
                """
                SELECT a.attname
                FROM pg_constraint c
                JOIN pg_attribute a
                  ON a.attrelid = c.confrelid
                 AND a.attnum = ANY(c.confkey)
                WHERE c.conname =
                    'fk_user_identities_global_id_users_global_id'
                """
            ).fetchone()[0]
            assert identity_fk_target == "global_id"

            global_id = connection.execute(
                "INSERT INTO efhc_core.users DEFAULT VALUES "
                "RETURNING global_id"
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO efhc_core.efhc_transfers_log "
                "(tg_id, global_id, amount, direction, balance_type, "
                "reason, idempotency_key) "
                "VALUES (%s, %s, %s, 'credit', 'main', "
                "'schema_freeze_test', %s)",
                (
                    8_991_000_000_001,
                    global_id,
                    Decimal("1.00000000"),
                    f"schema-freeze-{database}",
                ),
            )
            stored = connection.execute(
                "SELECT amount FROM efhc_core.efhc_transfers_log "
                "WHERE global_id=%s AND reason='schema_freeze_test'",
                (global_id,),
            ).fetchone()[0]
            assert Decimal(stored) == Decimal("1.00000000")
            connection.rollback()
    finally:
        _drop_database(admin_url, database)
