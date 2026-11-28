"""Synthetic store seam only; no database/network/wallet or real transaction."""
import asyncio
import copy
import unittest
from contextlib import asynccontextmanager

from app.services.shop_prepayment_external_row import (
    ExternalPromotionRefused, link_new_external_intent, promote_selected_external_order,
)


BASE = {"sku":"ITEM", "method":"TON", "quantity":1, "custom":None,
        "quote":{"item_type":"EFHC_PACKAGE", "expected_amount":"1.25", "quantity_efhc":None,
                 "external_amount_atomic":"1250000000", "external_decimals":9,
                 "to_address":"synthetic-receiver"}}
SNAP = {"sku":"ITEM", "item_type":"EFHC_PACKAGE", "payment_method":"TON", "request_quantity":1, "custom_efhc_amount_d8":None,
        "expected_amount":"1.25", "external_amount_atomic":"1250000000", "external_decimals":9,
        "canonical_memo":"synthetic-quote", "to_address":"synthetic-receiver"}
ARGS = dict(owner=1, order_id=101, key="synthetic-key", prepared=BASE, snapshot=SNAP)


class Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value


class Unit:
    def __init__(self):
        self.row={"owner":1,"order_id":101,"key":"synthetic-key","status":"SELECTED","linked":False}
        self.open=False
        self.calls=[]
        self.can_link=True

    def in_transaction(self): return self.open

    @asynccontextmanager
    async def begin(self):
        before = copy.deepcopy(self.row)
        self.open=True
        try:
            yield self
        except BaseException:
            self.row=before
            raise
        finally:
            self.open=False

    async def execute(self, query, args):
        self.calls.append((query,args))
        if not all(self.row[k] == args[k] for k in ("owner","order_id","key")):
            return Result(None)
        if "SET status='PENDING'" in query and self.row["status"]=="SELECTED":
            self.row["status"]="PENDING"
        elif (self.can_link and "efhc_core.payment_intents" in query and self.row["status"]=="PENDING"
              and not self.row["linked"] and args["intent_id"] == 9):
            self.row["linked"]=True
        else:
            return Result(None)
        return Result(self.row["order_id"])


async def promote(unit, **override):
    return await promote_selected_external_order(unit, str, quantity_efhc=None, **(ARGS | override))


async def link(unit, **override):
    params=ARGS | dict(intent_id=9, intent_memo="synthetic-intent", payer_wallet="synthetic-payer",
                       delivery_wallet=None, vip_number=None, quantity_efhc=None) | override
    return await link_new_external_intent(unit, str, **params)


class ExternalRowTests(unittest.TestCase):
    def test_two_staged_updates_are_same_row_and_do_not_commit_or_insert(self):
        async def run():
            u=Unit()
            async with u.begin():
                self.assertEqual(await promote(u),101)
                self.assertEqual(await link(u),101)
                self.assertTrue(u.open)
            self.assertEqual(u.row, dict(owner=1,order_id=101,key="synthetic-key",status="PENDING",linked=True))
            self.assertEqual(len(u.calls),2)
            for query,args in u.calls:
                self.assertIn("WHERE id=:order_id AND global_id=:owner AND idempotency_key=:key",query)
                self.assertNotIn("INSERT",query)
                self.assertNotIn("COMMIT",query)
                self.assertEqual({k:args[k] for k in ("owner","order_id","key")},{k:ARGS[k] for k in ("owner","order_id","key")})
            self.assertIn("AND memo IS NULL AND tx_hash IS NULL",u.calls[0][0])
            self.assertIn("i.asset=:method AND i.to_address=:receiver AND i.payload=:memo",u.calls[1][0])
        asyncio.run(run())

    def test_missing_quote_changed_amount_or_no_transaction_no_statement(self):
        async def run():
            u=Unit()
            with self.assertRaisesRegex(ExternalPromotionRefused,"TRANSACTION_REQUIRED"):
                await promote(u)
            async with u.begin():
                for p,s in [
                    ({k:v for k,v in BASE.items() if k != "quote"},SNAP),
                    (BASE,SNAP | {"expected_amount":"1.26"}),
                    (BASE,SNAP | {"external_amount_atomic":"1250000001"}),
                    (BASE,SNAP | {"intent_id":9}),
                ]:
                    with self.assertRaisesRegex(ExternalPromotionRefused,"SNAPSHOT_MISMATCH"):
                        await promote(u,prepared=p,snapshot=s)
            self.assertEqual(u.calls,[])
        asyncio.run(run())

    def test_failed_link_rolls_back_promotion_and_double_promotion_refused(self):
        async def run():
            u=Unit()
            with self.assertRaisesRegex(ExternalPromotionRefused,"TRANSITION_REFUSED"):
                async with u.begin():
                    await promote(u)
                    await link(u,intent_id=19)
            self.assertEqual(u.row["status"],"SELECTED")
            async with u.begin():
                await promote(u)
                await link(u)
            with self.assertRaisesRegex(ExternalPromotionRefused,"TRANSITION_REFUSED"):
                async with u.begin():
                    await promote(u)
            self.assertTrue(u.row["linked"])
        asyncio.run(run())
