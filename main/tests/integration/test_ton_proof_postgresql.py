"""Real PostgreSQL proof/replay/TTL tests цикла 1616."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from app.identity.auth_provider import AuthProvider
from app.identity.auth_runtime_services import (
    AuthChallengeService,
    IssuedAuthChallenge,
)
from app.identity.ton_login_challenge import (
    TON_LOGIN_CHALLENGE_TTL,
    TON_LOGIN_PURPOSE,
)
from app.identity.ton_proof_verification import (
    TON_MAINNET_CHAIN,
    TonProofVerificationError,
    TonProofVerificationService,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.support.ton_proof_vectors import (
    TON_PROOF_ADDRESS,
    TON_PROOF_DOMAIN,
    TON_PROOF_NOW,
    FakeTonWalletKeyResolver,
    TonProofVector,
    build_ton_proof_vector,
)

pytestmark = pytest.mark.asyncio


class MutableClock:
    """Управляемые UTC-часы для exact TTL boundary."""

    def __init__(self) -> None:
        self.now = TON_PROOF_NOW

    def __call__(self):
        return self.now


async def _issued_service(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    clock: MutableClock,
) -> tuple[
    AuthChallengeService,
    IssuedAuthChallenge,
    TonProofVector,
]:
    challenge_service = AuthChallengeService(
        session_factory,
        clock=clock,
    )
    issued = await challenge_service.issue(
        provider=AuthProvider.TON,
        purpose=TON_LOGIN_PURPOSE,
        domain=TON_PROOF_DOMAIN,
        ttl=TON_LOGIN_CHALLENGE_TTL,
    )
    vector = build_ton_proof_vector(
        timestamp=int(clock.now.timestamp()),
        payload=issued.token,
    )
    return challenge_service, issued, vector


async def test_concurrent_ton_proof_consumption_имеет_одного_winner(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = MutableClock()
    challenge_service, issued, vector = await _issued_service(
        integration_session_factory,
        clock=clock,
    )
    resolver = FakeTonWalletKeyResolver(public_key=vector.public_key)
    verifier = TonProofVerificationService(
        challenge_consumer=challenge_service,
        key_resolver=resolver,
        configured_network="mainnet",
        clock=clock,
    )

    async def verify_once():
        return await verifier.verify(
            challenge_id=issued.challenge_id,
            address=TON_PROOF_ADDRESS,
            network=TON_MAINNET_CHAIN,
            public_key=vector.public_key.hex(),
            proof=vector.proof,
            expected_domain=TON_PROOF_DOMAIN,
        )

    results = await asyncio.gather(
        *(verify_once() for _ in range(6)),
        return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in results) == 1
    rejected = [
        item
        for item in results
        if isinstance(item, TonProofVerificationError)
    ]
    assert len(rejected) == 5
    assert {item.reason for item in rejected} == {
        "CHALLENGE_NOT_CONSUMABLE"
    }


@pytest.mark.parametrize("case", ["expired", "wrong_id"])
async def test_storage_boundaries_отклоняют_валидную_подпись(
    integration_session_factory: async_sessionmaker[AsyncSession],
    case: str,
) -> None:
    clock = MutableClock()
    challenge_service, issued, _ = await _issued_service(
        integration_session_factory,
        clock=clock,
    )
    challenge_id = issued.challenge_id
    if case == "expired":
        clock.now += TON_LOGIN_CHALLENGE_TTL + timedelta(seconds=1)
    else:
        challenge_id = uuid4()
    vector = build_ton_proof_vector(
        timestamp=int(clock.now.timestamp()),
        payload=issued.token,
    )
    verifier = TonProofVerificationService(
        challenge_consumer=challenge_service,
        key_resolver=FakeTonWalletKeyResolver(
            public_key=vector.public_key
        ),
        configured_network="mainnet",
        clock=clock,
    )
    with pytest.raises(TonProofVerificationError) as captured:
        await verifier.verify(
            challenge_id=challenge_id,
            address=TON_PROOF_ADDRESS,
            network=TON_MAINNET_CHAIN,
            public_key=vector.public_key.hex(),
            proof=vector.proof,
            expected_domain=TON_PROOF_DOMAIN,
        )
    assert captured.value.reason == "CHALLENGE_NOT_CONSUMABLE"
