from contextlib import asynccontextmanager
from functools import partial
from types import SimpleNamespace
from unittest import TestCase

from fastapi import FastAPI
from fastapi.testclient import TestClient

from main.backend.app.routes import shop_prepayment_routes as api
from main.backend.app.services.shop_prepayment_external_pay import pay_external
from main.backend.app.services.shop_prepayment import Checkout, ShopRequest, freeze_review
from main.backend.app.services.shop_prepayment_store import PostgresCheckoutStore


class ExternalPayContract(TestCase):
    def setUp(self):
        self.events = []
        self.row = {"id": 40, "status": "SELECTED", "selection_fresh": True, "extra": {
            "shop_prepayment": {"sku": "sku", "method": "TON", "quantity": 1, "custom": None,
                "quote": {"expected_amount": "3.25", "to_address": "not public"}},
        }}
        self.commit_fails = False
        self.issue_fails = False
        store = PostgresCheckoutStore(self.session, self.owner_lock, lambda q: q)
        app = FastAPI()
        app.include_router(api.router, prefix="/api")
        self.owner = "0000000042"
        app.dependency_overrides[api.get_trusted_owner] = lambda: self.owner
        app.dependency_overrides[api.get_checkout] = lambda: Checkout(store)
        app.dependency_overrides[api.get_external_pay] = lambda: partial(
            pay_external, store=store, ops=self,
        )
        self.client = TestClient(app, raise_server_exceptions=False)
        self.body = {"sku": "sku", "key": "one", "quantity": 1, "method": "TON"}
        self.body["review_id"] = freeze_review(
            42, ShopRequest("one", "sku", "TON", 1),
            self.row["extra"]["shop_prepayment"],
        ).review_id

    @asynccontextmanager
    async def session(self):
        yield self

    @asynccontextmanager
    async def begin(self):
        previous = self.row.copy()
        self.events.append("begin")
        try:
            yield
            if self.commit_fails:
                raise RuntimeError("synthetic commit failure")
            self.events.append("commit")
        except BaseException:
            self.row = previous
            self.events.append("rollback")
            raise

    async def execute(self, query, params):
        self.assertEqual(params["owner"], int(self.owner))
        if "SELECT so.status" in query:
            visible = self.row if params["owner"] == 42 and params["key"] == "one" else None
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: visible))
        return SimpleNamespace(scalar_one=lambda: False)

    async def owner_lock(self, db, *, global_id):
        self.events.append("owner")
        return SimpleNamespace(global_id=global_id)

    async def lock_item(self, db, owner, request):
        self.events.append("item")
        return object()

    async def issue(self, db, sql, item, owner, oid, request, prepared):
        self.events.append("issue")
        self.row.update(status="PENDING", linked_intent_id=43)
        if self.issue_fails:
            raise RuntimeError("synthetic failure after promotion")
        return {"state": "issued", "order_id": "40", "intent_id": "43", "payment": {"memo": "fixture-only"}}

    def pay(self, **overrides):
        return self.client.post("/api/shopfront/checkout-requests/pay", json=self.body | overrides)

    def test_fresh_releases_only_after_commit_replay_never_signs(self):
        response = self.pay()
        self.assertEqual(response.status_code, 200)
        self.assertIn("payment", response.json())
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.events, ["begin", "item", "owner", "issue", "commit"])
        replay = self.pay()
        self.assertEqual(replay.json(), {"state": "issued", "order_id": "40", "intent_id": "43"})
        self.assertEqual(self.events.count("issue"), 1)
        self.assertEqual(self.events.count("item"), 1)

    def test_issue_or_commit_failure_rolls_back_and_exposes_no_signing_material(self):
        for prop in ("issue_fails", "commit_fails"):
            setattr(self, prop, True)
            response = self.pay()
            self.assertEqual(response.status_code, 500)
            self.assertNotIn("fixture-only", response.text)
            self.assertEqual(self.row["status"], "SELECTED")
            self.assertEqual(self.events[-1], "rollback")
            setattr(self, prop, False)

    def test_payload_conflict_and_unsupported_balance_never_issue(self):
        self.assertEqual(self.pay(sku="other").json()["detail"], "SHOP_REQUEST_PAYLOAD_MISMATCH")
        self.assertEqual(self.pay(method="EFHC").json()["detail"], "SHOP_REQUEST_METHOD_UNAVAILABLE")
        self.assertNotIn("issue", self.events)

    def test_review_changed_or_missing_cannot_issue_at_actual_api(self):
        self.assertEqual(self.pay(review_id="a" * 64).json()["detail"], "SHOP_REQUEST_REVIEW_MISMATCH")
        self.row["extra"]["shop_prepayment"]["quote"]["expected_amount"] = "3.26"
        self.assertEqual(self.pay().json()["detail"], "SHOP_REQUEST_REVIEW_MISMATCH")
        del self.body["review_id"]
        self.assertEqual(self.pay().status_code, 422)
        self.assertNotIn("issue", self.events)

    def test_actual_status_projects_exact_unsigned_review_only_for_owner(self):
        path = "/api/shopfront/checkout-requests/status"
        response = self.client.post(path, json={"key": "one"})
        self.assertEqual(response.json(), {
            "state": "prepared", "quote": {"asset": "TON", "amount": "3.25"},
            "review_id": self.body["review_id"],
        })
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.owner = "0000000043"
        hidden = self.client.post(path, json={"key": "one"})
        self.assertEqual(hidden.json(), {"state": "not_seen"})
        self.assertNotIn("issue", self.events)
