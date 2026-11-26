# backend/app/services/admin/admin_notifications.py
# ======================================================================
# EFHC Bot — Уведомления админам (БД + опционально Telegram)
# ======================================================================

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.sql_aliases_core import canon_schema
from app.identity.types import parse_global_id
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
S = get_settings()

SCHEMA_ADMIN: str = canon_schema(
    getattr(S, "DB_SCHEMA_ADMIN", "efhc_admin") or "efhc_admin",
)

try:  # pragma: no cover
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

BOT_TOKEN: str = str(getattr(S, "BOT_TOKEN", "") or "")


def _notification_chat_ids() -> list[str]:
    raw_list = getattr(S, "ADMIN_NOTIFICATIONS_CHAT_IDS", []) or []
    ids = [str(v).strip() for v in raw_list if str(v).strip()]
    single = str(
        getattr(S, "ADMIN_NOTIFICATIONS_CHAT_ID", "") or ""
    ).strip()
    if single and single not in ids:
        ids.append(single)
    return ids


# ======================================================================
# DTO
# ======================================================================


class AdminNotification(BaseModel):
    """Одна запись для отображения в админ-панели."""

    id: int
    event: str = Field(
        ...,
        description=("Код события (например NEW_WITHDRAWAL)"),
    )
    payload_json: str = Field(
        ...,
        description="JSON-полезная нагрузка (сырой текст)",
    )
    status: str = Field(
        ...,
        description="Статус обработки (NEW/SENT/ERROR/IGNORED)",
    )
    created_at: str = Field(
        ...,
        description="Создано (ISO8601 UTC)",
    )

    @field_validator("created_at", mode="before")
    @classmethod
    def _norm_created_at(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class NotificationsFilter(BaseModel):
    """Фильтр для списка уведомлений."""

    status: str | None = Field(
        default=None,
        description=(
            "Фильтр по статусу (например NEW/ERROR). "
            "None — все статусы."
        ),
    )
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort_desc: bool = Field(
        default=True,
        description="True — новые сверху",
    )


# ======================================================================
# Внутренние утилиты
# ======================================================================


async def _store_notification(
    db: AsyncSession,
    *,
    event: str,
    payload_json: str,
    status: str = "NEW",
) -> int:
    sql = text(
        "\n".join(
            [
                "INSERT INTO " + SCHEMA_ADMIN + ".admin_notifications",
                "(event, payload_json, status, created_at)",
                "VALUES (:e, :p, :s, NOW() AT TIME ZONE 'UTC')",
                "RETURNING id",
            ]
        )
    )
    r: Result = await db.execute(
        sql,
        {"e": event, "p": payload_json, "s": status},
    )
    return int(r.scalar_one())


async def _send_telegram_message(text_message: str) -> None:
    chat_ids = _notification_chat_ids()
    if not BOT_TOKEN or not chat_ids:
        return
    if httpx is None:  # type: ignore[truthy-function]
        logger.debug(
            "Admin notifications: httpx missing, Telegram disabled"
        )
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for chat_id in chat_ids:
                payload = {
                    "chat_id": chat_id,
                    "text": text_message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }
                await client.post(url, json=payload)
    except Exception as e:  # pragma: no cover
        logger.warning(
            "Admin notifications: Telegram send failed: %s",
            e,
        )


# ======================================================================
# Public API
# ======================================================================


class AdminNotifier:
    """Централизованный сервис уведомлений админам."""

    @staticmethod
    async def notify_generic(
        db: AsyncSession,
        *,
        event: str,
        message: str,
        payload_json: str = "{}",
        send_telegram: bool = True,
    ) -> int:
        if not event or not isinstance(event, str):
            raise ValueError("event должен быть непустой строкой")

        if not payload_json:
            payload_json = "{}"

        notif_id = await _store_notification(
            db,
            event=event,
            payload_json=payload_json,
            status="NEW",
        )

        if send_telegram:
            await _send_telegram_message(
                f"🔔 {event}\n{message}\nNID: {notif_id}"
            )
        return notif_id

    @staticmethod
    async def send_telegram_after_commit(
        *,
        notification_id: int,
        event: str,
        message: str,
    ) -> None:
        """Доставить Telegram-уведомление только после DB commit.

        Денежные сервисы сначала сохраняют ``admin_notifications`` как
        outbox-запись в той же DB transaction, что и money+audit. Сетевой
        Telegram вызов выполняется уже после commit и не может откатить или
        скрыть финансовую операцию.
        """

        await _send_telegram_message(
            f"🔔 {event}\n{message}\nNID: {int(notification_id)}"
        )

    @staticmethod
    async def notify_new_withdrawal(
        db: AsyncSession,
        *,
        request_id: int,
        global_id: str,
        amount_efhc: str,
    ) -> int:
        gid = str(parse_global_id(global_id))
        payload = (
            f'{{"request_id":{int(request_id)},'
            f'"global_id":"{gid}",'
            f'"amount":"{amount_efhc}"}}'
        )
        message = (
            f"💸 Новая заявка на вывод #{int(request_id)}\n"
            f"Аккаунт: <code>G{gid}</code>\n"
            f"Сумма: <b>{amount_efhc} EFHC</b>"
        )
        return await AdminNotifier.notify_generic(
            db,
            event="NEW_WITHDRAWAL",
            message=message,
            payload_json=payload,
            send_telegram=True,
        )
