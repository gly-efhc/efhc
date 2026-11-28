# backend/app/core/database_core.py
# =====================================================================
# Назначение кода:
# • Единая точка работы с БД EFHC Bot (PostgreSQL + asyncpg).
# • Создание и конфигурация AsyncEngine и async_sessionmaker.
# • Безопасная выдача сессий для FastAPI-роутов и сервисов.
# • Базовые health/self-healing утилиты (ping, мягкий реинициализатор).
#
# Канон / инварианты EFHC:
# • Только async-движок (create_async_engine), никаких sync-engine.
# • DSN берём из Settings.database_url_asyncpg(): SSOT.
# • Пул соединений: DB_POOL_SIZE / DB_MAX_OVERFLOW.
# • Сессии expire_on_commit=False (во избежание лишних рефрешей).
#
# ИИ-защита:
# • При проблемах с созданием движка/сессии — подробный лог и понятные
# исключения, без скрытого «молчаливого» падения.
# • db_ping(): healthcheck и самопроверка перед стартом воркеров.
# • Лёгкий self-healing: reset_engine() позволяет аккуратно пересоздать
# движок при смене настроек или после серьёзных сбоев.
#
# Запреты:
# • Никакой бизнес-логики (эмиссия, списания, банк) в этом модуле.
# • Никаких Alembic-миграций/DDL здесь — только подключения и сессии.
# =====================================================================

from __future__ import annotations

import asyncio
import ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = get_logger(__name__)
settings = get_settings()


def _normalise_asyncpg_connect(
    dsn: str,
) -> tuple[str, dict[str, object]]:
    """Adapt libpq Neon URL options for SQLAlchemy's asyncpg driver.

    asyncpg.connect does not accept the libpq query keywords ``sslmode``
    and ``channel_binding``. A strict channel-binding request cannot be
    represented as an asyncpg argument. To avoid an unverified-TLS downgrade,
    it is replaced by mandatory CA + hostname verification for this driver.
    This is verified TLS, not SCRAM-SHA-256-PLUS channel binding.
    """
    parts = urlsplit(dsn)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    clean_pairs: list[tuple[str, str]] = []
    sslmode: str | None = None
    channel_binding: str | None = None
    for key, value in pairs:
        lowered = key.lower()
        if lowered == "sslmode":
            sslmode = value.lower()
            continue
        if lowered == "channel_binding":
            channel_binding = value.lower()
            continue
        clean_pairs.append((key, value))

    if channel_binding not in {None, "require", "prefer", "disable"}:
        raise ValueError("Unsupported channel_binding option in PostgreSQL DSN")
    if channel_binding in {"require", "prefer"} and sslmode == "disable":
        raise ValueError("TLS is required for channel-binding Neon DSN")
    # TEST compatibility is not a claim of SCRAM-SHA-256-PLUS support.
    # Do not silently weaken an explicit production binding requirement.
    if channel_binding == "require" and settings.env_normalized == "prod":
        raise ValueError(
            "Production channel_binding=require needs a driver enforcing "
            "SCRAM-SHA-256-PLUS; asyncpg cannot enforce this DSN option"
        )

    clean_query = urlencode(clean_pairs, doseq=True)
    clean_dsn = urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            clean_query,
            parts.fragment,
        )
    )
    connect_args: dict[str, object] = {}
    if channel_binding in {"require", "prefer"}:
        # Unlike ssl=True, a default SSLContext explicitly validates both
        # the certificate chain and the server DNS name.
        connect_args["ssl"] = ssl.create_default_context()
    elif sslmode in {"require", "verify-ca", "verify-full"}:
        connect_args["ssl"] = True
    return clean_dsn, connect_args


# --------------------------------------------------------------------
# Глобальные объекты: движок и фабрика сессий
# --------------------------------------------------------------------
_engine: AsyncEngine | None = None
_SessionFactory: async_sessionmaker[AsyncSession] | None = None
_engine_lock = asyncio.Lock()


def _create_engine() -> AsyncEngine:
    """
    Создаёт новый AsyncEngine на базе актуальных настроек.

    Особенности:
    • DSN приводится к asyncpg-формату через
      settings.database_url_asyncpg().
    • pool_pre_ping: раннее обнаружение "умерших" соединений.
    • echo включается только в DEBUG-режиме.
    """
    dsn = settings.database_url_asyncpg()
    dsn, connect_args = _normalise_asyncpg_connect(dsn)
    logger.info(
        "Creating async DB engine",
        extra={"dsn_set": bool(dsn)},
    )
    engine = create_async_engine(
        dsn,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        echo=settings.DEBUG,
        connect_args=connect_args,
    )
    return engine


