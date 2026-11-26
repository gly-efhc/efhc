"""Test configuration (Postgres-only, canon).

- Enforces no bytecode files during tests
- Provides Postgres-only async SQLAlchemy engine/session fixtures
- Ensures schemas are canon: efhc_core / efhc_admin (no main)
- Prevents env cross-test pollution (DB_SCHEMA_CORE etc.)
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest


def _get_admin_provider_tg_id() -> int:
    """Вернуть Telegram subject только для provider-boundary tests."""

    try:
        from app.core.config_core import settings as s
    except Exception:
        return 900001

    ids = list(getattr(s, "ADMIN_TG_IDS", []) or [])
    if ids:
        try:
            return int(ids[0])
        except Exception:
            return 900001

    try:
        value = int(getattr(s, "ADMIN_TG_ID", 0) or 0)
        return value or 900001
    except Exception:
        return 900001


@pytest.fixture(scope="session")
def admin_global_id() -> int:
    """Канонический owner/actor администратора для business tests."""

    return 8_000_900_001


@pytest.fixture(scope="session")
def admin_provider_tg_id() -> int:
    """Telegram subject администратора для provider-boundary tests."""

    return _get_admin_provider_tg_id()


import asyncio  # noqa: E402
import subprocess  # noqa: E402

import pytest_asyncio  # noqa: E402

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True


def _ensure_repo_root_on_syspath() -> None:
    # tests/ -> repo root
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_repo_root_on_syspath()




def _running_in_ci() -> bool:
    """Return True only for the blocking GitHub Actions environment."""
    return os.getenv("GITHUB_ACTIONS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _to_async_sqlalchemy_url(url: str) -> str:
    # prefer asyncpg for AsyncEngine
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg://"):
        prefix = "postgresql+asyncpg://"
        return prefix + url[len("postgresql+psycopg://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


def _get_async_db_url() -> str:
    url = (
        os.getenv("ASYNC_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("SYNC_DATABASE_URL")
    )
    if not url:
        message = (
            "DATABASE_URL/ASYNC_DATABASE_URL is required for real "
            "PostgreSQL integration tests"
        )
        if _running_in_ci():
            pytest.fail(message)
        pytest.skip(message)
    if url.lower().startswith("sqlite"):
        pytest.fail("SQLite is forbidden in CI canon (Postgres-only)")
    return _to_async_sqlalchemy_url(url)


def get_async_db_url() -> str:
    """Helper for tests that need async SQLAlchemy URL."""
    return _get_async_db_url()


@pytest.fixture(autouse=True)
def _restore_env_and_syspath() -> Iterator[None]:
    # prevent cross-test env pollution (main schema etc.)
    _ensure_repo_root_on_syspath()
    saved = dict(os.environ)
    # enforce canon schemas
    os.environ["DB_SCHEMA_CORE"] = "efhc_core"
    os.environ["DB_SCHEMA_ADMIN"] = "efhc_admin"
    # keep ADMIN bank id stable for tests that touch it
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


@pytest.fixture(scope="session")
def schema_core() -> str:
    return "efhc_core"


@pytest.fixture(scope="session")
def schema_admin() -> str:
    return "efhc_admin"


@pytest.fixture(scope="session")
def async_db_url() -> str:
    return _get_async_db_url()


@pytest_asyncio.fixture(scope="session")
async def async_engine(
    async_db_url: str,
):
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
    except ImportError as exc:
        message = "SQLAlchemy/asyncpg dependencies are required"
        if _running_in_ci():
            pytest.fail(message)
        pytest.skip(message)
        raise AssertionError("unreachable") from exc

    engine = create_async_engine(
        async_db_url,
        future=True,
        poolclass=NullPool,
    )
    # Warm up the engine/pool in the session event loop.
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def schemas_ready(
    async_engine,
    schema_core: str,
    schema_admin: str,
) -> None:
    # Create canon schemas once per session.
    async with async_engine.begin() as conn:
        await _ensure_schema(conn, schema_admin)
        await _ensure_schema(conn, schema_core)


@pytest_asyncio.fixture(scope="session")
async def db_migrated(
    schemas_ready,
) -> None:
    # Make DB tests self-contained: ensure alembic upgraded to head.
    repo = Path(__file__).resolve().parents[1]
    backend_dir = repo / "backend"
    cmd = [
        sys.executable,
        "-m",
        "alembic",
        "-c",
        "alembic.ini",
        "upgrade",
        "head",
    ]

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
        )

    p = await asyncio.to_thread(_run)
    if p.returncode != 0:
        out = (p.stdout or "") + (p.stderr or "")
        msg = "alembic upgrade head failed:\n" + out
        raise RuntimeError(msg)


async def _ensure_schema(conn, schema: str) -> None:
    from sqlalchemy import text

    # Schema name is internal (from fixtures), keep it simple.
    stmt = 'CREATE SCHEMA IF NOT EXISTS "' + schema + '"'
    await conn.execute(text(stmt))


async def _truncate__schema__tables(conn, schema: str) -> None:
    # truncate all tables in schema except alembic_version
    from sqlalchemy import text

    q = text("""
        SELECT tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname = :schema
          AND tablename <> 'alembic_version'
        """)
    res = await conn.execute(q, {"schema": schema})
    rows = res.fetchall()
    if not rows:
        return
    tbls = ", ".join([f'{schema}."{r[0]}"' for r in rows])
    stmt = text(f"TRUNCATE TABLE {tbls} RESTART IDENTITY CASCADE")
    await conn.execute(stmt)


@pytest_asyncio.fixture
async def db_clean(
    async_engine,
    schema_core: str,
    schema_admin: str,
    db_migrated,
) -> AsyncIterator[None]:
    # Clean tables per test (schemas created once per session).
    # Pre-test cleanup is sufficient: every database test starts from the
    # same canonical empty state, and the CI PostgreSQL container is
    # disposable. A second full TRUNCATE after every test doubles DDL
    # relfilenode churn and can trigger multi-minute checkpoint storms on
    # shared GitHub runners. The next test performs the canonical cleanup.
    async with async_engine.begin() as conn:
        await _truncate__schema__tables(conn, schema_admin)
        await _truncate__schema__tables(conn, schema_core)
    yield


@pytest_asyncio.fixture
async def db_session(async_engine, db_clean):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with Session() as s:
        yield s
