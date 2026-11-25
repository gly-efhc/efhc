from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

from app.core.config_core import get_settings
from app.core.database_core import db_ping, db_session, dispose_engine
from app.core.errors_core import setup_exception_handlers
from app.core.logging_core import CorrelationIdMiddleware, get_logger
from app.core.system_locks import (
    assert_system_locks,
    install_security_middlewares,
)
from app.middleware.request_observability import (
    RequestObservabilityMiddleware,
)
from app.middleware.security_headers import SecurityHeadersMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

logger = get_logger(__name__)
settings = get_settings()

# --- PROD safety guard -----------------------------------------------
# If insecure user-id headers are enabled in PROD, fail fast on startup.
# This prevents configuration mistakes from turning into financial
# vulnerabilities.
_insecure_flag = os.getenv(
    "ALLOW_INSECURE_USER_HEADERS", ""
).strip().lower() in {"1", "true", "yes", "on"}
if getattr(settings, "ENV", "").lower() == "prod" and _insecure_flag:
    raise RuntimeError(
        "SECURITY: ALLOW_INSECURE_USER_HEADERS = true is forbidden "
        "when ENV = prod"
    )

_real_funds_flag = os.getenv(
    "ALLOW_REAL_FUNDS", ""
).strip().lower() in {"1", "true", "yes", "on"}
if (
    getattr(settings, "ENV", "").lower() in {"stage", "staging"}
    and _real_funds_flag
):
    raise RuntimeError(
        "SAFETY: ALLOW_REAL_FUNDS = true is forbidden when ENV = stage"
    )


# ----------------------------------------------------------------------
# CORS: фронтенд/вебхуки из .env
# ----------------------------------------------------------------------


def _as_origin(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw == "*":
        return "*"
    p = urlparse(raw)
    if p.scheme and p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return raw


def _build_cors_origins() -> list[str]:
    """SSOT: список доверенных Origin для CORS.

    Канон:
    - В prod НЕ разрешаем localhost.
    - Источник: CORS_ALLOW_ORIGINS (CSV) и базовые URL из settings.
    """
    origins: list[str] = []
    csv = (os.getenv("CORS_ALLOW_ORIGINS") or "").strip()
    if csv:
        for part in csv.split(","):
            v = part.strip()
            if v:
                origins.append(_as_origin(v))

    for name in (
        "APP_URL",
        "BACKEND_URL",
        "FRONTEND_URL",
        "WEBHOOK_URL",
    ):
        raw_v = getattr(settings, name, None)
        origin_v: str | None = raw_v if isinstance(raw_v, str) else None
        if origin_v is None:
            origin_v = os.environ.get(name)
        if origin_v:
            origins.append(_as_origin(origin_v))

    if getattr(settings, "env_normalized", "local") != "prod":
        origins.extend(
            [
                "http://localhost",
                "http://localhost:3000",
                "http://127.0.0.1",
                "http://127.0.0.1:3000",
            ]
        )

    uniq = sorted({o for o in origins if o})
    if "*" in uniq and settings.env_normalized == "prod":
        raise RuntimeError(
            "CORS: '*' is forbidden in prod when credentials "
            "are enabled"
        )
    return uniq


# ----------------------------------------------------------------------
# Лайфспан: старт/стоп приложения
# ----------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Владеть startup/shutdown lifecycle canonical ``app.main:app``."""
    del app

    # Ошибки программирования и конфигурации не маскируются как необязательный импорт.
    assert_system_locks()
    logger.info("system_locks: стартовые проверки канона пройдены")
    if settings.env_normalized in {"prod", "stage"}:
        if not await db_ping():
            raise RuntimeError("database preflight failed")
        logger.info("database preflight: OK")

    # Production-планировщик работает в отдельном контейнере.
    embedded = os.getenv(
        "RUN_EMBEDDED_TON_AGENT",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    if embedded and not settings.SERVERLESS:
        raise RuntimeError(
            "RUN_EMBEDDED_TON_AGENT is forbidden in production; "
            "use the dedicated scheduler service"
        )

    from app.bot.fsm.manager import get_state_manager

    state_manager = get_state_manager()
    await state_manager.start_background_gc()
    logger.info(
        "startup: embedded TON agent disabled; "
        "scheduler service owns background jobs"
    )
    try:
        yield
    finally:
        await state_manager.stop_background_gc()
        await dispose_engine()


# ----------------------------------------------------------------------
# Приложение FastAPI
# ----------------------------------------------------------------------

app = FastAPI(
    title=getattr(settings, "PROJECT_NAME", "EFHC - Bot"),
    version=getattr(settings, "APP_VERSION", "0.0.0"),
    openapi_url=getattr(settings, "OPENAPI_URL", None),
    docs_url=getattr(settings, "DOCS_URL", None),
    redoc_url=getattr(settings, "REDOC_URL", None),
    lifespan=lifespan,
)

app.add_middleware(RequestObservabilityMiddleware)
app.add_middleware(CorrelationIdMiddleware)

trusted_hosts = [
    str(value).strip()
    for value in (getattr(settings, "TRUSTED_HOSTS", []) or [])
    if str(value).strip()
]
if trusted_hosts:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=trusted_hosts,
    )
elif settings.env_normalized in {"prod", "stage", "staging"}:
    logger.warning(
        "TRUSTED_HOSTS не задан: backend допустим только за "
        "каноническим приватным reverse-proxy contour"
    )

app.add_middleware(
    SecurityHeadersMiddleware,
    environment=settings.env_normalized,
    max_request_body_bytes=settings.MAX_REQUEST_BODY_BYTES,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
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
)

# ----------------------------------------------------------------------
# Security middleware: единый канонический установщик.
# ----------------------------------------------------------------------
install_security_middlewares(app)


# ----------------------------------------------------------------------
# Подключение HTTP-роутов (КАНОН)
# ----------------------------------------------------------------------

from app.routes import register as register_routes  # noqa: E402

# Важно: локальные роуты не вшивают /api, но runtime использует
# единый API_PREFIX из Settings.
register_routes(app, prefix=settings.API_PREFIX)
setup_exception_handlers(app)


# ----------------------------------------------------------------------
# Отдельный readiness-probe БД: HTTP 503 при недоступности PostgreSQL.
# ----------------------------------------------------------------------


@app.get(
    "/meta/health_db",
    tags=["meta"],
    response_model=None,
)
async def health_db() -> Any:
    """Проверить доступность БД с транспортной 503-семантикой."""
    try:
        async with db_session() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        logger.exception("health_db: database availability check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "error"},
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        reload=True,
    )
