from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.routes import exchange_routes, panels_routes

pytestmark = pytest.mark.asyncio


class _PanelResult:
    def __init__(self, row: tuple[object, ...]) -> None:
        self._row = row

    def first(self) -> tuple[object, ...]:
        return self._row


class _PanelDb:
    def __init__(self, row: tuple[object, ...]) -> None:
        self._row = row
        self.execute_calls = 0

    async def execute(self, statement: object) -> _PanelResult:
        _ = statement
        self.execute_calls += 1
        return _PanelResult(self._row)


async def test_panel_activation_preserves_transaction_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activated_at = datetime(2026, 7, 16, 10, tzinfo=UTC)
    expires_at = datetime(2027, 1, 12, 10, tzinfo=UTC)
    db = _PanelDb(
        (2, "PNL-00000002", activated_at, expires_at),
    )
    activate = AsyncMock(
        return_value=SimpleNamespace(created_panel_ids=[2]),
    )
    monkeypatch.setattr(panels_routes.svc, "activate_panel", activate)

    output = await panels_routes._activate_one_panel(
        idempotency_key="panel-proof-1556",
        db=db,  # type: ignore[arg-type]
        owner=SimpleNamespace(global_id=2001),
    )

    activate.assert_awaited_once_with(
        db,
        global_id=2001,
        qty=1,
        idempotency_key="panel-proof-1556",
    )
    assert db.execute_calls == 1
    assert output.panel.id == 2
    assert output.panel.public_id == "PNL-00000002"
    assert output.panel.activated_at == activated_at.isoformat()
    assert output.panel.expires_at == expires_at.isoformat()


async def test_exchange_convert_normalizes_and_scopes_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = AsyncMock(
        return_value=SimpleNamespace(
            ok=True,
            exchanged_kwh=Decimal("10.00000000"),
            credited_efhc=Decimal("10.00000000"),
            new_available_kwh=Decimal("90.00000000"),
            new__main__balance=Decimal("110.00000000"),
            log_id=501,
            detail="converted",
        ),
    )
    monkeypatch.setattr(
        exchange_routes,
        "svc_exchange_kwh_to_efhc",
        exchange,
    )

    async def _key(candidate_db, *, canonical_key, legacy_key=None):
        assert candidate_db is db
        assert canonical_key == "exchange:G0000002001:digest-1556"
        assert legacy_key == "exchange:1001:digest-1556"
        return SimpleNamespace(selected=legacy_key)

    monkeypatch.setattr(
        exchange_routes,
        "choose_idempotency_key_with_history",
        _key,
    )
    db = object()
    owner = SimpleNamespace(global_id=2001, provider_tg_id=1001)

    output = await exchange_routes.convert(
        body=exchange_routes.ExchangeConvertIn(amount_kwh="10"),
        db=db,  # type: ignore[arg-type]
        idk_digest="digest-1556",
        owner=owner,
    )

    exchange.assert_awaited_once_with(
        db,
        global_id=2001,
        amount_kwh=Decimal("10.00000000"),
        idempotency_key="exchange:1001:digest-1556",
    )
    assert output.exchanged_kwh == "10.00000000"
    assert output.credited_efhc == "10.00000000"
    assert output.new_available_kwh == "90.00000000"
    assert output.new__main__balance == "110.00000000"
    assert output.log_id == 501
