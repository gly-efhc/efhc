# КАНОН: этот модуль намеренно не имеет prefix.
# system_routes: /health, /health/db, /health/runtime и близкие
# системные
# health endpoints живут без /system/ prefix по соглашению проекта.
# Не добавлять prefix без согласования с архитектором EFHC Bot.
# backend/app/routes/system_routes.py
# ======================================================================
# Назначение:
# Системные ручки EFHC Bot.
#
# Канон:
# - /cron/tick выполняет один проход и отдаёт JSON.
# - Без вечных циклов внутри HTTP.
# - Telegram webhook проверяет секрет.
# ======================================================================

from __future__ import annotations

import hmac
import json
import os
import time
from typing import Any, cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.runtime_observability import runtime_observability
from app.deps import (
    ExternalEventDedupeUnavailable,
    get_db,
    register_external_event_after_secret,
    require_admin_or_nft_or_key,
)
from app.lib.time import utcnow
from app.services.scheduler_service import SchedulerService
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("efhc.routes.system")
router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, Any]:
    """Проверка живости сервиса."""
    return {"status": "ok"}


def _metrics_token_guard(value: str | None) -> None:
    settings = get_settings()
    env = str(
        getattr(settings, "env_normalized", "local") or "local"
    )
    expected = str(os.getenv("METRICS_TOKEN", "") or "").strip()
    if env in {"prod", "stage", "staging"} and not expected:
        raise HTTPException(
            status_code=503,
            detail="Metrics access is not configured",
        )
    if expected and not hmac.compare_digest(value or "", expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid metrics token",
        )


async def _detailed_health_guard(
    request: Request,
    db: AsyncSession,
) -> None:
    """Разрешить detailed health только Admin session или metrics token."""

    metrics_token = request.headers.get("X-Metrics-Token")
    if metrics_token is not None:
        _metrics_token_guard(metrics_token)
        return
    # Direct calls must honor the same application-scoped dependency override
    # as Depends; isolated TEST preview does not change production RBAC.
    guard = request.app.dependency_overrides.get(
        require_admin_or_nft_or_key, require_admin_or_nft_or_key,
    )
    await guard(request, db)


@router.get("/meta/metrics", include_in_schema=False)
async def runtime_metrics(
    x_metrics_token: str | None = Header(
        default=None,
        alias="X-Metrics-Token",
    ),
) -> dict[str, Any]:
    """Safe bounded HTTP metrics for monitoring collectors."""
    _metrics_token_guard(x_metrics_token)
    return cast(
        dict[str, Any],
        runtime_observability.snapshot(),
    )


@router.get("/meta/deployment", include_in_schema=False)
async def deployment_metadata(
    x_metrics_token: str | None = Header(
        default=None,
        alias="X-Metrics-Token",
    ),
) -> dict[str, Any]:
    """Expose non-secret build provenance and deployment mode."""
    _metrics_token_guard(x_metrics_token)
    settings = get_settings()
    image_ref = str(os.getenv("IMAGE_REFERENCE", "") or "")
    image_digest = str(os.getenv("IMAGE_DIGEST", "") or "")
    immutable = bool(
        "@sha256:" in image_ref
        or image_digest.startswith("sha256:")
    )
    return {
        "ok": True,
        "environment": getattr(
            settings,
            "env_normalized",
            "local",
        ),
        "app_version": str(
            getattr(settings, "APP_VERSION", "unknown")
        ),
        "build_sha": str(os.getenv("BUILD_SHA", "") or "unknown"),
        "image_immutable": immutable,
        "image_digest_present": bool(image_digest),
        "serverless": bool(getattr(settings, "SERVERLESS", False)),
        "scheduler_enabled": bool(
            getattr(settings, "SCHEDULER_ENABLED", False)
        ),
    }


