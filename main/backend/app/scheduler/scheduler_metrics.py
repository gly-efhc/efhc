# backend/app/scheduler/scheduler_metrics.py
# =====================================================================
# EFHC Bot — Scheduler metrics / monitoring hooks
#
# Назначение:
# • Централизованная фиксация событий планировщика.
# • Опциональные алерты админам (Telegram) при сбоях.
#
# Канон:
# • Секреты/ключи не логируются.
# • Настройки берутся только из .env (через config_core).
# =====================================================================

from __future__ import annotations

from app.core.config_core import get_settings
from app.core.logging_core import get_logger

logger = get_logger(__name__)
S = get_settings()

try:  # pragma: no cover
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # type: ignore[assignment]


def _alert_chat_id() -> str:
    return str(getattr(S, "SCHEDULER_ALERTS_CHAT_ID", "") or "")


def _bot_token() -> str:
    # Используем каноничный BOT_TOKEN из env.
    return str(getattr(S, "BOT_TOKEN", "") or "")


async def send_scheduler_alert(
    text_message: str,
    *,
    disable_preview: bool = True,
) -> None:
    """Отправляет алерт админам в Telegram (если включено env)."""

    token = _bot_token()
    chat_id = _alert_chat_id()
    if not token or not chat_id:
        return
    if httpx is None:  # type: ignore[truthy-function]
        logger.debug("Scheduler alerts: httpx missing")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text_message,
        "disable_web_page_preview": bool(disable_preview),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
    except Exception as e:  # pragma: no cover
        logger.warning("Scheduler alerts: send failed: %s", e)


def metric_event(name: str, value: float = 1.0) -> None:
    """No-op хук метрик для планировщика.

    Важно:
    • В serverless метрики часто снимаются логами/внешним APM.
    • Этот хук оставлен как единая точка интеграции.

    """

    _ = value
    if not name:
        return
    logger.info("scheduler_metric name=%s", name)


async def metric_error(
    name: str,
    *,
    detail: str | None = None,
    alert: bool = True,
) -> None:
    """Фиксирует сбой планировщика и опционально алертит админов."""

    if not name:
        name = "scheduler_error"

    msg = f"⚠️ SCHEDULER ERROR: {name}"
    if detail:
        msg = f"{msg}\n{detail}"

    logger.warning("%s", msg)
    if alert:
        await send_scheduler_alert(msg)
