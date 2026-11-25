# backend/app/scheduler/reports_daily.py
# ======================================================================
# Назначение кода:
# Ежедневный отчёт для администратора.
#
# Подтверждено пользователем:
# • Храним в логах (таблица админ-уведомлений/логов) И
# • Отправляем админу в Telegram (ADMIN_TG_ID) через Bot API.
#
# Канон:
# • Без секретов в коде. BOT_TOKEN, ADMIN_TG_ID — только из ENV.
# ======================================================================

from __future__ import annotations

import json
from typing import Any

from app.core.config_core import get_settings
from app.core.database_core import db_session
from app.core.logging_core import get_logger
from app.lib.time import utcnow
from app.services.admin.admin_notifications import AdminNotifier
from app.services.reports_service import daily_admin_summary
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("efhc.scheduler.reports_daily")


async def _write_log(
    db: AsyncSession,
    title: str,
    payload: dict[str, Any],
) -> None:
    """Запись отчёта в админ - лог (таблица admin_events, если есть)."""
    get_settings()
    # Best-effort запись изолирована savepoint и не владеет root-транзакцией.
    try:
        from sqlalchemy import text

        async with db.begin_nested():
            q = text(
                "INSERT INTO efhc_core.admin_events "
                "(event_type, title, payload, created_at) "
                "VALUES (:t, :title, :payload, NOW())"
            )
            await db.execute(
                q,
                {
                    "t": "daily_report",
                    "title": title,
                    "payload": json.dumps(payload, ensure_ascii=False),
                },
            )
    except Exception:
        logger.info(
            "daily_report: admin_events table not available; "
            "stored in logs only"
        )


async def run_once() -> dict[str, Any]:
    """Собирает ежедневный отчёт и отправляет админу."""
    s = get_settings()

    async with db_session() as db:
        try:
            report = await daily_admin_summary(db, days=1)

            title = (
                f"EFHC Daily Report • "
                f"{utcnow().date().isoformat()}"
            )
            await _write_log(db, title=title, payload=report)

            # Отправка в Telegram админу
            msg = (
                "EFHC Daily Report\n"
                + json.dumps(report, ensure_ascii=False, default=str)
            )
            payload_json = json.dumps(
                {
                    "source": "reports_daily",
                    "date": utcnow().date().isoformat(),
                    "summary": report,
                },
                ensure_ascii=False,
                default=str,
            )
            notification_id: int | None = None
            try:
                notification_id = await AdminNotifier.notify_generic(
                    db,
                    event="reports.daily",
                    message=msg,
                    payload_json=payload_json,
                    send_telegram=True,
                )
            except Exception:
                logger.exception("daily_report: notification failed")

            await db.commit()
            return {
                "report": report,
                "sent_to_admin": (
                    notification_id is not None
                    and bool(s.BOT_TOKEN and s.ADMIN_TG_ID)
                ),
                "notification_id": notification_id,
            }
        except BaseException:
            await db.rollback()
            raise


__all__ = ["run_once"]
