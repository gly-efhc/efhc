# backend/app/scheduler/update_ranks.py
# ======================================================================
# Назначение кода:
# Планировочная задача «пересчёт рейтинга» (Я + TOP).
#
# Канон:
# • Время — триггер. Пересчёт идёт по данным БД.
# • Scheduler тикает часто, но DB-backed claim допускает не более одного
#   canonical rebuild на UTC business-day после границы 02:00 UTC.
# • Результат фиксируется в users.rank_position/rank_score_kwh/rank_calculated_at.
# ======================================================================

from __future__ import annotations

from typing import Any

from app.core.database_core import db_session
from app.core.logging_core import get_logger
from app.services.ranks_service import run_daily_rank_update_if_due
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = get_logger("efhc.scheduler.update_ranks")


class RanksJobSettings(BaseSettings):
    """Настройки батча рейтинга (алиасы для удобства на Vercel)."""

    RANKS_LIMIT_USERS: int = Field(
        default=200,
        validation_alias=AliasChoices(
            "RANKS_LIMIT_USERS",
            "SCHED_RANKS_LIMIT_USERS",
        ),
    )

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


S = RanksJobSettings()


async def run_once() -> dict[str, Any]:
    """Один проход пересчёта рейтинга."""

    async with db_session() as db:
        # RANKS_LIMIT_USERS сохраняется как ENV compatibility alias,
        # но current product contract требует полный ranking universe.
        _ = S.RANKS_LIMIT_USERS
        meta, ran, claim_date = await run_daily_rank_update_if_due(db)

    logger.info(
        "update_ranks: snapshot_at=%s total_users=%s ran=%s claim_date=%s",
        meta.snapshot_at,
        meta.total_users,
        ran,
        claim_date.isoformat(),
    )
    return {
        "snapshot_at": meta.snapshot_at.isoformat(),
        "total_users": int(meta.total_users),
        "ran": bool(ran),
        "claim_date": claim_date.isoformat(),
    }


__all__ = ["run_once"]
