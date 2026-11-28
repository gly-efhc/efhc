"""Общие cryptographic vectors TON Proof для циклов 1616+."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.identity.auth_errors import AuthChallengeNotConsumable
from app.identity.auth_provider import AuthProvider
from app.identity.auth_runtime_services import ConsumedAuthChallenge
from app.identity.ton_proof_verification import (
    TonProofData,
    TonWalletKeyMaterial,
    build_ton_proof_message,
)
from app.lib.ton_address import parse_ton_address
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

TON_PROOF_NOW = datetime(2026, 7, 30, 20, 0, tzinfo=UTC)
TON_PROOF_DOMAIN = "app.efhc.example"
TON_PROOF_ADDRESS = "0:" + ("11" * 32)
TON_PROOF_CHALLENGE_ID = UUID(
    "11111111-1111-1111-1111-111111111111"
)
TON_PROOF_PAYLOAD = "A" * 43
TON_PROOF_STATE_INIT = base64.b64encode(
    bytes.fromhex("b5ee9c72") + (b"\x00" * 16)
).decode("ascii")


@dataclass(frozen=True, slots=True)
class TonProofVector:
    """Полный подписанный vector без storage side effects."""

    private_key: Ed25519PrivateKey
    public_key: bytes
    proof: TonProofData


class FakeChallengeConsumer:
    """Детерминированный one-time consumer для unit tests."""

    def __init__(self, *, consumable: bool = True) -> None:
        self.consumable = consumable
        self.calls: list[dict[str, object]] = []

    async def consume(
        self,
        token: object,
        *,
        provider: AuthProvider,
        purpose: str,
        domain: str,
        provider_tenant: str = "default",
        expected_challenge_id: UUID | None = None,
    ) -> ConsumedAuthChallenge:
        self.calls.append(
            {
                "token": token,
                "provider": provider,
                "purpose": purpose,
                "domain": domain,
                "provider_tenant": provider_tenant,
                "expected_challenge_id": expected_challenge_id,
            }
        )
        if not self.consumable:
            raise AuthChallengeNotConsumable()
        self.consumable = False
        assert expected_challenge_id is not None
        return ConsumedAuthChallenge(
            challenge_id=expected_challenge_id,
            provider=provider,
            purpose=purpose,
            domain=domain,
        )


class FakeTonWalletKeyResolver:
    """Authoritative key resolver с управляемым результатом."""

    def __init__(
        self,
        *,
        public_key: bytes,
        address: str = TON_PROOF_ADDRESS,
        network: str = "mainnet",
    ) -> None:
        self.public_key = public_key
        self.address = address
        self.network = network
        self.calls: list[dict[str, str]] = []

    async def resolve(
        self,
        *,
        state_init: str,
        address: str,
        network: str,
    ) -> TonWalletKeyMaterial:
        self.calls.append(
            {
                "state_init": state_init,
                "address": address,
                "network": network,
            }
        )
        return TonWalletKeyMaterial(
            address=self.address,
            public_key=self.public_key,
            network=self.network,
            source="unit_state_init",
        )


def build_ton_proof_vector(
    *,
    timestamp: int | None = None,
    payload: str = TON_PROOF_PAYLOAD,
    domain: str = TON_PROOF_DOMAIN,
    state_init: str = TON_PROOF_STATE_INIT,
) -> TonProofVector:
    """Создать подписанный Ed25519 vector с общим message builder."""

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    proof_timestamp = timestamp or int(TON_PROOF_NOW.timestamp())
    message = build_ton_proof_message(
        address=parse_ton_address(TON_PROOF_ADDRESS),
        domain=domain,
        timestamp=proof_timestamp,
        payload=payload,
    )
    signature = base64.b64encode(private_key.sign(message)).decode(
        "ascii"
    )
    return TonProofVector(
        private_key=private_key,
        public_key=public_key,
        proof=TonProofData(
            timestamp=proof_timestamp,
            domain_length_bytes=len(domain.encode("utf-8")),
            domain=domain,
            signature=signature,
            payload=payload,
            state_init=state_init,
        ),
    )


__all__ = [
    "FakeChallengeConsumer",
    "FakeTonWalletKeyResolver",
    "TON_PROOF_ADDRESS",
    "TON_PROOF_CHALLENGE_ID",
    "TON_PROOF_DOMAIN",
    "TON_PROOF_NOW",
    "TON_PROOF_PAYLOAD",
    "TON_PROOF_STATE_INIT",
    "TonProofVector",
    "build_ton_proof_vector",
]
