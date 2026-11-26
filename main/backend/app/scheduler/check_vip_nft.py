# backend/app/scheduler/check_vip_nft.py
# ======================================================================
# Планировщик: проверить VIP по владению NFT.
# ======================================================================

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.services import nft_check_service
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()
logger = get_logger(__name__)

RETRY_ON_ERROR_SEC = 60
DEFAULT_BATCH_LIMIT = 1000


async def run_check_vip_nft_once(
    db: AsyncSession,
    *,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
    force: bool = False,
) -> dict[str, Any]:
    """Один канонический прогон NFT/VIP/Admin-NFT проверки."""
    result = await nft_check_service.check__all__users_once(
        db,
        batch_size=int(batch_limit),
        force_refresh=bool(force),
    )
    return {
        "processed": int(result.get("total", 0)),
        "updated": int(result.get("changed", 0)),
        "left": 0,
        "batches": int(result.get("batches", 0)),
    }


async def scheduler_tick_check_vip_nft(
    db: AsyncSession,
) -> dict[str, Any]:
    """Один тик выполняет ровно один полный NFT/VIP проход."""

    t0 = time.monotonic()
    step = await run_check_vip_nft_once(
        db,
        batch_limit=DEFAULT_BATCH_LIMIT,
        force=False,
    )
    took_ms = int((time.monotonic() - t0) * 1000)
    return {
        "total_processed": int(step.get("processed", 0)),
        "total_updated": int(step.get("updated", 0)),
        "batches": int(step.get("batches", 0)),
        "last_step": step,
        "took_ms": took_ms,
    }


async def scheduler_task_check_vip_nft(
    session_factory: Callable[[], AsyncSession],
    stop_event: asyncio.Event | None = None,
) -> None:
    """Фоновый цикл тиков; при ошибках — лог + пауза + следующий тик."""
    if settings.SCHEDULER_TICK_SECONDS:
        tick_sec = int(settings.SCHEDULER_TICK_SECONDS)
    else:
        tick_sec = 600

    logger.info(
        "VIP NFT checker started: tick=%ss, batch_limit=%s",
        tick_sec,
        DEFAULT_BATCH_LIMIT,
    )

    while True:
        t_loop_start = time.monotonic()
        try:
            async with session_factory() as db:
                stats = await scheduler_tick_check_vip_nft(db)
                await db.commit()
                logger.info(
                    "VIP NFT tick ok: processed=%s updated=%s "
                    "batches=%s took=%sms",
                    stats.get("total_processed"),
                    stats.get("total_updated"),
                    stats.get("batches"),
                    stats.get("took_ms"),
                )
        except asyncio.CancelledError:
            logger.warning("VIP NFT checker: cancellation передан lifecycle owner")
            raise
        except Exception as e:
            logger.warning(
                "VIP NFT tick failed: %s",
                e,
                exc_info=settings.is_dev,
            )
            await asyncio.sleep(RETRY_ON_ERROR_SEC)

        elapsed = time.monotonic() - t_loop_start
        sleep_for = max(1.0, tick_sec - elapsed)

        if stop_event is not None and stop_event.is_set():
            logger.info("VIP NFT checker stop requested")
            break

        await asyncio.sleep(sleep_for)


async def run_once() -> dict[str, Any]:
    """Serverless entrypoint: один тик проверки VIP NFT."""
    from app.core.database_core import db_session

    async with db_session() as db:
        try:
            stats = await scheduler_tick_check_vip_nft(db)
            await db.commit()
            return stats
        except BaseException:
            await db.rollback()
            raise


__all__ = [
    "run_once",
    "run_check_vip_nft_once",
    "scheduler_tick_check_vip_nft",
    "scheduler_task_check_vip_nft",
]
