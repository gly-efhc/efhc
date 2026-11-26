# backend/migrations/env.py
# =====================================================================
# Назначение кода:
# Alembic-окружение для EFHC Bot (Postgres-only).
# Канон схем: efhc_core и efhc_admin.
# Online: создаёт схемы (если нет), ставит search_path.
# Затем гоняет миграции.
# Строго Postgres-only.
# Offline: генерирует SQL без подключения.
#
# Канон / инварианты:
# • База — PostgreSQL.
# • Объекты лежат в двух схемах:
#   DB_SCHEMA_CORE (по умолчанию efhc_core)
#   DB_SCHEMA_ADMIN (по умолчанию efhc_admin)
# • Миграции не должны быть деструктивными без явной необходимости.
#
# ИИ-защиты:
# • URL берём из окружения (Postgres-only).
# • Явная установка search_path на схему из .env, чтобы миграции не
# «расползались».
# • Опциональная установка statement_timeout через окружение.
#
# Запреты:
# • Без жёсткого «затирания» схем/таблиц. Схемы создаём в env.py
# ДО транзакции миграций.
# =====================================================================
from __future__ import annotations

import logging
import os
import re
from logging.config import fileConfig
from urllib.parse import urlparse

from alembic import context
from sqlalchemy import engine_from_config, pool, text

config = context.config


def _get_database_url() -> str:
    configured = config.file_config.get(
        config.config_ini_section,
        "sqlalchemy.url",
        raw=True,
        fallback="",
    ).strip()
    if configured and "%(" not in configured:
        return configured
    url = os.environ.get("PSYCOPG_URL")
    if url:
        return url
    url = os.environ.get("SYNC_DATABASE_URL")
    if url:
        return url
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    raise RuntimeError(
        "DB URL missing: set PSYCOPG_URL or SYNC_DATABASE_URL "
        "or DATABASE_URL"
    )


DB_URL = _get_database_url()
# Конфигурация Alembic
# Логи Alembic
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")
# --------------------------------------------------------------------
# Параметры окружения / схема / таймаут
# --------------------------------------------------------------------
DB_SCHEMA_CORE = os.getenv("DB_SCHEMA_CORE", "efhc_core")
DB_SCHEMA_ADMIN = os.getenv("DB_SCHEMA_ADMIN", "efhc_admin")
# Для Neon/SSL: добавим sslmode=require только для внешних DB.
# Docker/local Postgres не поддерживает SSL по умолчанию.
# Хосты db/postgres являются локальными compose-сервисами.
if "sslmode=" not in DB_URL:
    _p = urlparse(DB_URL)
    _host = (_p.hostname or "").lower()
    _env = (os.getenv("ENV") or "local").strip().lower()
    _local_envs = {"local", "dev", "development", "ci", "test"}
    _local_hosts = {"localhost", "127.0.0.1", "::1", "db", "postgres"}
    if _env not in _local_envs and _host not in _local_hosts:
        _join = "&" if "?" in DB_URL else "?"
        DB_URL = f"{DB_URL}{_join}sslmode=require"
# Statement timeout (мс) опционально
PG_STATEMENT_TIMEOUT_MS = os.getenv("PG_STATEMENT_TIMEOUT_MS")
if PG_STATEMENT_TIMEOUT_MS:
    try:
        int(PG_STATEMENT_TIMEOUT_MS)
    except ValueError as err:
        raise RuntimeError(
            "PG_STATEMENT_TIMEOUT_MS: целое число (мс)"
        ) from err
# Прокидываем URL в конфиг Alembic
config.set_main_option("sqlalchemy.url", DB_URL)
# --------------------------------------------------------------------
# env.py не использует metadata для Alembic autogenerate. Единственный
# Greenfield 0001 сам загружает Base.metadata и создаёт clean initial schema.
# --------------------------------------------------------------------
target_metadata = None




def _is_valid_ident(name: str) -> bool:
    if not name:
        return False
    if len(name) > 63:
        return False
    return bool(re.fullmatch(r"[a-z_][a-z0-9_]*", name))