@router.get("/health/readiness", response_model=None)
async def health_readiness(
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool] | JSONResponse:
    """Coarse fail-closed readiness без internal runtime details."""

    settings = get_settings()
    try:
        await db.execute(text("SELECT 1"))
        version = (
            await db.execute(
                text(
                    "SELECT version_num FROM efhc_core.alembic_version "
                    "LIMIT 1"
                )
            )
        ).scalar_one_or_none()
    except Exception:
        return JSONResponse(status_code=503, content={"ok": False})

    migration_ok = str(version or "") == "0001"
    scheduler_enabled = bool(
        getattr(settings, "SCHEDULER_ENABLED", False)
    )
    if not scheduler_enabled:
        watcher_ok = True
    else:
        query = text(
            "SELECT status, executed_at "
            "FROM efhc_core.scheduler_task_log "
            "WHERE task_name = 'check_ton_inbox' "
            "ORDER BY executed_at DESC NULLS LAST, id DESC "
            "LIMIT 1"
        )
        watcher_ok = False
        try:
            row = (await db.execute(query)).first()
        except Exception:
            row = None
        if row and row[1] is not None:
            age_sec = max(0.0, utcnow().timestamp() - row[1].timestamp())
            watcher_ok = str(row[0] or "") == "ok" and age_sec <= 120

    metrics = runtime_observability.snapshot()
    critical_alert = any(
        item.get("severity") == "critical"
        for item in metrics.get("alerts", [])
    )
    ok = bool(migration_ok and watcher_ok and not critical_alert)
    if not ok:
        return JSONResponse(status_code=503, content={"ok": False})
    return {"ok": True}


