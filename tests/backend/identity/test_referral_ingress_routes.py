"""HTTP transport tests provider-neutral referral ingress цикла 1638."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from app.identity.telegram_auth_session import (
    TelegramAuthSessionService,
)
from app.identity.types import GlobalId
from app.routes.auth_telegram_routes import issue_telegram_auth_session
from app.routes.auth_ton_routes import verify_ton_login_proof
from app.schemas.auth_telegram_schemas import TelegramAuthSessionIn
from app.schemas.auth_ton_schemas import TonLoginProofIn
from fastapi import HTTPException, Response
from tests.support.ton_proof_vectors import (
    TON_PROOF_ADDRESS,
    TON_PROOF_CHALLENGE_ID,
    TON_PROOF_DOMAIN,
    TON_PROOF_NOW,
    build_ton_proof_vector,
)

NOW = datetime(2026, 8, 3, 0, 0, tzinfo=UTC)


def _ton_body(*, referral_start_param: str | None) -> TonLoginProofIn:
    vector = build_ton_proof_vector()
    return TonLoginProofIn.model_validate(
        {
            "challenge_id": str(TON_PROOF_CHALLENGE_ID),
            "ton_wallet_id": TON_PROOF_ADDRESS,
            "network": "-239",
            "public_key": vector.public_key.hex(),
            "referral_start_param": referral_start_param,
            "proof": {
                "timestamp": vector.proof.timestamp,
                "domain": {
                    "lengthBytes": vector.proof.domain_length_bytes,
                    "value": vector.proof.domain,
                },
                "signature": vector.proof.signature,
                "payload": vector.proof.payload,
                "state_init": vector.proof.state_init,
            },
        }
    )


@pytest.mark.asyncio
async def test_telegram_route_передаёт_нормализованный_referral() -> None:
    captured: dict[str, object] = {}

    class Adapter:
        def verify(self, _raw: object) -> object:
            return object()

    class Service:
        async def login(
            self,
            _verified: object,
            *,
            referral_start_param: str,
        ) -> object:
            captured["referral_start_param"] = referral_start_param
            return SimpleNamespace(
                account=SimpleNamespace(
                    global_id=GlobalId(42),
                    outcome="existing_identity",
                ),
                session=SimpleNamespace(
                    token="S" * 43,
                    expires_at=NOW,
                ),
            )

    result = await issue_telegram_auth_session(
        response=Response(),
        init_data="auth_date=1&hash=x&user=y",
        body=TelegramAuthSessionIn(
            referral_start_param=" ref_ABC123 "
        ),
        _enabled=None,
        adapter=cast(object, Adapter()),
        service=cast(TelegramAuthSessionService, Service()),
    )

    assert result.global_id == "0000000042"
    assert captured == {"referral_start_param": "ABC123"}


@pytest.mark.asyncio
async def test_telegram_route_отклоняет_invalid_referral_до_adapter() -> None:
    class Adapter:
        def verify(self, _raw: object) -> object:
            raise AssertionError("adapter не должен вызываться")

    with pytest.raises(HTTPException) as captured:
        await issue_telegram_auth_session(
            response=Response(),
            init_data="auth_date=1&hash=x&user=y",
            body=TelegramAuthSessionIn(referral_start_param="ref_***"),
            _enabled=None,
            adapter=cast(object, Adapter()),
            service=cast(TelegramAuthSessionService, object()),
        )

    assert captured.value.status_code == 400
    assert captured.value.detail["error"] == "auth.referral_start_invalid"


@pytest.mark.asyncio
async def test_ton_route_передаёт_нормализованный_referral() -> None:
    captured: dict[str, object] = {}

    class ProofService:
        async def verify(self, **_kwargs: object) -> object:
            return SimpleNamespace(
                challenge_id=TON_PROOF_CHALLENGE_ID,
                ton_wallet_id=TON_PROOF_ADDRESS,
                network="mainnet",
                verified_at=TON_PROOF_NOW,
            )

    class AuthService:
        async def login(
            self,
            _proof: object,
            *,
            referral_start_param: str,
        ) -> object:
            captured["referral_start_param"] = referral_start_param
            return SimpleNamespace(
                account=SimpleNamespace(
                    global_id=GlobalId(42),
                    outcome="existing_identity",
                ),
                session=SimpleNamespace(
                    token="S" * 43,
                    expires_at=TON_PROOF_NOW,
                ),
            )

    result = await verify_ton_login_proof(
        body=_ton_body(referral_start_param="ref_ABC123"),
        response=Response(),
        domain=TON_PROOF_DOMAIN,
        _enabled=None,
        service=ProofService(),  # type: ignore[arg-type]
        auth_service=AuthService(),  # type: ignore[arg-type]
    )

    assert result.global_id == "0000000042"
    assert captured == {"referral_start_param": "ABC123"}


@pytest.mark.asyncio
async def test_ton_route_отклоняет_invalid_referral_до_proof() -> None:
    class ProofService:
        async def verify(self, **_kwargs: object) -> object:
            raise AssertionError("proof verifier не должен вызываться")

    with pytest.raises(HTTPException) as captured:
        await verify_ton_login_proof(
            body=_ton_body(referral_start_param="ref_***"),
            response=Response(),
            domain=TON_PROOF_DOMAIN,
            _enabled=None,
            service=ProofService(),  # type: ignore[arg-type]
            auth_service=object(),  # type: ignore[arg-type]
        )

    assert captured.value.status_code == 400
    assert captured.value.detail["error"] == "auth.referral_start_invalid"
