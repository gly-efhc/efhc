# backend/app/scheduler/ads_rotation.py
# ======================================================================
# Назначение кода:
# Планировочная задача ротации/валидации рекламных объявлений.
#
# Примечание:
# В каноне допускается, что ротатор — это «санитар»:
# • деактивирует объявления, у которых истёк ends_at,
# • активирует те, которые в окне (starts_at <= now <= ends_at).
#
# Конкретный алгоритм показа (рандом/вес/приоритет) реализуется в
# API/фронте.
# ======================================================================

from __future__ import annotations

from typing import Any

from app.core.database_core import db_session
from app.core.logging_core import get_logger
from sqlalchemy import text

logger = get_logger("efhc.scheduler.ads_rotation")


async def run_once() -> dict[str, Any]:
    """Один проход обслуживания Ads."""
    async with db_session() as db:
        # Истёкшие объявления -> inactive
        q_expire = text(
            "UPDATE efhc_core.ads\n"
            "SET status = 'inactive'\n"
            "WHERE status = 'active'\n"
            "AND ends_at IS NOT NULL\n"
            "AND ends_at < NOW()"
        )
        q1 = await db.execute(q_expire)
        expired = int(getattr(q1, "rowcount", 0) or 0)

        # Те, что попали в окно -> active (если были draft)
        q_activate = text(
            "UPDATE efhc_core.ads\n"
            "SET status = 'active'\n"
            "WHERE status IN ('draft', 'inactive')\n"
            "AND (starts_at IS NULL OR starts_at <= NOW())\n"
            "AND (ends_at IS NULL OR ends_at >= NOW())"
        )
        q2 = await db.execute(q_activate)
        activated = int(getattr(q2, "rowcount", 0) or 0)

        await db.commit()

    logger.info(
        "ads_rotation: expired=%s activated=%s",
        expired,
        activated,
    )
    return {
        "expired": expired,
        "activated": activated,
    }


__all__ = ["run_once"]
