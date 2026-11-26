"""Lease-bound TEST guest topup HTTP contract. No Neon or real funds."""
from __future__ import annotations

import unittest
from datetime import UTC,datetime,timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch

from fastapi import FastAPI
from httpx import ASGITransport,AsyncClient

from demo_backend.config import DemoConfig
from demo_backend.guest_pool import _digest
from demo_backend.routes import DemoRoutes
from demo_backend.session_store import DemoSessionStore


class FakeResult:
    def scalar_one(self):
        return True


class FakeDb:
    def __init__(self):
        self.commits=0
        self.rollbacks=0
    async def execute(self,*args,**kwargs):
        return FakeResult()
    async def commit(self):
        self.commits+=1
    async def rollback(self):
        self.rollbacks+=1


def test_config() -> DemoConfig:
    return DemoConfig(
        database_url="postgresql://test:pass@localhost/neondb?sslmode=require",
        neon_host="localhost",password="test-operator-password-only",
        initial_global_id="0000001000",cors_origins=("https://example.test",),
        cookie_secure=False,cookie_name="efhc_demo_sid",
        scheduler_enabled=False,scheduler_period=60,max_topup_efhc="10000.00000000",
        dataset="genesis",
    )


class GuestTopupHttpTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db=FakeDb()
        self.store=DemoSessionStore()
        self.resume="z"*48
        self.guest=self.store.issue(
            "0000003001",scope="guest",lease_hash=_digest(self.resume)
        )
        self.operator=self.store.issue(
            "0000003002",scope="operator",lease_hash=_digest("x"*48)
        )
        async def db_dependency():
            yield self.db
        app=FastAPI()
        with patch.object(DemoRoutes,"_dependency",return_value=db_dependency):
            app.include_router(DemoRoutes(test_config(),self.store).router)
        self.app=app

    def _headers(self,session=None,csrf=True,idk=True):
        s=session or self.guest
        result={"Authorization":"Bearer "+s.token}
        if csrf:
            result["X-EFHC-Test-CSRF"]=s.csrf
        if idk:
            result["Idempotency-Key"]="test-topup-operation-00001"
        return result

    async def _post(self,amount,headers=None):
        async with AsyncClient(
            transport=ASGITransport(app=self.app),base_url="http://test"
        ) as client:
            return await client.post(
                "/api/staging/guest-topup",
                json={"amount_efhc":amount},
                headers=self._headers() if headers is None else headers,
            )

    async def test_no_csrf_rejected_without_any_bank_write(self):
        response=await self._post("50.00000000",self._headers(csrf=False))
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.db.commits,0)

    async def test_operator_password_never_grants_guest_topup(self):
        response=await self._post("50.00000000",
                                  self._headers(self.operator))
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.db.commits,0)

    async def test_missing_idempotency_key_rejected(self):
        response=await self._post("50.00000000",self._headers(idk=False))
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.db.commits,0)

    async def test_guest_topup_uses_exact_canonical_ledger_service(self):
        result=SimpleNamespace(
            user__main__balance=Decimal("950.00000000"),
            bank__main__balance=Decimal("1000000.00000000"),
            detail="success",
        )
        from app.services import transactions_service
        with patch.object(
            transactions_service,"credit_user_from_bank_nocommit",
            new_callable=AsyncMock,return_value=result,
        ) as service:
            response=await self._post("50.00000000")
        self.assertEqual(response.status_code,200,response.text)
        payload=response.json()
        self.assertEqual(payload["global_id"],"0000003001")
        self.assertEqual(payload["amount_efhc"],"50.00000000")
        self.assertIs(payload["real_funds"],False)
        self.assertEqual(payload["main_balance"],"950.00000000")
        self.assertEqual(self.db.commits,1)
        service.assert_awaited_once()
        kwargs=service.await_args.kwargs
        self.assertEqual(kwargs["global_id"],3001)
        self.assertEqual(kwargs["amount"],Decimal("50.00000000"))
        self.assertEqual(kwargs["reason"],"demo_simulated_external_deposit")
        self.assertEqual(kwargs["meta"]["real_funds"],False)
        self.assertEqual(kwargs["meta"]["test_only"],True)

    async def test_negative_or_oversized_topup_rejected(self):
        for amount in ("0","10000.00000001"):
            with self.subTest(amount=amount):
                response=await self._post(amount)
                self.assertEqual(response.status_code,422)
        self.assertEqual(self.db.commits,0)


if __name__=="__main__":
    unittest.main()
