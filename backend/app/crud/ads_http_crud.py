"""Data access for the advertising HTTP use cases; no reward or commit policy."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.ads_models import AdEvent, AdSession
from app.models.tasks_models import Task
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


async def read_user_language_metadata(db: AsyncSession, *, global_id: int) -> Any:
    row = (
        await db.execute(
            text("SELECT meta FROM efhc_core.users WHERE global_id=:gid LIMIT 1"),
            {"gid": global_id},
        )
    ).scalar_one_or_none()
    return row


async def find_recent_adsgram_session(db: AsyncSession, *, global_id: int, cutoff: datetime) -> AdSession | None:
    session = (
        await db.execute(
            select(AdSession)
            .where(
                AdSession.global_id == global_id,
                AdSession.actual_provider == "adsgram",
                AdSession.started_at >= cutoff,
            )
            .order_by(AdSession.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return session


async def find_adsgram_reward_signal(db: AsyncSession, *, provider_event_id: str) -> Any:
    existing = (
        await db.execute(
            select(AdEvent.id).where(
                AdEvent.provider == "adsgram",
                AdEvent.provider_event_id == provider_event_id,
                AdEvent.event_type == "postback_received",
            ).limit(1)
        )
    ).scalar_one_or_none()
    return existing


def add_adsgram_reward_signal(db: AsyncSession, *, session: AdSession, provider_event_id: str) -> None:
    db.add(
        AdEvent(
            session_id=session.session_id,
            provider="adsgram",
            task_code=session.task_code,
            event_type="postback_received",
            provider_event_id=provider_event_id,
            metadata_json={"source": "reward_url", "reward_authority": False},
        )
    )


async def find_ad_task(db: AsyncSession, *, task_code: str) -> Task | None:
    task = (
        await db.execute(select(Task).where(Task.code == task_code).limit(1))
    ).scalar_one_or_none()
    return task
