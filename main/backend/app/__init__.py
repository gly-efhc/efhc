# backend/app/__init__.py
# ======================
# Инициализация серверной части EFHC Bot.
#
# ВАЖНОЕ РЕШЕНИЕ ЦИКЛА 1728 ДЛЯ БУДУЩИХ АУДИТОВ:
# канонический экземпляр FastAPI создаётся в app.main и запускается как
# app.main:app. Функция create_app() ниже сохранена бессрочно как исторический
# import/startup seam. Она НЕ должна превращаться во вторую фабрику FastAPI,
# повторно подключать middleware/routers или создавать второй runtime app.
# Отсутствие прямых callers create_app() не является основанием для удаления:
# этот путь сохраняется для внешних импортов, старых инструментов и совместимости.

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import Lifespan

# ВАЖНО (Lock: packages importable)
# Этот модуль не должен выполнять тяжёлую инициализацию на этапе import.
# Зависимости (settings/logging/router) импортируются лениво.
# Каноническая runtime-точка входа: app.main:app. create_app() — только
# бессрочный compatibility facade, а не альтернативная точка сборки приложения.

# Зависимость для health/ping БД импортируем лениво внутри обработчика.
# Это позволяет импортировать пакет без настроек окружения и без БД.
_db_ping = None


def _build_description() -> str:
    """Текстовое описание API для Swagger UI/Redoc."""
    return (
        "EFHC Bot API — серверная часть экосистемы EFHC:\n\n"
        " - Панели, баланс, обмен kWh→EFHC (1:1)\n"
        " - Магазин: покупки за TON/USDT/EFHC, заявки на VIP NFT\n"
        " - Реферальная система и пользовательские события\n"
        " - Админ-панель (банк EFHC, товары, заказы,"
        " ставки генерации)\n"
    )


def _install_middlewares(
    app: FastAPI,
    origins: Iterable[str],
    trusted_hosts: Iterable[str],
    gzip_min_size: int,
) -> None:
    """Подключение middleware: CORS, GZip, TrustedHosts."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=[
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Request-ID",
            "X-Telegram-Init-Data",
            "X-EFHC-Handoff",
            "X-Cron-Secret",
            "X-Telegram-Bot-Api-Secret-Token",
            "X-Event-Id",
            "X-Delivery-Id",
        ],
        expose_headers=["Content-Disposition"],
        max_age=600,
    )

    app.add_middleware(GZipMiddleware, minimum_size=gzip_min_size)

    hosts = [h for h in trusted_hosts if h.strip()]
    if hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)


def _install_exception_handlers(app: FastAPI) -> None:
    """Единые обработчики ошибок с JSON-ответом."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "error": "validation_error",
                "details": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        _: Request,
        exc: Exception,
    ) -> JSONResponse:
        logging.getLogger("efhc").exception(
            "Unhandled error",
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "internal_error"},
        )


def _lifespan() -> Lifespan[FastAPI]:
    """Lifespan (startup/shutdown) через AsyncExitStack."""

    @asynccontextmanager
    async def _inner(app: FastAPI) -> AsyncIterator[None]:
        _ = app
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            yield
        finally:
            await stack.aclose()

    return _inner


def _install_basic_routes(app: FastAPI) -> None:
    """Служебные маршруты: root/healthz."""

    @app.get("/", tags=["public"])
    async def root() -> dict:
        return {
            "ok": True,
            "service": app.title,
            "version": app.version,
        }

    @app.get("/healthz", tags=["public"])
    async def healthz() -> dict:
        global _db_ping

        if _db_ping is None:
            try:
                from .deps import db_ping as ping  # type: ignore

                _db_ping = ping
            except Exception:
                _db_ping = None

        if _db_ping:
            try:
                from .db import AsyncSessionFactory

                async with AsyncSessionFactory() as session:
                    result = await _db_ping(session)  # type: ignore
                return {"ok": True, "db": result.get("db", "unknown")}
            except Exception:
                return {"ok": False, "db": "fail"}

        return {"ok": True}


def create_app() -> FastAPI:
    """Вернуть канонический ``app.main.app`` через старый import path.

    Решение цикла 1728: фасад сохраняется бессрочно. Это намеренно тонкая
    обёртка, а не фабрика. Будущему аудиту запрещено «упрощать» её удалением
    только потому, что основной запуск использует ``app.main:app``. Также
    запрещено переносить сюда создание второго FastAPI-приложения: это
    породит два расходящихся runtime-контура.
    """

    from .main import app as main_app

    return main_app


__all__ = ["create_app", "services"]
