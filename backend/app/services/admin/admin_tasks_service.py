"""Административные helpers контура заданий.

Модуль оставляет единый безопасный вход для ручного запуска обслуживания
idempotency-locks из Admin Panel. Денежных операций здесь нет.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


async def force_tasks_sync(db: AsyncSession) -> dict[str, Any]:
    """Запустить безопасное обслуживание idempotency-locks заданий.

    Название функции сохранено как compatibility boundary. Фактическая
    операция не «синхронизирует статусы» заданий: она вызывает canonical
    scheduler maintenance и удаляет только старые credited-locks согласно
    TASKS_LOCK_RETENTION_DAYS.
    """
    del db
    try:
        from app.scheduler.tasks_autorestart import run_once
    except Exception:
        return {
            "ok": False,
            "detail": "Контур обслуживания заданий недоступен",
            "deleted": 0,
            "retention_days": None,
        }

    result = await run_once()
    deleted = int(result.get("deleted", 0) or 0)
    retention_days = int(result.get("retention_days", 0) or 0)
    if result.get("ok"):
        return {
            "ok": True,
            "detail": (
                "Обслуживание Tasks завершено; удалено старых "
                f"credited-locks: {deleted}"
            ),
            "deleted": deleted,
            "retention_days": retention_days,
        }
    return {
        "ok": False,
        "detail": result.get("error") or "Обслуживание Tasks завершилось ошибкой",
        "deleted": deleted,
        "retention_days": retention_days or None,
    }
