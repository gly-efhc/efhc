from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("aiogram")

from app.bot.handlers import ranks_handlers
from app.services.ranks_service import RankRow, RankSnapshotMeta

pytestmark = pytest.mark.asyncio


class _Message:
    def __init__(self, tg_id: int):
        self.from_user = SimpleNamespace(id=tg_id)
        self.answer = AsyncMock()


async def test_ranks_handler_uses_top_limit(monkeypatch):
    captured: dict[str, int] = {}

    async def fake_rank(db, *, global_id: int, top_limit: int = 100):
        captured["global_id"] = int(global_id)
        captured["top_limit"] = int(top_limit)
        return (
            RankRow(
                global_id=700201,
                username="me",
                total_kwh="9.00000000",
                rank=1,
                is_vip=False,
            ),
            [
                RankRow(
                    global_id=700202,
                    username="top",
                    total_kwh="8.00000000",
                    rank=2,
                    is_vip=False,
                )
            ],
            RankSnapshotMeta(
                snapshot_at=datetime.now(UTC),
                total_users=2,
            ),
        )

    monkeypatch.setattr(
        ranks_handlers,
        "get_user_by_telegram_subject",
        AsyncMock(
            return_value=SimpleNamespace(
                global_id=700201,
                tg_id=900201,
            )
        ),
    )
    monkeypatch.setattr(
        ranks_handlers,
        "get_user_rank_and_top",
        fake_rank,
    )

    message = _Message(900201)
    await ranks_handlers.cmd_ranks(message, db=AsyncMock())

    assert captured == {"global_id": 700201, "top_limit": 10}
    message.answer.assert_awaited_once()
    body = message.answer.await_args.args[0]
    assert "top" in body or "2" in body


async def test_ranks_handler_logs_exception_and_falls_back(monkeypatch):
    async def failing_rank(db, *, global_id: int, top_limit: int = 100):
        raise RuntimeError("boom")

    logger = SimpleNamespace(exception=AsyncMock())
    exception_calls = []

    def exception_spy(message: str):
        exception_calls.append(message)

    logger.exception = exception_spy
    monkeypatch.setattr(
        ranks_handlers,
        "get_user_by_telegram_subject",
        AsyncMock(
            return_value=SimpleNamespace(
                global_id=700202,
                tg_id=900202,
            )
        ),
    )
    monkeypatch.setattr(
        ranks_handlers,
        "get_user_rank_and_top",
        failing_rank,
    )
    monkeypatch.setattr(ranks_handlers, "logger", logger)

    message = _Message(900202)
    await ranks_handlers.cmd_ranks(message, db=AsyncMock())

    assert exception_calls == ["Failed to load ranks for bot user"]
    message.answer.assert_awaited_once()