def _quote_ident(name: str) -> str:
    # Ident для Postgres: двойные кавычки.
    # Здесь name уже валидирован regex.
    return f'"{name}"'


def _validate_schemas() -> tuple[str, str]:
    core = (DB_SCHEMA_CORE or "efhc_core").strip()
    admin = (DB_SCHEMA_ADMIN or "efhc_admin").strip()
    allowed = ("efhc_core", "efhc_admin")
    for s in (core, admin):
        if not _is_valid_ident(s):
            raise RuntimeError(
                "Invalid schema name; allowed: [a-z_][a-z0-9_]*"
            )
    if (core, admin) != allowed:
        raise RuntimeError(
            "Only canonical schemas are allowed: "
            "efhc_core and efhc_admin"
        )
    return core, admin


CORE_SCHEMA, ADMIN_SCHEMA = _validate_schemas()


def _apply__schema__translate_map(connection):
    """Привязать объекты без схемы к efhc_core (Postgres-only)."""
    mp = {None: DB_SCHEMA_CORE}
    return connection.execution_options(schema_translate_map=mp)

def _set_search_path(connection) -> None:
    """
    Выставляет search_path на efhc_core и efhc_admin.
    """
    sp = f"{_quote_ident(CORE_SCHEMA)}, {_quote_ident(ADMIN_SCHEMA)}"
    connection.exec_driver_sql(f"SET search_path TO {sp}")
    if PG_STATEMENT_TIMEOUT_MS:
        connection.execute(
            text(
                f"SET statement_timeout TO "
                f"{int(PG_STATEMENT_TIMEOUT_MS)}"
            )
        )

def run_migrations_offline() -> None:
    """
    Offline-режим: Alembic генерирует SQL без подключения к БД.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        version_table_schema=DB_SCHEMA_CORE,
        include_schemas=True,
        render_as_batch=False,
    )
    with context.begin_transaction():
        # В offline search_path задаётся в 0001_init.
        # DDL: CREATE SCHEMA IF NOT EXISTS ...
        # NOT EXISTS
        context.run_migrations()
def run_migrations_online() -> None:
    """
    Online-режим: подключение к БД.
    Установка search_path и прогон миграций.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    # Создание схем выполняется на отдельном AUTOCOMMIT connection.
    # Migration connection не должен наследовать AUTOCOMMIT: data
    # migrations используют PostgreSQL locks и обязаны быть atomic.
    with connectable.connect() as bootstrap_connection:
        conn_ac = bootstrap_connection.execution_options(
            isolation_level="AUTOCOMMIT"
        )
        for _schema in (CORE_SCHEMA, ADMIN_SCHEMA):
            ident = _quote_ident(_schema)
            conn_ac.exec_driver_sql(
                "CREATE SCHEMA IF NOT EXISTS " + ident
            )

    with connectable.connect() as connection:
        _set_search_path(connection)

        # Таблицы без явной схемы должны идти в efhc_core.
        conn2 = _apply__schema__translate_map(connection)

        # Диагностика выполняется до Alembic transaction.
        try:
            db = conn2.execute(text("SELECT current_database()"))
            db = db.scalar()
            sp = conn2.execute(text("SHOW search_path")).scalar()
            logger.info("DB diag: db=%s search_path=%s", db, sp)
        except Exception:
            logger.info("DB diag: unavailable")

        # SET/search diagnostics вызывают autobegin. Завершаем только
        # setup transaction; session-level search_path сохраняется.
        conn2.commit()

        context.configure(
            connection=conn2,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            version_table_schema=DB_SCHEMA_CORE,
            include_schemas=True,
            render_as_batch=False,
        )
        with context.begin_transaction():
            context.run_migrations()

# Точка входа Alembic
if context.is_offline_mode():
    logger.info(
        "EFHC Alembic offline; schemas=%s,%s",
        DB_SCHEMA_CORE,
        DB_SCHEMA_ADMIN,
    )
    run_migrations_offline()
else:
    logger.info(
        "EFHC Alembic online; schemas=%s,%s",
        DB_SCHEMA_CORE,
        DB_SCHEMA_ADMIN,
    )
    run_migrations_online()
