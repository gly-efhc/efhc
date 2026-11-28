from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.identity.financial_owner import FinancialReadOwner
from app.routes import me_routes
from app.services.nft_check_service import (
    NftCheckService,
    _fetch_wallet_candidates_batch,
)


class _FakeResult:
    def __init__(self, rows: list[SimpleNamespace] | None = None):
        self._rows = rows or []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _WalletResolverDb:
    def __init__(self, *, binding_wallet: str | None) -> None:
        self.binding_wallet = binding_wallet
        self.queries: list[str] = []

    async def execute(self, sql, params=None):
        query = str(sql)
        self.queries.append(query)
        if "FROM efhc_core.wallet_bindings" in query:
            rows = (
                [SimpleNamespace(wallet_address=self.binding_wallet)]
                if self.binding_wallet
                else []
            )
            return _FakeResult(rows)
        raise AssertionError("unexpected query: " + query)


class _WalletBatchDb:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.queries: list[str] = []

    async def execute(self, sql, params=None):
        query = str(sql)
        self.queries.append(query)
        assert "SELECT DISTINCT ON (wb.global_id)" in query
        assert "wallet_bindings" in query
        assert "users.ton_wallet" not in query
        return _FakeResult(self.rows)


@pytest.mark.asyncio
async def test_canonical_wallet_binding_is_used_when_user_ton_wallet_empty():
    db = _WalletResolverDb(binding_wallet="EQ_CANONICAL_BINDING")

    wallet = await NftCheckService.get_wallet_for_user(db, global_id=1234567001)  # type: ignore[arg-type]

    assert wallet == "EQ_CANONICAL_BINDING"
    assert "wallet_bindings" in db.queries[0]
    assert len(db.queries) == 1


@pytest.mark.asyncio
async def test_wallet_resolver_has_no_users_legacy_fallback():
    db = _WalletResolverDb(binding_wallet=None)

    wallet = await NftCheckService.get_wallet_for_user(
        db, global_id=1234567002  # type: ignore[arg-type]
    )

    assert wallet is None
    assert len(db.queries) == 1
    assert "wallet_bindings" in db.queries[0]
    assert "FROM efhc_core.users" not in db.queries[0]


@pytest.mark.asyncio
async def test_v1_me_triggers_stale_refresh_for_tonconnect_user(
    monkeypatch,
):
    user = SimpleNamespace(
        global_id=1234567890,
        username="tonconnect_user",
        is_vip=False,
        vip_checked_at=datetime.now(UTC) - timedelta(seconds=1200),
    )
    fake_db = AsyncMock()
    fake_result = SimpleNamespace(
        scalar_one_or_none=lambda: user
    )
    fake_db.execute.return_value = fake_result
    check_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(me_routes, "check_user_vip_once", check_mock)
    owner = FinancialReadOwner(
        global_id=user.global_id,
        provider_tg_id=910004,
    )

    result = await me_routes.me(db=fake_db, owner=owner)

    check_mock.assert_awaited_once_with(
        fake_db,
        global_id=user.global_id,
        force_refresh=False,
    )
    fake_db.commit.assert_awaited_once()
    fake_db.refresh.assert_awaited_once_with(user)
    assert result["global_id"] == "1234567890"
    assert "tg_id" not in result


@pytest.mark.asyncio
async def test_batch_scheduler_includes_wallet_bindings_users():
    db = _WalletBatchDb(
        [
            SimpleNamespace(
                global_id=1234567005,
                wallet_address="EQ_BATCH_BINDING",
                wallet_source="wallet_bindings",
            )
        ]
    )

    candidates = await _fetch_wallet_candidates_batch(db, offset=0, limit=50)  # type: ignore[arg-type]

    assert [c.global_id for c in candidates] == [1234567005]
    assert candidates[0].wallet_address == "EQ_BATCH_BINDING"
    assert candidates[0].wallet_source == "wallet_bindings"


@pytest.mark.asyncio
async def test_batch_scheduler_has_no_duplicate_when_both_sources_exist():
    db = _WalletBatchDb(
        [
            SimpleNamespace(
                global_id=1234567006,
                wallet_address="EQ_CANONICAL_ONLY_ONCE",
                wallet_source="wallet_bindings",
            )
        ]
    )

    candidates = await _fetch_wallet_candidates_batch(db, offset=0, limit=50)  # type: ignore[arg-type]

    assert len(candidates) == 1
    assert candidates[0].global_id == 1234567006
    assert candidates[0].wallet_source == "wallet_bindings"

@pytest.mark.asyncio
async def test_v1_me_does_not_create_missing_user() -> None:
    fake_db = AsyncMock()
    fake_result = SimpleNamespace(
        scalar_one_or_none=lambda: None
    )
    fake_db.execute.return_value = fake_result
    owner = FinancialReadOwner(
        global_id=1234567890,
        provider_tg_id=910099,
    )

    with pytest.raises(Exception) as exc:
        await me_routes.me(db=fake_db, owner=owner)

    assert getattr(exc.value, "status_code", None) == 404
    assert getattr(exc.value, "detail", None) == "user_not_onboarded"
    fake_db.commit.assert_not_awaited()

