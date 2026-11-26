# backend/app/scheduler/tasks_autorestart.py
# ======================================================================
# Назначение кода:
# Планировочная задача обслуживания системы заданий (Tasks).
#
# В данном проекте «autorestart» трактуется как обслуживание:
# • Очистка таблицы task_complete_lock от старых записей (ретеншен).
# • Снижение риска раздувания таблицы и ускорение запросов.
#
# Канон:
# • Время — триггер.
# • Никаких денег в планировщике. Денежные начисления в tasks_service.
# ======================================================================

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, cast

from app.core.database_core import db_session
from app.core.logging_core import get_logger
from app.lib.time import utcnow
from sqlalchemy import text

logger = get_logger("efhc.scheduler.tasks")


def _utcnow() -> datetime:
    """Текущее время в UTC."""
    return cast(datetime, utcnow())


async def run_once() -> dict[str, Any]:
    """Один проход обслуживания таблиц Tasks."""
    # Ретеншен можно подкрутить через ENV
    retention_days = int(os.getenv("TASKS_LOCK_RETENTION_DAYS", "45"))
    cutoff = _utcnow() - timedelta(days=retention_days)

    deleted = 0
    try:
        async with db_session() as db:
            q = text(
                "DELETE FROM efhc_core.task_complete_lock\n"
                "WHERE credited = TRUE\n"
                "AND created_at < :cutoff"
            )
            res = await db.execute(q, {"cutoff": cutoff})
            deleted = int(getattr(res, "rowcount", 0) or 0)
            await db.commit()
    except Exception as e:
        logger.exception("tasks_autorestart: failed: %s", e)
        return {
            "ok": False,
            "deleted": deleted,
            "retention_days": retention_days,
            "error": str(e),
        }

    return {
        "ok": True,
        "deleted": deleted,
        "retention_days": retention_days,
    }


__all__ = ["run_once"]
