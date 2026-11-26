from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("aiogram")

from app.bot.handlers import referrals_handlers
from app.services.referral_service import ReferralStats

pytestmark = pytest.mark.asyncio


class _Message:
    def __init__(self, tg_id: int):
        self.from_user = SimpleNamespace(id=tg_id)
        self.answer = AsyncMock()


async def test_referrals_handler_resolves_inviter_global_id(monkeypatch):
    captured: dict[str, int] = {}

    async def fake_stats(db, *, inviter_global_id: int):
        captured["inviter_global_id"] = int(inviter_global_id)
        return ReferralStats(
            inviter_global_id=inviter_global_id,
            total_referrals=5,
            active_referrals=2,
            level=0,
            next_level=1,
            current_level_min=0,
            next_level_min=10,
            refs_to_next=8,
            progress=0.2,
            referral_code="ABC",
            referral_link=None,
        )

    monkeypatch.setattr(
        referrals_handlers,
        "get_user_by_telegram_subject",
        AsyncMock(
            return_value=SimpleNamespace(
                tg_id=900101,
                global_id=1000000101,
            )
        ),
    )
    monkeypatch.setattr(
        referrals_handlers,
        "get_referral_stats",
        fake_stats,
    )

    message = _Message(900101)
    await referrals_handlers.cmd_referrals(message, db=AsyncMock())

    assert captured == {"inviter_global_id": 1000000101}
    message.answer.assert_awaited_once()
