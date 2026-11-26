# backend/app/scheduler/archive_panels.py
# ======================================================================
# Назначение кода:
# Планировочная задача «архивация панелей», которые считаются
# просроченными
# по правилам бизнес-логики (если предусмотрено).
#
# Канон:
# • Время — триггер. Сервис сам выбирает просроченные панели.
# ======================================================================

from __future__ import annotations

from typing import Any

from app.core.database_core import db_session
from app.core.logging_core import get_logger
from app.services.panels_service import archive_expired_panels
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = get_logger("efhc.scheduler.archive_panels")


class _Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    PANELS_ARCHIVE_BATCH_SIZE: int = Field(
        default=200,
        validation_alias=AliasChoices(
            "PANELS_ARCHIVE_BATCH_SIZE",
            "SCHED_PANELS_ARCHIVE_BATCH_SIZE",
        ),
    )


S = _Settings()


async def run_once() -> dict[str, Any]:
    """Архивация панелей — один проход."""
    async with db_session() as db:
        res = await archive_expired_panels(
            db,
            limit=int(S.PANELS_ARCHIVE_BATCH_SIZE),
        )
        await db.commit()

    logger.info("archive_panels: %s", res)
    return {"archived": int(res)}


__all__ = ["run_once"]
