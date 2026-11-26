# backend/app/scheduler/healthcheck_ping.py
# ======================================================================
# Назначение кода:
# Лёгкий health-ping job. Нужен, чтобы планировщик мог подтверждать
# «я жив», а также чтобы иметь точку для будущих интеграций (Prometheus,
# Sentry).
#
# Важно:
# Этот job НИКАК не влияет на деньги. Это телеметрия.
# ======================================================================

from __future__ import annotations

from typing import Any

from app.core.logging_core import get_logger

logger = get_logger("efhc.scheduler.health")


async def run_once() -> dict[str, Any]:
    """Лёгкий ping планировщика.

    Этот job не влияет на деньги. Нужен как сигнал "жив" и как
    точка расширения для будущей телеметрии.
    """
    logger.info("healthcheck_ping: ok")
    return {"ok": True}


__all__ = ["run_once"]
