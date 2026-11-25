from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.identity.ton_login_challenge import IssuedTonLoginChallenge
from app.routes import auth_ton_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeTonLoginChallengeService:
    async def issue(self, *, domain: object) -> IssuedTonLoginChallenge:
        assert domain == "app.example.org"
        return IssuedTonLoginChallenge(
            challenge_id=UUID("11111111-1111-1111-1111-111111111111"),
            payload="B" * 43,
            expires_at=datetime(
                2026,
                7,
                30,
                20,
                10,
                tzinfo=UTC,
            ),
            domain="app.example.org",
        )


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(auth_ton_routes.router)
    app.dependency_overrides[
        auth_ton_routes.require_ton_login_enabled
    ] = lambda: None
    app.dependency_overrides[
        auth_ton_routes.get_ton_login_domain
    ] = lambda: "app.example.org"
    app.dependency_overrides[
        auth_ton_routes.get_ton_login_challenge_service
    ] = FakeTonLoginChallengeService
    return TestClient(app)


def test_challenge_endpoint_provider_neutral_и_no_store() -> None:
    response = _build_client().post("/auth/ton/challenge")
    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "ton"
    assert body["purpose"] == "ton.login"
    assert body["domain"] == "app.example.org"
    assert body["payload"] == "B" * 43
    assert "tg_id" not in body
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
