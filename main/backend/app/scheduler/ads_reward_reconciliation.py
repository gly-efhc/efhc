"""Адаптер планировщика для независимого доведения ADS-наград."""

from __future__ import annotations

from typing import cast

from app.core.database_core import db_session
from app.services.ads.ad_manager import reconcile_due_ad_rewards


async def run_once() -> dict[str, int]:
    """Один bounded проход unpaid verified ADS rewards."""
    async with db_session() as db:
        try:
            result = await reconcile_due_ad_rewards(db, limit=100)
            return cast(dict[str, int], result)
        except BaseException:
            await db.rollback()
            raise


__all__ = ["run_once"]
