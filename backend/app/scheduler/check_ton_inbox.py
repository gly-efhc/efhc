# backend/app/scheduler/check_ton_inbox.py
# =====================================================================
# Оркестратор входящих TON-платежей.
# Будит watcher_service, читает новые транзакции и догоняет «хвосты».
# Сам не делает денежных действий и не выдаёт NFT.
# =====================================================================

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from collections.abc import Callable
from contextlib import (
    AbstractAsyncContextManager,
    suppress,
)
from dataclasses import dataclass
from typing import Any

from app.core.config_core import get_settings
from app.core.database_core import db_session
from app.core.logging_core import get_logger
from app.services import watcher_service as watcher
from app.services.admin.admin_notifications import AdminNotifier
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()
SCHEMA = getattr(settings, "DB_SCHEMA_CORE", "efhc_core")


def _env_int(attr: str, default: int) -> int:
    val = getattr(settings, attr, default)
    try:
        return int(val or default)
    except Exception:
        return int(default)


# ---------------------------------------------------------------------
# Параметры тика/защиты (значения по умолчанию безопасные)
# ---------------------------------------------------------------------
INTERVAL_SEC: int = _env_int("CHECK_TON_INBOX_INTERVAL_SEC", 600)
TASK_TIMEOUT_SEC: int = _env_int("CHECK_TON_INBOX_TIMEOUT_SEC", 900)

TON_POLL_LIMIT: int = _env_int("TON_WATCHER_POLL_LIMIT", 200)
TON_RETRY_LIMIT: int = _env_int("TON_WATCHER_RETRY_LIMIT", 500)
ACTIVITY_COOLDOWN_SEC = 60
ACTIVITY_REPLAY_SECONDS = 7 * 24 * 3600

RECONCILE_EVERY_TICKS: int = _env_int("TON_RECONCILE_EVERY_TICKS", 6)
RECONCILE_HOURS: int = _env_int("TON_RECONCILE_HOURS", 24)

LOCK_KEY1: int = _env_int("TON_INBOX_ADVISORY_KEY1", 0xEF0C)
LOCK_KEY2: int = _env_int("TON_INBOX_ADVISORY_KEY2", 0x01)

_LOCAL_LOCK = asyncio.Lock()


async def _try_acquire_advisory_lock(db: AsyncSession) -> bool:
    # Transaction-scoped: releasing a SQLAlchemy pooled connection after
    # commit must not strand a PostgreSQL session-level advisory lock.
    row = await db.execute(
        text("SELECT pg_try_advisory_xact_lock(:k1, :k2)"),
        {"k1": LOCK_KEY1, "k2": LOCK_KEY2},
    )
    return bool(row.scalar())


async def _release_advisory_lock(db: AsyncSession) -> None:
    # XACT advisory lock is released by COMMIT / ROLLBACK (or session close).
    # Session-level pg_advisory_unlock is intentionally never called.
    return None