@router.get("/health/db")
async def health_db(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Проверка БД и базовых инвариантов схемы.

    Возвращает компактный статус:
    - db.ok: выполнился SELECT 1
    - schema.ok: ключевые колонки withdraw_requests
    """
    out: dict[str, Any] = {
        "ok": False,
        "db": {"ok": False},
        "schema": {"ok": False},
    }

    try:
        await db.execute(text("SELECT 1"))
        out["db"]["ok"] = True
    except Exception:
        logger.exception("health_db: database availability check failed")
        out["db"]["error"] = "database_unavailable"
        return out

    try:
        schema = await _health_db_schema(db=db)
    except Exception:
        logger.exception("health_db: schema check failed")
        out["schema"] = {
            "ok": False,
            "status": "schema_check_unavailable",
        }
        return out
    out["schema"] = {
        "ok": bool(schema.get("ok")),
        "status": str(schema.get("status") or "unknown"),
    }
    out["ok"] = bool(out["db"]["ok"] and schema.get("ok"))
    return out


@router.get("/health/db-schema", response_model=None)
async def health_db_schema(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any] | JSONResponse:
    """Coarse DevOps schema-check с транспортной 503 при mismatch."""

    try:
        schema = await _health_db_schema(db=db)
    except Exception:
        logger.exception("health_db_schema: schema check failed")
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "status": "schema_check_unavailable",
            },
        )
    if not bool(schema.get("ok")):
        logger.error(
            "health_db_schema: mismatch: %s",
            schema,
        )
        return JSONResponse(
            status_code=503,
            content={"ok": False, "status": "schema_mismatch"},
        )
    return {"ok": True, "status": "ok"}


async def _health_db_schema(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Проверка схемы БД по текущему канону.

    Если миграции не прогнаны до head, код может падать на
    отсутствующих колонках. Ручка даёт сигнал DevOps.

    Проверяем минимум: withdraw_requests содержит колонки для
    холда и рефанда.
    """
    schema = getattr(get_settings(), "DB_SCHEMA_CORE", "efhc_core")
    required_cols = {
        "id",
        "tg_id",
        "amount",
        "status",
        "idempotency_key",
        "hold_done",
        "refund_done",
        "payout_ref",
        "created_at",
        "updated_at",
    }

    q = text(
        "\n".join(
            [
                "SELECT column_name",
                "FROM information_schema.columns",
                "WHERE table_schema = :schema",
                "  AND table_name = 'withdraw_requests'",
            ]
        )
    )
    r = await db.execute(q, {"schema": schema})
    cols = {str(x[0]) for x in r.fetchall()}
    missing = sorted(required_cols - cols)

    if missing:
        return {
            "ok": False,
            "status": "schema_mismatch",
            "schema": schema,
            "table": f"{schema}.withdraw_requests",
            "missing": missing,
            "hint": "Run migrations: alembic upgrade head",
        }

    return {"ok": True, "status": "ok", "schema": schema}


@router.get("/health/runtime")
async def health_runtime(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Detailed runtime health под Admin/metrics authorization."""
    await _detailed_health_guard(request, db)
    out: dict[str, Any] = {
        "ok": False,
        "backend": {"ok": True},
        "db": {"ok": False},
        "watcher": {
            "ok": False,
            "task_name": "check_ton_inbox",
            "last_heartbeat": None,
            "heartbeat_age_sec": None,
            "stale_after_sec": 120,
        },
    }

    try:
        await db.execute(text("SELECT 1"))
        out["db"]["ok"] = True
    except Exception:
        logger.exception("health_runtime: database availability check failed")
        out["db"]["error"] = "database_unavailable"
        return out

    q = text(
        "\n".join(
            [
                "SELECT status, executed_at",
                "FROM efhc_core.scheduler_task_log",
                "WHERE task_name = 'check_ton_inbox'",
                "ORDER BY executed_at DESC NULLS LAST, id DESC",
                "LIMIT 1",
            ]
        )
    )
    try:
        row = (await db.execute(q)).first()
    except Exception:
        logger.exception("health_runtime: watcher query failed")
        out["watcher"]["error"] = "watcher_unavailable"
        out["ok"] = bool(out["db"]["ok"])
        return out

    if row is None:
        out["watcher"]["status"] = "missing"
        out["ok"] = bool(out["db"]["ok"])
        return out

    status = str(row[0] or "")
    executed_at = row[1]
    out["watcher"]["status"] = status
    if executed_at is not None:
        ts = executed_at.isoformat()
        age_sec = max(0.0, utcnow().timestamp() - executed_at.timestamp())
        out["watcher"]["last_heartbeat"] = ts
        out["watcher"]["heartbeat_age_sec"] = round(age_sec, 2)
        out["watcher"]["ok"] = age_sec <= 120.0 and status == "ok"
    out["ok"] = bool(out["db"]["ok"] and out["watcher"]["ok"])
    return out


@router.get("/cron/tick", include_in_schema=False)
async def cron_tick(
    x_cron_secret: str | None = Header(
        default=None,
        alias="X-Cron-Secret",
    ),
) -> dict[str, Any]:
    """Один проход планировщика.

    Рекомендуется внешний Cron каждые 5 минут.

    Безопасность:
    - в prod/stage CRON_SECRET обязателен и проверяется fail-closed;
    - в local/dev/ci пустой secret допускается только для разработки.
    """
    s = get_settings()
    env = getattr(s, "env_normalized", "local")
    cron_secret = str(getattr(s, "CRON_SECRET", "") or "").strip()
    if env in {"prod", "stage"} and not cron_secret:
        raise HTTPException(
            status_code=401,
            detail="Invalid cron secret",
        )
    if cron_secret:
        token = x_cron_secret or ""
        if not hmac.compare_digest(token, cron_secret):
            raise HTTPException(
                status_code=401,
                detail="Invalid cron secret",
            )

    t0 = time.perf_counter()
    sched = SchedulerService()
    sched.register_defaults(strict=env in {"prod", "stage"})
    stats = await sched.run_single_tick()
    stats["total_wall_ms"] = round(
        (time.perf_counter() - t0) * 1000.0,
        2,
    )
    return dict(stats)


@router.post("/tg/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        default=None,
        alias="X-Telegram-Bot-Api-Secret-Token",
    ),
    db: AsyncSession = Depends(get_db),
    x_event_id: str | None = Header(
        default=None,
        alias="X-Event-Id",
    ),
    x_delivery_id: str | None = Header(
        default=None,
        alias="X-Delivery-Id",
    ),
    x_update_id: str | None = Header(
        default=None,
        alias="X-Telegram-Update-Id",
    ),
) -> dict[str, Any]:
    """Единая ручка Telegram Webhook.

    Канон:
    - вебхук попадает в aiogram.Dispatcher.

    Безопасность:
    - проверяем TELEGRAM_WEBHOOK_SECRET.
    """
    s = get_settings()
    webhook_secret = str(s.TELEGRAM_WEBHOOK_SECRET or "").strip()
    if s.env_normalized in {"prod", "stage"} and not webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Telegram webhook secret не настроен",
        )
    if webhook_secret:
        token = x_telegram_bot_api_secret_token or ""
        if not hmac.compare_digest(token, webhook_secret):
            raise HTTPException(
                status_code=401,
                detail="Неверный Telegram webhook secret",
            )

    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="INVALID_TELEGRAM_UPDATE",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="INVALID_TELEGRAM_UPDATE",
        )

    from app.bot.bot import process_update

    try:
        ext = await register_external_event_after_secret(
            "telegram",
            request,
            db,
            x_event_id=x_event_id,
            x_delivery_id=x_delivery_id,
            x_update_id=x_update_id,
        )
        if ext.get("is_duplicate"):
            await db.rollback()
            return {"status": "ok", "dedupe": True}

        await process_update(db=db, payload=payload)
        await db.commit()
        return {"status": "ok"}
    except ExternalEventDedupeUnavailable as exc:
        await db.rollback()
        raise HTTPException(
            status_code=503,
            detail="WEBHOOK_DEDUPE_UNAVAILABLE",
        ) from exc
    except HTTPException:
        await db.rollback()
        raise
    except BaseException:
        await db.rollback()
        logger.exception("telegram webhook processing failed")
        raise


__all__ = ["router"]
