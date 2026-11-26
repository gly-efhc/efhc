import asyncio
import copy
import unittest
from contextlib import asynccontextmanager

from main.backend.app.services.shop_prepayment import (
    Checkout,
    Outcome,
    References,
    ShopRequest,
    ShopRequestError,
)


class _Store:
    def __init__(self):
        self.rows = {}
        self.calls = 0
        self.legacy_active = set()
        self.lock = asyncio.Lock()
        self.issue_fails = False
        self.settled = set()

    @asynccontextmanager
    async def owner_unit(self, owner, *, issuing=None):
        async with self.lock:
            self.owner = owner
            before = copy.deepcopy(self.rows)
            try:
                yield self
            except BaseException:
                self.rows = before
                raise

    async def find(self, key):
        row = self.rows.get((self.owner, key))
        if row is not None and row.outcome is Outcome.ISSUED and (self.owner, key) in self.settled:
            return type(row)(row.request, Outcome.PAID, row.references)
        return row

    async def lane_busy(self, *, except_key=None):
        return self.owner in self.legacy_active or any(
            owner == self.owner and key != except_key and (
                row.outcome is Outcome.PREPARED
                or (row.outcome is Outcome.ISSUED and (owner, key) not in self.settled)
            )
            for (owner, key), row in self.rows.items()
        )

    async def save(self, attempt):
        self.rows[(self.owner, attempt.request.key)] = attempt

    async def issue(self, request):
        self.calls += 1
        if self.issue_fails:
            raise RuntimeError("synthetic issue failure")
        return References(order_id="20", intent_id="11" if request.method != "EFHC" else None)


class Prepayment(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = _Store()
        self.shop = Checkout(self.store)
        self.a = ShopRequest("first", "sku", "TON", 1)
        self.b = ShopRequest("second", "sku", "EFHC", 1)

    async def test_only_pay_issues_and_only_prepared_can_cancel(self):
        prepared = await self.shop.prepare("one", self.a)
        self.assertIs(prepared.outcome, Outcome.PREPARED)
        self.assertIsNone(prepared.references)
        self.assertEqual(self.store.calls, 0)
        with self.assertRaisesRegex(ShopRequestError, "SHOP_REQUEST_ACTIVE"):
            await self.shop.prepare("one", self.b)
        self.assertIs((await self.shop.cancel("one", self.a)).outcome, Outcome.CANCELED)
        await self.shop.prepare("one", self.b)
        paid = await self.shop.pay("one", self.b)
        self.assertIs(paid.outcome, Outcome.PAID)
        self.assertEqual(await self.shop.pay("one", self.b), paid)
        with self.assertRaisesRegex(ShopRequestError, "SHOP_REQUEST_ALREADY_ISSUED"):
            await self.shop.cancel("one", self.b)
        self.assertEqual(self.store.calls, 1)
        upcoming = ShopRequest("new", "sku", "USDT", 1)
        self.assertIs((await self.shop.prepare("one", upcoming)).outcome, Outcome.PREPARED)
        self.assertEqual((await self.shop.prepare("other", self.a)).outcome, Outcome.PREPARED)

    async def test_unknown_prepare_tombstone_and_conflicting_payload(self):
        self.assertIs((await self.shop.cancel("one", self.a)).outcome, Outcome.CANCELED)
        self.assertIs((await self.shop.prepare("one", self.a)).outcome, Outcome.CANCELED)
        with self.assertRaisesRegex(ShopRequestError, "SHOP_REQUEST_NOT_PREPARED"):
            await self.shop.pay("one", self.a)
        different = ShopRequest("first", "different", "TON", 1)
        with self.assertRaisesRegex(ShopRequestError, "SHOP_REQUEST_PAYLOAD_MISMATCH"):
            await self.shop.prepare("one", different)
        self.assertEqual(self.store.calls, 0)

    async def test_legacy_active_other_method_and_failed_issue_rollback(self):
        self.store.legacy_active.add("one")
        with self.assertRaisesRegex(ShopRequestError, "SHOP_REQUEST_ACTIVE"):
            await self.shop.prepare("one", self.b)
        self.store.legacy_active.clear()
        await self.shop.prepare("one", self.a)
        self.store.issue_fails = True
        with self.assertRaises(RuntimeError):
            await self.shop.pay("one", self.a)
        self.assertIs((await self.shop.status("one", self.a)).outcome, Outcome.PREPARED)
        self.assertIs((await self.shop.cancel("one", self.a)).outcome, Outcome.CANCELED)

    async def test_pay_rechecks_legacy_lane_under_existing_lock(self):
        await self.shop.prepare("one", self.a)
        self.store.legacy_active.add("one")
        with self.assertRaisesRegex(ShopRequestError, "SHOP_REQUEST_ACTIVE"):
            await self.shop.pay("one", self.a)
        self.assertIs((await self.shop.status("one", self.a)).outcome, Outcome.PREPARED)
        self.assertEqual(self.store.calls, 0)

    async def test_external_issued_is_not_paid_and_only_settlement_releases(self):
        await self.shop.prepare("one", self.a)
        issued = await self.shop.pay("one", self.a)
        self.assertIs(issued.outcome, Outcome.ISSUED)
        self.assertEqual(await self.shop.status("one", self.a), issued)
        self.assertIsNone(await self.shop.status("one", self.b))
        with self.assertRaisesRegex(ShopRequestError, "SHOP_REQUEST_ACTIVE"):
            await self.shop.prepare("one", self.b)
        with self.assertRaisesRegex(ShopRequestError, "SHOP_REQUEST_ALREADY_ISSUED"):
            await self.shop.cancel("one", self.a)

        self.store.settled.add(("one", self.a.key))
        paid = await self.shop.status("one", self.a)
        self.assertIs(paid.outcome, Outcome.PAID)
        self.assertEqual(paid.references, issued.references)
        with self.assertRaisesRegex(ShopRequestError, "SHOP_REQUEST_ALREADY_ISSUED"):
            await self.shop.cancel("one", self.a)
        self.assertIs((await self.shop.prepare("one", self.b)).outcome, Outcome.PREPARED)
        self.assertEqual(self.store.calls, 1)

    async def test_pay_cancel_only_one_wins(self):
        await self.shop.prepare("one", self.a)
        results = await asyncio.gather(
            self.shop.cancel("one", self.a),
            self.shop.pay("one", self.a),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(x, ShopRequestError) for x in results), 1)
        canceled = not isinstance(results[0], ShopRequestError)
        self.assertEqual(self.store.calls, 0 if canceled else 1)
        stored = await self.shop.status("one", self.a)
        self.assertIs(stored.outcome, Outcome.CANCELED if canceled else Outcome.ISSUED)
