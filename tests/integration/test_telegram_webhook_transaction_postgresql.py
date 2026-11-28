import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from app.routes import system_routes
from app.services.referral_service import (
    onboard_user_at_first_creation_in_transaction,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.asyncio


class FakeRequest:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.state = SimpleNamespace(_raw_body=None)
        self._body = json.dumps(payload).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


def _prepare_route(
    monkeypatch: pytest.MonkeyPatch,
    process_update: Any,
) -> None:
    module = ModuleType("app.bot.bot")
    module.process_update = process_update
    monkeypatch.setitem(sys.modules, "app.bot.bot", module)
    monkeypatch.setattr(
        system_routes,
        "get_settings",
        lambda: SimpleNamespace(
            TELEGRAM_WEBHOOK_SECRET="",
            env_normalized="ci",
        ),
    )


async def _call(
    db: AsyncSession,
    *,
    event_id: str,
    update_id: int,
) -> dict[str, Any]:
    return await system_routes.telegram_webhook(
        FakeRequest({"update_id": update_id}),
        x_telegram_bot_api_secret_token=None,
        db=db,
        x_event_id=event_id,
        x_delivery_id=None,
        x_update_id=None,
    )


async def _marker_count(async_engine, event_id_hash: str | None = None) -> int:
    query = "SELECT COUNT(*) FROM efhc_core.processed_external_events"
    params: dict[str, Any] = {}
    if event_id_hash is not None:
        query += " WHERE provider='telegram' AND event_id=:event_id"
        params["event_id"] = event_id_hash
    async with async_engine.connect() as conn:
        return int((await conn.execute(text(query), params)).scalar_one())


async def test_concurrent_same_event_обрабатывается_один_раз(
    async_engine,
    db_clean,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Session = sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    first_processing = asyncio.Event()
    release_first = asyncio.Event()
    process_calls = 0

    async def process_update(**_kwargs: Any) -> None:
        nonlocal process_calls
        process_calls += 1
        if process_calls == 1:
            first_processing.set()
            await release_first.wait()

    _prepare_route(monkeypatch, process_update)

    async with Session() as db_a, Session() as db_b:
        task_a = asyncio.create_task(
            _call(db_a, event_id="pg-concurrent-success", update_id=10001)
        )
        await first_processing.wait()
        task_b = asyncio.create_task(
            _call(db_b, event_id="pg-concurrent-success", update_id=10001)
        )
        await asyncio.sleep(0)
        release_first.set()
        result_a, result_b = await asyncio.gather(task_a, task_b)

    assert process_calls == 1
    assert {tuple(sorted(result_a.items())), tuple(sorted(result_b.items()))} == {
        (("status", "ok"),),
        (("dedupe", True), ("status", "ok")),
    }
    assert await _marker_count(async_engine) == 1


async def test_concurrent_event_после_rollback_может_обработаться(
    async_engine,
    db_clean,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Session = sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    first_processing = asyncio.Event()
    fail_first = asyncio.Event()
    process_calls = 0
    successful_calls = 0

    async def process_update(**_kwargs: Any) -> None:
        nonlocal process_calls, successful_calls
        process_calls += 1
        if process_calls == 1:
            first_processing.set()
            await fail_first.wait()
            raise RuntimeError("first processing failed")
        successful_calls += 1

    _prepare_route(monkeypatch, process_update)

    async with Session() as db_a, Session() as db_b:
        task_a = asyncio.create_task(
            _call(db_a, event_id="pg-concurrent-rollback", update_id=10002)
        )
        await first_processing.wait()
        task_b = asyncio.create_task(
            _call(db_b, event_id="pg-concurrent-rollback", update_id=10002)
        )
        await asyncio.sleep(0)
        fail_first.set()
        results = await asyncio.gather(task_a, task_b, return_exceptions=True)

    assert any(
        isinstance(item, RuntimeError) and str(item) == "first processing failed"
        for item in results
    )
    assert any(item == {"status": "ok"} for item in results)
    assert successful_calls == 1
    assert await _marker_count(async_engine) == 1


async def test_webhook_root_transaction_включает_start_registration(
    async_engine,
    db_clean,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Session = sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    tg_id = 9_917_901
    first = True

    async def process_update(*, db: AsyncSession, payload: dict[str, Any]) -> None:
        nonlocal first
        await onboard_user_at_first_creation_in_transaction(
            db,
            tg_id=tg_id,
            username="webhook_root_tx",
        )
        if first:
            first = False
            raise RuntimeError("fail after onboarding mutation")

    _prepare_route(monkeypatch, process_update)

    async with Session() as db:
        with pytest.raises(RuntimeError, match="fail after onboarding mutation"):
            await _call(db, event_id="pg-start-root-tx", update_id=10003)

    async with async_engine.connect() as conn:
        assert int(
            (
                await conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM efhc_core.users
                        WHERE username=:username
                        """
                    ),
                    {"username": "webhook_root_tx"},
                )
            ).scalar_one()
        ) == 0
        assert int(
            (
                await conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM efhc_core.user_identities
                        WHERE provider='telegram'
                          AND provider_subject=:subject
                        """
                    ),
                    {"subject": str(tg_id)},
                )
            ).scalar_one()
        ) == 0
        assert int(
            (
                await conn.execute(
                    text("SELECT COUNT(*) FROM efhc_core.referral_links")
                )
            ).scalar_one()
        ) == 0
        assert int(
            (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM efhc_core.processed_external_events"
                    )
                )
            ).scalar_one()
        ) == 0

    async with Session() as db:
        assert await _call(
            db,
            event_id="pg-start-root-tx",
            update_id=10003,
        ) == {"status": "ok"}

    async with async_engine.connect() as conn:
        assert int(
            (
                await conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM efhc_core.users
                        WHERE username=:username
                        """
                    ),
                    {"username": "webhook_root_tx"},
                )
            ).scalar_one()
        ) == 1
        assert int(
            (
                await conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM efhc_core.user_identities
                        WHERE provider='telegram'
                          AND provider_subject=:subject
                        """
                    ),
                    {"subject": str(tg_id)},
                )
            ).scalar_one()
        ) == 1
        assert int(
            (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM efhc_core.processed_external_events"
                    )
                )
            ).scalar_one()
        ) == 1
