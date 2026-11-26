"""Real PostgreSQL contract extended domain ownership пакета 1628."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

psycopg = pytest.importorskip("psycopg")


ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skip(
        reason=(
            "Исторический pre-squash переход удалён; "
            "final schema проверяет release 0001"
        )
    ),
]


def _to_psycopg_url(url: str) -> str:
    return (
        url.replace("postgresql+psycopg://", "postgresql://")
        .replace("postgresql+psycopg2://", "postgresql://")
        .replace("postgresql+asyncpg://", "postgresql://")
    )


def _database_url_or_skip() -> str:
    url = os.getenv("SYNC_DATABASE_URL") or os.getenv("DATABASE_URL")
    if url and str(url).startswith("postgresql"):
        return str(url)
    message = "Тест требует реальный PostgreSQL"
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        pytest.fail(message)
    pytest.skip(message)


def _config(url: str) -> Config:
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _set_environment(url: str) -> dict[str, str | None]:
    names = (
        "DATABASE_URL",
        "SYNC_DATABASE_URL",
        "ASYNC_DATABASE_URL",
        "PSYCOPG_URL",
    )
    previous = {name: os.getenv(name) for name in names}
    os.environ["DATABASE_URL"] = url
    os.environ["SYNC_DATABASE_URL"] = url
    os.environ["ASYNC_DATABASE_URL"] = url
    os.environ["PSYCOPG_URL"] = _to_psycopg_url(url)
    return previous


def _restore_environment(previous: dict[str, str | None]) -> None:
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def test_0012_extended_owner_contract_на_postgresql() -> None:
    base_url = _database_url_or_skip()
    parsed = make_url(base_url)
    database = f"extended_owner_1628_{uuid.uuid4().hex[:12]}"
    admin_url = parsed.set(database="postgres")
    test_url = parsed.set(database=database)
    admin_psycopg = _to_psycopg_url(
        admin_url.render_as_string(hide_password=False)
    )
    test_sqlalchemy = test_url.render_as_string(hide_password=False)
    test_psycopg = _to_psycopg_url(test_sqlalchemy)

    with psycopg.connect(admin_psycopg, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{database}"')

    previous = _set_environment(test_sqlalchemy)
    try:
        command.upgrade(_config(test_sqlalchemy), "0012")
        with psycopg.connect(test_psycopg, autocommit=True) as connection:
            revision = connection.execute(
                "SELECT version_num FROM efhc_core.alembic_version"
            ).fetchone()[0]
            assert revision == "0012"

            global_id = int(
                connection.execute(
                    """
                    INSERT INTO efhc_core.users (global_id)
                    VALUES (928000001)
                    RETURNING global_id
                    """
                ).fetchone()[0]
            )
            second_global_id = int(
                connection.execute(
                    """
                    INSERT INTO efhc_core.users (global_id)
                    VALUES (928000002)
                    RETURNING global_id
                    """
                ).fetchone()[0]
            )

            connection.execute(
                """
                INSERT INTO efhc_core.shop_orders (global_id, type, status)
                VALUES (928000001, 'NFT', 'PENDING')
                """
            )
            connection.execute(
                """
                INSERT INTO efhc_core.user_skins (global_id, skin_id)
                VALUES (928000001, 2)
                """
            )
            connection.execute(
                """
                INSERT INTO efhc_core.user_cosmetics (
                    global_id, active_skin_id
                ) VALUES (928000001, 2)
                """
            )

            assert connection.execute(
                "SELECT global_id FROM efhc_core.shop_orders "
                "WHERE global_id=928000001"
            ).fetchone()[0] == global_id
            assert connection.execute(
                "SELECT global_id FROM efhc_core.user_skins "
                "WHERE global_id=928000001 AND skin_id=2"
            ).fetchone()[0] == global_id
            assert connection.execute(
                "SELECT global_id FROM efhc_core.user_cosmetics "
                "WHERE global_id=928000001"
            ).fetchone()[0] == global_id

            connection.execute(
                """
                INSERT INTO efhc_core.user_skins (global_id, skin_id)
                VALUES (%s, 3)
                """,
                (second_global_id,),
            )
            global_only = connection.execute(
                "SELECT global_id, global_id FROM efhc_core.user_skins "
                "WHERE global_id=%s AND skin_id=3",
                (second_global_id,),
            ).fetchone()
            assert global_only == (None, second_global_id)

            with (
                pytest.raises(psycopg.Error),
                connection.transaction(),
            ):
                connection.execute(
                    """
                    INSERT INTO efhc_core.shop_orders (
                        global_id, global_id, type, status
                    ) VALUES (928000001, %s, 'NFT', 'PENDING')
                    """,
                    (second_global_id,),
                )

        # Downgrade fail-closed при provider-neutral owner data.
        from sqlalchemy.exc import DBAPIError

        with pytest.raises(DBAPIError):
            command.downgrade(_config(test_sqlalchemy), "0011")
        with psycopg.connect(test_psycopg, autocommit=True) as connection:
            assert connection.execute(
                "SELECT version_num FROM efhc_core.alembic_version"
            ).fetchone()[0] == "0012"
    finally:
        _restore_environment(previous)
        with psycopg.connect(admin_psycopg, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{database}"')
