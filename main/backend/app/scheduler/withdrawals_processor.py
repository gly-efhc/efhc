# backend/app/scheduler/withdrawals_processor.py
# ======================================================================
# Назначение кода:
# Обслуживание очереди заявок на вывод.
#
# Канон:
# • Выводы в EFHC требуют админ-подтверждения.
# • Автоматическая часть в планировщике — это контроль/уведомления:
# - сколько pending,
# - есть ли заявки, которые «залипли» слишком долго.
#
# Реальная отправка средств (TON/... на кошелёк пользователя) здесь НЕ
# выполняется.
# ======================================================================

from __future__ import annotations

import json
from datetime import timedelta

from app.core.database_core import db_session
from app.core.logging_core import get_logger
from app.lib.time import utcnow
from app.models.transactions_models import WithdrawalRequest
from app.services.admin.admin_notifications import AdminNotifier
from sqlalchemy import select

logger = get_logger("efhc.scheduler.withdrawals")


def _utcnow():
    """UTC now для задач планировщика."""
    return utcnow()


async def run_once() -> dict[str, int]:
    """Один проход: метрики очереди и уведомление админа."""
    async with db_session() as db:
        q = await db.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.status == "PENDING"
            )
        )
        pending = q.scalars().all()

        pending_count = len(pending)
        stale_cutoff = _utcnow() - timedelta(days=3)
        stale_count = sum(
            1
            for r in pending
            if (r.created_at or _utcnow()) < stale_cutoff
        )

        # Логи — всегда.
        logger.info(
            "withdrawals: pending=%s stale=%s",
            pending_count,
            stale_count,
        )

        # Telegram админу — если есть stale.
        if stale_count > 0:
            threshold_days = 3
            message = (
                f"Pending withdrawals: {pending_count}\n"
                f"Stale (>{threshold_days}d): {stale_count}"
            )
            payload_json = json.dumps(
                {
                    "pending_count": int(pending_count),
                    "stale_count": int(stale_count),
                    "threshold_days": int(threshold_days),
                    "source": "withdrawals_processor",
                },
                ensure_ascii=False,
            )
            try:
                notification_id = await AdminNotifier.notify_generic(
                    db,
                    event="withdrawals.stale",
                    message=message,
                    payload_json=payload_json,
                    send_telegram=True,
                )
                logger.info(
                    "withdrawals: stale notification id=%s",
                    notification_id,
                )
            except Exception:
                logger.exception(
                    "withdrawals: stale notification failed"
                )

        return {
            "pending": pending_count,
            "stale": stale_count,
        }


__all__ = ["run_once"]
