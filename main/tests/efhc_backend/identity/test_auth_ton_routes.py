"""Узкие HTTP contract tests TON login циклов 1615–1617."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.identity.ton_account_registration import (
    TonAccountRegistrationError,
)
from app.identity.ton_proof_verification import (
    TonProofVerificationError,
)
from app.identity.types import GlobalId
from app.routes.auth_ton_routes import verify_ton_login_proof
from app.schemas.auth_ton_schemas import TonLoginProofIn
from fastapi import HTTPException, Response
from tests.support.ton_proof_vectors import (
    TON_PROOF_ADDRESS,
    TON_PROOF_CHALLENGE_ID,
    TON_PROOF_DOMAIN,
    TON_PROOF_NOW,
    build_ton_proof_vector,
)


def _request_body() -> TonLoginProofIn:
    vector = build_ton_proof_vector()
    return TonLoginProofIn.model_validate(
        {
            "challenge_id": str(TON_PROOF_CHALLENGE_ID),
            "ton_wallet_id": TON_PROOF_ADDRESS,
            "network": "-239",
            "public_key": vector.public_key.hex(),
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
async def test_ton_proof_endpoint_выдаёт_account_и_session() -> None:
    class AcceptingService:
        async def verify(self, **_kwargs: object) -> object:
            return SimpleNamespace(
                challenge_id=TON_PROOF_CHALLENGE_ID,
                ton_wallet_id=TON_PROOF_ADDRESS,
                network="mainnet",
                verified_at=TON_PROOF_NOW,
            )

    class AcceptingAuthService:
        async def login(self, _proof: object) -> object:
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

    response = Response()
    result = await verify_ton_login_proof(
        body=_request_body(),
        response=response,
        domain=TON_PROOF_DOMAIN,
        _enabled=None,
        service=AcceptingService(),  # type: ignore[arg-type]
        auth_service=AcceptingAuthService(),  # type: ignore[arg-type]
    )
    payload = result.model_dump()
    assert payload["verified"] is True
    assert payload["ton_wallet_id"] == TON_PROOF_ADDRESS
    assert payload["global_id"] == "0000000042"
    assert payload["account_outcome"] == "existing_identity"
    assert payload["session"]["access_token"] == "S" * 43
    assert payload["session"]["token_type"] == "Bearer"
    assert "tg_id" not in payload
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_ton_proof_endpoint_возвращает_canonical_error_envelope() -> None:
    class RejectingService:
        async def verify(self, **_kwargs: object) -> object:
            raise TonProofVerificationError("SIGNATURE_INVALID")

    with pytest.raises(HTTPException) as captured:
        await verify_ton_login_proof(
            body=_request_body(),
            response=Response(),
            domain=TON_PROOF_DOMAIN,
            _enabled=None,
            service=RejectingService(),  # type: ignore[arg-type]
            auth_service=object(),  # type: ignore[arg-type]
        )
    assert captured.value.status_code == 400
    assert captured.value.detail == {
        "error": "auth.ton_proof_invalid",
        "message": "TON Proof недействителен",
        "details": {"reason": "SIGNATURE_INVALID"},
    }


@pytest.mark.asyncio
async def test_ton_proof_endpoint_конфликт_account_завершается_закрыто() -> None:
    class AcceptingService:
        async def verify(self, **_kwargs: object) -> object:
            return SimpleNamespace(
                challenge_id=TON_PROOF_CHALLENGE_ID,
                ton_wallet_id=TON_PROOF_ADDRESS,
                network="mainnet",
                verified_at=TON_PROOF_NOW,
            )

    class RejectingAuthService:
        async def login(self, _proof: object) -> object:
            raise TonAccountRegistrationError(
                "WALLET_IDENTITY_CONFLICT"
            )

    with pytest.raises(HTTPException) as captured:
        await verify_ton_login_proof(
            body=_request_body(),
            response=Response(),
            domain=TON_PROOF_DOMAIN,
            _enabled=None,
            service=AcceptingService(),  # type: ignore[arg-type]
            auth_service=RejectingAuthService(),  # type: ignore[arg-type]
        )
    assert captured.value.status_code == 409
    assert captured.value.detail == {
        "error": "auth.ton_account_conflict",
        "message": "TON account не может быть разрешён",
        "details": {"reason": "WALLET_IDENTITY_CONFLICT"},
    }
