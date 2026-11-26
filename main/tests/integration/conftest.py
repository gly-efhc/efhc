"""Shared fixtures for real PostgreSQL referral integration tests."""

from __future__ import annotations

import itertools
from collections.abc import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_TG_SEQUENCE = itertools.count(8_840_000_000_000)


@pytest.fixture
def next_referral_tg_id() -> Callable[[], int]:
    """Return collision-free Telegram IDs for one pytest process."""

    def _next() -> int:
        return next(_TG_SEQUENCE)

    return _next


@pytest.fixture
def integration_session_factory(
    async_engine,
) -> async_sessionmaker[AsyncSession]:
    """Independent sessions for concurrency tests on the migrated DB."""
    return async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