def _create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """
    Строит async_sessionmaker поверх переданного движка.

    Канон:
    • expire_on_commit=False: объекты валидны после commit().
    • autoflush=False — явный контроль flush при необходимости.
    """
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
        class_=AsyncSession,
    )


async def reset_engine() -> None:
    """
    Мягко пересоздаёт движок и фабрику сессий.

    Использование:
    • при критических сбоях подключения;
    • при горячем обновлении конфигурации DSN (редкий случай).

    ИИ-защита:
    • Закрывает старый engine через dispose(), чтобы не оставлять
      "висящие" соединения.
    """
    global _engine, _SessionFactory

    async with _engine_lock:
        old_engine = _engine
        try:
            new_engine = _create_engine()
            _SessionFactory = _create_session_factory(new_engine)
            _engine = new_engine
            logger.info("DB engine has been reset successfully")
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to reset DB engine",
                extra={"error": str(exc)},
            )
            # Если новый движок не поднялся — откатываемся к старому
            if old_engine is not None:
                _engine = old_engine
            raise
        else:
            if old_engine is not None:
                try:
                    await old_engine.dispose()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Error during old engine dispose",
                        exc_info=True,
                    )


async def dispose_engine() -> None:
    """Детерминированно закрыть process-scoped DB engine.

    Сначала атомарно снимаем глобальные ссылки под lock, затем выполняем
    потенциально долгий ``dispose()`` вне lock. Повторный вызов безопасен.
    """
    global _engine, _SessionFactory

    async with _engine_lock:
        engine = _engine
        _engine = None
        _SessionFactory = None

    if engine is not None:
        await engine.dispose()
        logger.info("DB engine disposed")


def get_engine() -> AsyncEngine:
    """
    Возвращает текущий AsyncEngine.

    Если движок ещё не был создан (например, при раннем импортировании),
    создаёт его синхронно. Для продакшна вызывайте db_ping()
    на старте, чтобы гарантировать живое подключение.
    """
    global _engine, _SessionFactory

    if _engine is None:
        engine = _create_engine()
        _engine = engine
        _SessionFactory = _create_session_factory(engine)
        logger.info("DB engine lazily initialized")
    # _engine уже инициализирован выше.
    # Если нет — это баг инициализации.
    if _engine is None:
        raise RuntimeError("DB engine is not initialized")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Возвращает фабрику сессий.

    Гарантирует, что движок создан (через get_engine()).
    """
    global _SessionFactory

    if _SessionFactory is None:
        engine = get_engine()
        _SessionFactory = _create_session_factory(engine)
        logger.info("Session factory initialized")
    if _SessionFactory is None:
        raise RuntimeError("DB session factory is not initialized")
    return _SessionFactory


# --------------------------------------------------------------------
# FastAPI-совместимая зависимость: выдача сессии
# --------------------------------------------------------------------
async def fastapi_db_dependency() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость поверх канонического ``db_session``.

    HTTP/application use-case остаётся владельцем commit/rollback.
    При аварийном выходе dependency гарантирует rollback и закрытие сессии.
    """
    async with db_session() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise


# --------------------------------------------------------------------
# Проверка доступности БД / ping
# --------------------------------------------------------------------
async def db_ping() -> bool:
    """
    Простейший health-check БД.

    Возвращает:
    • True — если SELECT 1 успешно прошёл;
    • False — если движок не создан или БД не отвечает.

    Использование:
    • endpoint /health;
    • проверка перед запуском фоновых воркеров/планировщика.
    """
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except (OperationalError, DBAPIError) as exc:
        logger.error(
            "DB ping failed: DB is not reachable",
            extra={"error": str(exc)},
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "DB ping failed with unexpected error",
            extra={"error": str(exc)},
        )
        return False


def new_session() -> AsyncSession:
    """Создать одну AsyncSession из канонической фабрики."""
    return get_session_factory()()


@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Выдать одну каноническую AsyncSession фоновой/runtime-задаче."""
    session = new_session()
    try:
        yield session
    finally:
        await session.close()


# --------------------------------------------------------------------
# Инициализация при импорте (lazy-friendly)
# --------------------------------------------------------------------
# ВАЖНО:
# • Мы не создаём движок при импорте, чтобы не ломать миграции/Alembic
# и не заставлять поднимать БД в любых вспомогательных скриптах.
# • get_engine()/get_session_factory() создадут движок лениво при первом
# вызове.
# =====================================================================

__all__ = [
    "AsyncSession",
    "AsyncEngine",
    "get_engine",
    "get_session_factory",
    "fastapi_db_dependency",
    "db_ping",
    "reset_engine",
    "dispose_engine",
    "new_session",
    "db_session",
]