def _json_dump_safe(obj: Any) -> str:
    try:
        return json.dumps(
            obj,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except Exception:
        return "{}"




async def _next_reconcile_tick(db: AsyncSession) -> tuple[int, bool]:
    """Persist the reconcile cadence across scheduler restarts."""
    key = "scheduler.ton_reconcile_tick_counter"
    query = text(
        "INSERT INTO efhc_core.app_settings (key, value) "
        "VALUES (:key, '1') "
        "ON CONFLICT (key) DO UPDATE SET "
        "value = (CASE WHEN app_settings.value ~ '^[0-9]+$' "
        "THEN app_settings.value::bigint ELSE 0 END + 1)::text, "
        "updated_at = now() RETURNING value"
    )
    result = await db.execute(query, {"key": key})
    tick = int(result.scalar_one())
    every = max(1, int(RECONCILE_EVERY_TICKS))
    return tick, tick % every == 0


async def _record_reconcile_success(db: AsyncSession) -> None:
    """Persist the last successful full reconciliation timestamp."""
    await db.execute(
        text(
            "INSERT INTO efhc_core.app_settings (key, value) "
            "VALUES ('scheduler.ton_reconcile_last_success_at', "
            "now()::text) ON CONFLICT (key) DO UPDATE SET "
            "value = EXCLUDED.value, updated_at = now()"
        )
    )


async def _notify_watcher_alert(
    db: AsyncSession,
    *,
    status: str,
    error_text: str,
    stats: dict[str, int] | None = None,
) -> None:
    payload = {
        "task_name": "check_ton_inbox",
        "status": status,
        "error_text": error_text,
        "stats": stats or {},
    }
    with suppress(Exception):
        await AdminNotifier.notify_generic(
            db,
            event="WATCHER_ALERT",
            message=(
                "⚠️ Watcher check_ton_inbox завершился с ошибкой\n"
                f"Статус: <b>{status}</b>\n"
                f"Ошибка: <code>{error_text}</code>"
            ),
            payload_json=_json_dump_safe(payload),
            send_telegram=True,
        )


async def _insert_scheduler_log(
    db: AsyncSession,
    *,
    status: str,
    error_text: str | None,
    duration_sec: float,
    stats: dict[str, int],
) -> None:
    """Audit one shared check using the deployed Genesis PostgreSQL schema.

    A failed SQL statement cannot be suppressed inside a PostgreSQL
    transaction: it leaves the transaction aborted and may silently discard
    the preceding activity watermark and financial watcher work.
    """
    await db.execute(
        text(
            "INSERT INTO efhc_core.scheduler_task_log "
            "(task_name, status, error_text, executed_at, duration_sec, "
            "payload, created_at, updated_at) "
            "VALUES ('check_ton_inbox', :status, :error_text, NOW(), :dur, "
            "CAST(:payload AS json), NOW(), NOW())"
        ),
        {
            "status": status,
            "error_text": error_text,
            "dur": max(0, int(duration_sec + 0.5)),
            "payload": _json_dump_safe(stats),
        },
    )


@dataclass
class TickResult:
    stats: dict[str, int]
    duration_sec: float
    status: str
    error_text: str | None = None


async def run_tick(
    db: AsyncSession,
    *,
    do_reconcile: bool = False,
) -> TickResult:
    start = time.perf_counter()
    stats: dict[str, int] = {}
    try:
        s1 = await watcher.process_incoming_payments(
            db,
            limit=TON_POLL_LIMIT,
            since_utime=None,
        )
        stats["new_ok"] = sum(
            v for k, v in s1.items() if not k.startswith("error")
        )
        for k, v in s1.items():
            kk = f"new_{k}"
            stats[kk] = stats.get(kk, 0) + int(v)

        s2 = await watcher.reprocess_unfinished_logs(
            db,
            limit=TON_RETRY_LIMIT,
        )
        stats["retry_ok"] = sum(
            v for k, v in s2.items() if not k.startswith("error")
        )
        for k, v in s2.items():
            kk = f"retry_{k}"
            stats[kk] = stats.get(kk, 0) + int(v)

        if do_reconcile:
            s3 = await watcher.reconcile_last_hours(
                db,
                hours=RECONCILE_HOURS,
                limit=TON_POLL_LIMIT,
            )
            stats["reconcile_ok"] = sum(
                v for k, v in s3.items() if not k.startswith("error")
            )
            for k, v in s3.items():
                kk = f"reconcile_{k}"
                stats[kk] = stats.get(kk, 0) + int(v)
            await _record_reconcile_success(db)

        dur = time.perf_counter() - start
        await _insert_scheduler_log(
            db,
            status="ok",
            error_text=None,
            duration_sec=dur,
            stats=stats,
        )
        return TickResult(stats=stats, duration_sec=dur, status="ok")

    except asyncio.CancelledError:
        logger.info("check_ton_inbox: tick cancelled")
        raise

    except Exception:
        logger.exception("check_ton_inbox: tick failed")
        raise


async def run_forever(
    session_factory: (
        Callable[[], AbstractAsyncContextManager[AsyncSession]] | None
    ) = None,
) -> None:
    """Compatibility loop using the canonical persistent run_once."""
    if session_factory is not None:
        logger.warning(
            "custom session_factory is ignored; use run_once tests"
        )
    while True:
        try:
            result = await run_once()
            logger.info(
                "check_ton_inbox: result=%s",
                result,
            )
            await asyncio.sleep(INTERVAL_SEC)
        except asyncio.CancelledError:
            logger.info(
                "check_ton_inbox: cancellation передан lifecycle owner"
            )
            raise


async def _activity_last_success(db: AsyncSession) -> datetime | None:
    """Persistent throttle across Render replicas and process restarts."""
    value = (await db.execute(
        text("SELECT value FROM efhc_core.app_settings "
             "WHERE key = 'scheduler.ton_activity_last_success_at' LIMIT 1")
    )).scalar_one_or_none()
    if not value:
        return None
    try:
        last = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return last.replace(tzinfo=timezone.utc) if last.tzinfo is None else last
    except ValueError:
        return None


async def _activity_record_success(db: AsyncSession) -> None:
    await db.execute(
        text("INSERT INTO efhc_core.app_settings (key, value) "
             "VALUES ('scheduler.ton_activity_last_success_at', :value) "
             "ON CONFLICT (key) DO UPDATE SET "
             "value = EXCLUDED.value, updated_at = now()"),
        {"value": datetime.now(timezone.utc).isoformat()},
    )


async def _run_activity_check(db: AsyncSession) -> dict[str, object]:
    """One bounded on-demand watcher pass; all credits use canonical bank service."""
    now = datetime.now(timezone.utc)
    last = await _activity_last_success(db)
    if last is not None and (now - last).total_seconds() < ACTIVITY_COOLDOWN_SEC:
        return {"status": "skipped", "reason": "cooldown", "stats": {}}

    # Replay since the last successful check, with a one-day overlap.
    # First run replays seven days. Exact tx_hash settlement prevents double credit.
    since = (max(0, int(last.timestamp()) - 86400) if last is not None
             else max(0, int(now.timestamp()) - ACTIVITY_REPLAY_SECONDS))
    started = time.perf_counter()
    incoming = await watcher.process_incoming_payments(
        db, limit=TON_POLL_LIMIT, since_utime=since
    )
    if int(incoming.get("error_network", 0) or 0):
        raise RuntimeError("TON_ACTIVITY_UPSTREAM_UNAVAILABLE")
    retry = await watcher.reprocess_unfinished_logs(db, limit=TON_RETRY_LIMIT)
    stats = {f"incoming_{k}": int(v) for k, v in incoming.items()}
    stats.update({f"retry_{k}": int(v) for k, v in retry.items()})
    await _activity_record_success(db)
    await _insert_scheduler_log(
        db, status="ok", error_text=None,
        duration_sec=time.perf_counter() - started, stats=stats,
    )
    await db.commit()
    return {"status": "ok", "stats": stats}


async def run_once(*, activity_trigger: bool = False) -> dict[str, object]:
    """One watcher pass; activity mode is user-triggered, bounded and throttled."""
    if activity_trigger and _LOCAL_LOCK.locked():
        return {"status": "skipped", "reason": "local_lock_held", "stats": {}}
    # The canonical ledger commits each credited operation inside its own
    # transaction. Hold the cross-replica XACT advisory lock on a DIFFERENT
    # DB session; otherwise those bank commits release the lock mid-scan.
    async with _LOCAL_LOCK, db_session() as lock_db, db_session() as db:
        got_lock = await _try_acquire_advisory_lock(lock_db)
        if not got_lock:
            return {
                "status": "skipped",
                "reason": "advisory_lock_held",
                "stats": {},
            }
        try:
            if activity_trigger:
                async with asyncio.timeout(TASK_TIMEOUT_SEC):
                    return await _run_activity_check(db)
            tick_no, do_reconcile = await _next_reconcile_tick(db)
            async with asyncio.timeout(TASK_TIMEOUT_SEC):
                res = await run_tick(db, do_reconcile=do_reconcile)
            await db.commit()
            return {
                "status": res.status,
                "duration_sec": res.duration_sec,
                "stats": res.stats,
                "error_text": res.error_text,
                "tick_no": tick_no,
                "reconcile": do_reconcile,
            }
        except TimeoutError:
            await db.rollback()
            logger.warning("check_ton_inbox: tick timeout")
            return {
                "status": "timeout_error",
                "error_code": "SCHEDULER_TIMEOUT",
                "stats": {},
            }
        except asyncio.CancelledError:
            await db.rollback()
            logger.info("check_ton_inbox: run_once cancelled")
            raise
        except Exception:
            await db.rollback()
            logger.exception("check_ton_inbox: run_once failed")
            return {
                "status": "error",
                "error_code": "SCHEDULER_INTERNAL_ERROR",
                "stats": {},
            }
        finally:
            # XACT lock is held until the dedicated session explicitly ends.
            await lock_db.rollback()
            await _release_advisory_lock(lock_db)
