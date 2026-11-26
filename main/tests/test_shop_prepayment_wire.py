import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Annotated

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from main.backend.app.routes import shop_prepayment_routes as api
from main.backend.app.services.shop_prepayment import Checkout, ShopRequest, ShopRequestError
from main.backend.app.services.shop_prepayment_store import PostgresCheckoutStore
from test_shop_prepayment_component import _Store


class HttpContract(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(api.router, prefix="/api")
        self.client = TestClient(self.app)
        self.base = "/api/shopfront/checkout-requests/"
        self.store = _Store()
        self.body = {"key": "fixture-one", "sku": "sku", "method": "TON", "quantity": 1}

    def endpoint(self, name, body, handoff=None):
        h = {"X-EFHC-Handoff": handoff} if handoff else {}
        return self.client.post(self.base + name, json=body, headers=h)

    def enable_fixture_only(self):
        async def owner(handoff: Annotated[str | None, Header(alias="X-EFHC-Handoff")] = None):
            if handoff in {"owner-a", "owner-b"}:
                return handoff
            return await api.get_trusted_owner(None)

        self.app.dependency_overrides[api.get_checkout] = lambda: Checkout(self.store)
        self.app.dependency_overrides[api.get_trusted_owner] = owner

    def test_default_has_no_enabled_service_or_pay(self):
        disabled = self.endpoint("prepare", self.body)
        self.assertEqual(disabled.status_code, 503)
        self.assertEqual(disabled.headers["Cache-Control"], "no-store")
        self.assertEqual(disabled.json(), {"detail": "SHOP_PREPAYMENT_UNAVAILABLE"})
        self.assertEqual(self.endpoint("pay", dict(self.body, review_id="a" * 64), "owner-a").status_code, 503)

    def test_auth_owner_status_minimization_cancel_and_invalid_data(self):
        self.enable_fixture_only()
        denied = self.endpoint("status", {"key": "fixture-one"})
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(denied.headers["Cache-Control"], "no-store")
        self.assertEqual(self.store.rows, {})

        invalid = self.endpoint("prepare", dict(self.body, global_id="owner-b"), "owner-a")
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json(), {"detail": "SHOP_REQUEST_INVALID"})
        self.assertEqual(invalid.headers["Cache-Control"], "no-store")

        prepared = self.endpoint("prepare", self.body, "owner-a")
        self.assertEqual(prepared.status_code, 200)
        self.assertEqual(prepared.json(), {"state": "prepared"})
        for owner, status in [("owner-a", "prepared"), ("owner-b", "not_seen")]:
            view = self.endpoint("status", {"key": "fixture-one"}, owner)
            self.assertEqual(view.json(), {"state": status})
            self.assertEqual(view.headers["Cache-Control"], "no-store")
        canceled = self.endpoint("cancel", self.body, "owner-a")
        self.assertEqual(canceled.json(), {"state": "canceled"})
        self.assertEqual(canceled.headers["Cache-Control"], "no-store")
        self.assertEqual(self.store.calls, 0)


class AdapterContract(unittest.IsolatedAsyncioTestCase):
    async def test_owner_lock_scope_and_no_sql_without_enabled_issuer(self):
        seen = []

        class Connection:
            @asynccontextmanager
            async def begin(self):
                seen.append("begin")
                yield
                seen.append("commit")

            async def execute(self, statement, params):
                self_check.assertNotIn("CREATE TABLE", statement)
                self_check.assertEqual(params, {"owner": 42, "key": "opaque"})
                self_check.assertIn("global_id=:owner", statement)
                seen.append("owner-status")
                return SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: None))

        self_check = self

        @asynccontextmanager
        async def session():
            seen.append("open")
            yield Connection()

        async def owner_lock(_db, *, global_id):
            seen.append(("lock", global_id))
            return SimpleNamespace(global_id=global_id)

        checkout = Checkout(PostgresCheckoutStore(session, owner_lock, lambda s: s))
        self.assertIsNone(await checkout.status_by_key("0000000042", "opaque"))
        self.assertEqual(seen, ["open", "begin", ("lock", 42), "owner-status", "commit"])
        with self.assertRaisesRegex(ShopRequestError, "SHOP_REQUEST_ISSUE_DISABLED"):
            await checkout.pay("0000000042", ShopRequest("opaque", "sku", "TON", 1))
        self.assertEqual(seen, ["open", "begin", ("lock", 42), "owner-status", "commit"])

    async def test_same_row_quote_is_frozen_and_cancel_never_issues(self):
        import json
        from main.backend.app.services.shop_prepayment_store import _Unit

        row = {}
        seen = []
        quote = {"item_type": "EFHC_PACKAGE", "expected_amount": "2.00",
                 "quantity_efhc": "10.00000000", "external_amount_atomic": "2000000000",
                 "external_decimals": 9, "to_address": "synthetic-receiver"}

        class Connection:
            async def execute(self, statement, params):
                if "INSERT" in statement:
                    if row:
                        raise AssertionError("duplicate row")
                    assert all(x not in statement for x in ("memo", "tx_hash", "payment_intents"))
                    row.update(status=params["state"], id=19, selection_fresh=True,
                               extra=json.loads(params["extra"]))
                    seen.append("insert")
                    return SimpleNamespace(scalar_one_or_none=lambda: 19)
                if "UPDATE" in statement:
                    assert params == {"owner": 42, "key": "opaque"}
                    assert row["status"] == "SELECTED"
                    row["status"] = "SELECTION_CANCELED"
                    seen.append("cancel")
                    return SimpleNamespace(scalar_one_or_none=lambda: 19)
                return SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: row or None))

        async def quote_item(_db, _request):
            return "EFHC", quote

        from main.backend.app.services.shop_prepayment import Attempt, Outcome
        request = ShopRequest("opaque", "sku", "TON", 1)
        unit = _Unit(Connection(), 42, lambda s: s, quote_item)
        await unit.save(Attempt(request, Outcome.PREPARED))
        quote["expected_amount"] = "99.00"
        status = await unit.find("opaque")
        assert status.references is None
        self.assertEqual(api._view(status), {
            "state": "prepared",
            "quote": {"asset": "TON", "amount": "2.00"},
            "review_id": status.review.review_id,
        })
        self.assertRegex(status.review.review_id, r"^[a-f0-9]{64}$")
        self.assertNotIn("synthetic-receiver", str(api._view(status)))
        assert row["extra"]["shop_prepayment"]["quote"]["expected_amount"] == "2.00"
        await unit.save(Attempt(request, Outcome.CANCELED))
        assert api._view(await unit.find("opaque")) == {"state": "canceled"}
        assert row["id"] == 19 and seen == ["insert", "cancel"]
