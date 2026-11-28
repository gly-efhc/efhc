# backend/app/scheduler/generate_energy.py
# ======================================================================
# Назначение кода:
# Планировочная задача «начисление энергии».
#
# Канон:
# • Время — триггер. Сервис сам определяет, кого и сколько обновлять.
# • Денежная точность: Decimal(8) и округление DOWN — внутри сервисов.
# • Serverless: этот модуль выполняется «одним проходом» и возвращает
# статистику.
# ======================================================================

from __future__ import annotations

from typing import Any

from app.core.database_core import db_session
from app.core.logging_core import get_logger
from app.services.energy_service import generate_energy_tick
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = get_logger("efhc.scheduler.generate_energy")


class _EnergySettings(BaseSettings):
    """Настройки батча для начисления энергии (serverless)."""

    ENERGY_BATCH_SIZE: int = Field(
        default=50,
        validation_alias=AliasChoices(
            "ENERGY_BATCH_SIZE",
            "SCHED_ENERGY_BATCH_SIZE",
        ),
        description="Сколько пользователей обновлять за один тик",
    )

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


S = _EnergySettings()


async def run_once() -> dict[str, Any]:
    """Один проход начисления энергии."""
    async with db_session() as db:
        stats = await generate_energy_tick(
            db,
            batch_size=int(S.ENERGY_BATCH_SIZE),
        )
        return {"energy": stats}


__all__ = ["run_once"]
