"""Optional energy-only DEMO scheduler; never starts blockchain agents."""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("efhc.demo_backend.scheduler")


async def periodic_energy(stop: asyncio.Event, period: int) -> None:
    from app.scheduler.generate_energy import run_once
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=period)
        except TimeoutError:
            try:
                await run_once()
            except Exception:
                log.exception("DEMO_NEON_ENERGY_TICK_FAILED")
