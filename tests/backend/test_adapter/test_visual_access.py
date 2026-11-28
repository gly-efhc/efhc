"""Temporary TEST layout pass; credentials never unlock privileged Admin APIs."""
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from demo_backend.config import DemoConfig
from demo_backend.routes import DemoRoutes
from demo_backend.session_store import DemoSessionStore
from demo_backend.guest_pool import GuestLease


SECRET = "efhc-test-" + "a" * 45


def config(*, expires: datetime | None = None) -> DemoConfig:
    return DemoConfig(
        database_url="postgresql://test:pass@localhost/neondb?sslmode=require",
        neon_host="localhost", password="non-privileged-operator-password",
        initial_global_id="0000001000", cors_origins=("https://example.test",),
        cookie_secure=False, cookie_name="efhc_demo_sid",
        scheduler_enabled=False, scheduler_period=60, max_topup_efhc="10000.00000000",
        public_global_id="0000001000", dataset="legacy",
        visual_access_key=SECRET,
        visual_access_until=expires or datetime.now(UTC) + timedelta(days=1),
    )


class TemporaryKeyTests(unittest.IsolatedAsyncioTestCase):
    async def _create_app(self, cfg: DemoConfig, *, safe: bool = True):
        from demo_backend import routes as module
        from demo_backend.routes import DemoRoutes

        class FakeDb:
            async def commit(self):
                return None

            async def rollback(self):
                return None

        async def fake_db():
            yield FakeDb()

        async def fake_safe(db, gid):
            return safe and str(gid) == "0000001000"

        app = FastAPI()
        with patch.object(DemoRoutes, "_dependency", return_value=fake_db):
            controller = DemoRoutes(cfg, DemoSessionStore())
        self._safe_patch = patch.object(module, "is_safe_synthetic_account", fake_safe)
        self._safe_patch.start()
        self.addCleanup(self._safe_patch.stop)
        app.include_router(controller.router)
        return app

    async def test_valid_key_is_only_unprivileged_visual_scope(self):
        app = await self._create_app(config())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/staging/visual-access", json={"key": SECRET}
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["scope"], "visual")
        self.assertEqual(payload["global_id"], "0000001000")
        self.assertNotIn("admin_id", payload)
        self.assertNotIn("role", payload)
        self.assertGreater(len(payload["demo_bearer_token"]), 32)

    async def test_wrong_key_denied_without_any_token(self):
        app = await self._create_app(config())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/staging/visual-access", json={"key": "a" * 60}
            )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("demo_bearer_token", response.text)

    async def test_expired_key_denied(self):
        app = await self._create_app(
            config(expires=datetime.now(UTC) - timedelta(hours=1))
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/staging/visual-access", json={"key": SECRET}
            )
        self.assertEqual(response.status_code, 401)

    async def test_admin_identity_cannot_be_selected_as_visual_owner(self):
        app = await self._create_app(config(), safe=False)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/staging/visual-access", json={"key": SECRET}
            )
        self.assertEqual(response.status_code, 503)

    async def test_server_session_is_short_lived_and_unprivileged(self):
        store = DemoSessionStore()
        s = store.issue("0000001000", scope="visual")
        self.assertLessEqual(s.expires_at - datetime.now(UTC).timestamp(), 3601)
        self.assertEqual(s.scope, "visual")
        self.assertNotEqual(s.global_id, "0000000088")
        self.assertEqual(store.get(s.token), s)

    async def test_key_not_exposed_by_config_representation(self):
        cfg = config()
        self.assertNotIn(SECRET, repr(cfg))
        self.assertTrue(cfg.visual_access_active)


    async def test_genesis_visual_key_uses_random_pool_identity(self):
        from demo_backend import routes as module
        cfg = replace(config(), dataset="genesis")
        app = await self._create_app(cfg)
        token = "r" * 48
        lease = GuestLease("0000003007", token, datetime.now(UTC) + timedelta(hours=48))
        with patch.object(module, "allocate_guest", new_callable=AsyncMock, return_value=lease) as pool:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/staging/visual-access",
                    json={"key": SECRET, "resume_token": token},
                )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["global_id"], "0000003007")
        self.assertEqual(data["scope"], "visual")
        self.assertNotEqual(data["global_id"], "0000001000")
        self.assertEqual(data["guest_resume_token"], token)
        pool.assert_awaited_once()

    async def test_genesis_operator_password_uses_random_pool_identity(self):
        from demo_backend import routes as module
        cfg = replace(config(), dataset="genesis")
        app = await self._create_app(cfg)
        token = "t" * 48
        lease = GuestLease("0000003771", token, datetime.now(UTC) + timedelta(hours=48))
        with patch.object(module, "allocate_guest", new_callable=AsyncMock, return_value=lease):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/staging/login",
                    json={"password": "non-privileged-operator-password", "resume_token": token},
                )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["global_id"], "0000003771")
        self.assertEqual(data["scope"], "operator")
        self.assertEqual(data["guest_resume_token"], token)
        self.assertNotIn("admin_id", data)
        self.assertNotIn("role", data)


if __name__ == "__main__":
    unittest.main()
