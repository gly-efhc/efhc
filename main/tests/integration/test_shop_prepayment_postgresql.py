"""Dormant I10 Shop entry points against the repository's disposable PostgreSQL fixtures.

Run on the reviewed I10 candidate over e932, with PYTHONPATH=main/backend:
    python -m pytest -q main/tests/integration/test_shop_prepayment_postgresql.py

Use only a dedicated disposable PostgreSQL instance: db_clean resets project tables.
No network, wallet signing, or actual settlement. Wallet identity alone is stubbed.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
_guard_path = Path(__file__).resolve().parents[3] / "site/ci/run_shop_native.py"
_guard_spec = importlib.util.spec_from_file_location("shop_database_guard", _guard_path)
_guard = importlib.util.module_from_spec(_guard_spec)
_guard_spec.loader.exec_module(_guard)
_guard.check_database_environment(os.environ)

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.identity.financial_write_owner import resolve_and_lock_financial_write_owner
from app.services import shop_service, wallets_service
from app.services.shop_prepayment import Checkout, Outcome, ShopRequest, ShopRequestError
from app.services.shop_prepayment_external_pay import CanonicalExternalPay, pay_external
from app.services.shop_prepayment_store import PostgresCheckoutStore, _resolve_type
from sqlalchemy import text

pytestmark = pytest.mark.asyncio
PACKAGE = "EFHC_PACKAGE_10"
RECEIVER = "0:" + "11" * 32
PAYER = "0:" + "22" * 32


async def _prepare(factory, monkeypatch, key):
    # Same migrated tables and synthetic owner/catalog shape as draft PR #17.
    async with factory() as db:
        owner = (await db.execute(text(
            "INSERT INTO efhc_core.users (main_balance, bonus_balance) "
            "VALUES (100, 10) RETURNING global_id"
        ))).scalar_one()
        await db.execute(
            text(
                "INSERT INTO efhc_core.shop_items "
                "(sku, title, quantity_efhc, is_active, extra, created_at, updated_at) "
                "VALUES (:sku, :sku, 10, TRUE, CAST(:extra AS jsonb), NOW(), NOW())"
            ),
            {"sku": PACKAGE, "extra": (
                '{"item_type":"EFHC_PACKAGE","price_ton":"2.00",'
                '"price_usdt":"3.00","pay_currencies":["TON","USDT"]}'
            )},
        )
        await db.commit()

    wire = f"{int(owner):010d}"

    async def fixture_wallets(_db, *, global_id):
        assert global_id == wire
        return [SimpleNamespace(
            wallet_address=PAYER, is_primary=True, is_active=True, proof_verified=True,
        )]

    monkeypatch.setattr(wallets_service, "list_wallets", fixture_wallets)
    monkeypatch.setattr(shop_service.settings, "TON_MAIN_WALLET", RECEIVER)
    store = PostgresCheckoutStore(factory, resolve_and_lock_financial_write_owner, text, _resolve_type)
    request = ShopRequest(key, PACKAGE, "TON", 1)
    checkout = Checkout(store)
    prepared = await checkout.prepare(wire, request)
    assert prepared.outcome == Outcome.PREPARED
    review = prepared.review
    assert review is not None
    assert (review.asset, Decimal(review.amount)) == ("TON", Decimal("2"))
    assert (await checkout.status(wire, request)).review == review
    return int(owner), wire, request, checkout, store, review.review_id


async def _state(factory, owner):
    async with factory() as db:
        orders = (await db.execute(text(
            "SELECT id,status,expected_amount,quantity_efhc,memo,tx_hash,extra "
            "FROM efhc_core.shop_orders WHERE global_id=:owner"
        ), {"owner": owner})).mappings().all()
        intents = (await db.execute(text(
            "SELECT id,status,purpose,asset,idempotency_key,to_address,payload,external_tx_hash "
            "FROM efhc_core.payment_intents WHERE global_id=:owner"
        ), {"owner": owner})).mappings().all()
        log_count = (await db.execute(text(
            "SELECT count(*) FROM efhc_core.efhc_transfers_log WHERE global_id=:owner"
        ), {"owner": owner})).scalar_one()
    return orders, intents, log_count


def _assert_issued(initial, orders, intents, log_count, issued, key):
    assert (len(orders), len(intents), log_count) == (1, 1, 0)
    order, intent = orders[0], intents[0]
    assert order["id"] == initial["id"] == int(issued["order_id"])
    assert order["extra"]["shop_prepayment"] == initial["extra"]["shop_prepayment"]
    assert order["status"] == intent["status"] == "PENDING"
    assert order["tx_hash"] is intent["external_tx_hash"] is None
    assert order["extra"]["intent_id"] == intent["id"] == int(issued["intent_id"])
    assert order["memo"] == intent["payload"] == issued["payment"]["memo"]
    assert (intent["purpose"], intent["asset"], intent["idempotency_key"], intent["to_address"]) == (
        "shop_external", "TON", key, RECEIVER,
    )
    payment = issued["payment"]
    assert payment["external_amount_atomic"] == "2000000000"
    assert payment["external_decimals"] == 9
    assert payment["pay_method"] == "TON" and payment["to_wallet"] == RECEIVER
    assert Decimal(payment["external_amount_display"]) == Decimal(payment["amount"]) == Decimal("2")
    assert str(payment["order_id"]) == issued["order_id"]
    assert str(payment["intent_id"]) == issued["intent_id"]
    messages = payment["tonconnect_tx"]["messages"]
    assert len(messages) == 1
    assert (messages[0]["address"], messages[0]["amount"]) == (RECEIVER, "2000000000")
    assert messages[0]["payload"] == payment["memo"]


async def test_cancel_racing_canonical_pay_changes_only_the_prepared_row(
    db_clean, integration_session_factory, monkeypatch,
):
    factory = integration_session_factory
    owner, wire, request, checkout, store, review_id = await _prepare(factory, monkeypatch, "cancel-pay")
    before, intents, log_count = await _state(factory, owner)
    assert (len(before), len(intents), log_count) == (1, 0, 0)
    assert before[0]["memo"] is None

    canceled, paid = await asyncio.wait_for(asyncio.gather(
        checkout.cancel(wire, request),
        pay_external(wire, request, review_id, store=store, ops=CanonicalExternalPay()),
        return_exceptions=True,
    ), timeout=15)
    orders, intents, log_count = await _state(factory, owner)
    if isinstance(canceled, ShopRequestError):
        assert str(canceled) == "SHOP_REQUEST_ALREADY_ISSUED"
        assert isinstance(paid, dict) and paid["state"] == "issued"
        _assert_issued(before[0], orders, intents, log_count, paid, request.key)
    else:
        assert canceled.outcome == Outcome.CANCELED
        assert isinstance(paid, ShopRequestError)
        assert str(paid) == "SHOP_REQUEST_NOT_PREPARED"
        assert (len(orders), len(intents), log_count) == (1, 0, 0)
        assert orders[0]["id"] == before[0]["id"]
        assert orders[0]["extra"] == before[0]["extra"]
        assert orders[0]["status"] == "SELECTION_CANCELED"
        assert orders[0]["memo"] is orders[0]["tx_hash"] is None


async def test_pay_rollback_and_parallel_replay_releases_payload_exactly_once(
    db_clean, integration_session_factory, monkeypatch,
):
    factory = integration_session_factory
    owner, wire, request, checkout, store, review_id = await _prepare(factory, monkeypatch, "one-pay")
    before = await _state(factory, owner)

    invalid_id = ("1" if review_id[0] == "0" else "0") + review_id[1:]
    with pytest.raises(ShopRequestError, match="^SHOP_REQUEST_REVIEW_MISMATCH$"):
        await pay_external(wire, request, invalid_id, store=store, ops=CanonicalExternalPay())
    assert await _state(factory, owner) == before

    class AbortAfterLink(CanonicalExternalPay):
        async def issue(self, *args, **kwargs):
            result = await super().issue(*args, **kwargs)
            assert result["payment"]["memo"]
            raise RuntimeError("fixture abort after canonical issue")

    with pytest.raises(RuntimeError, match="fixture abort after canonical issue"):
        await pay_external(wire, request, review_id, store=store, ops=AbortAfterLink())
    assert await _state(factory, owner) == before
    assert (await checkout.status(wire, request)).outcome == Outcome.PREPARED

    both = await asyncio.wait_for(asyncio.gather(*(
        pay_external(wire, request, review_id, store=store, ops=CanonicalExternalPay())
        for _ in range(2)
    )), timeout=15)
    issued, = [output for output in both if "payment" in output]
    assert both[1 - both.index(issued)] == {
        "state": "issued", "order_id": issued["order_id"], "intent_id": issued["intent_id"],
    }
    _assert_issued(before[0][0], *(await _state(factory, owner)), issued, request.key)
    with pytest.raises(ShopRequestError, match="^SHOP_REQUEST_ALREADY_ISSUED$"):
        await checkout.cancel(wire, request)
    issued_status = await checkout.status(wire, request)
    assert issued_status.outcome == Outcome.ISSUED
    assert issued_status.review is None
    committed = await _state(factory, owner)
    with pytest.raises(ShopRequestError, match="^SHOP_REQUEST_REVIEW_MISMATCH$"):
        await pay_external(wire, request, invalid_id, store=store, ops=CanonicalExternalPay())
    assert await _state(factory, owner) == committed
