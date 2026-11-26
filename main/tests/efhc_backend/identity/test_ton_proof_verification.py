"""Причинные cryptographic tests TON Proof цикла 1616."""

from __future__ import annotations

import base64
from dataclasses import replace
from datetime import timedelta

import pytest
from app.identity import ton_proof_verification as proof_module
from app.identity.auth_provider import AuthProvider
from app.identity.ton_proof_verification import (
    TON_MAINNET_CHAIN,
    TonApiStateInitResolver,
    TonProofVerificationError,
    TonProofVerificationService,
    build_ton_proof_message,
    build_ton_proof_verification_contract,
)
from app.lib.ton_address import parse_ton_address
from app.schemas.auth_ton_schemas import TonLoginProofIn
from pydantic import ValidationError
from tests.support.ton_proof_vectors import (
    TON_PROOF_ADDRESS,
    TON_PROOF_CHALLENGE_ID,
    TON_PROOF_DOMAIN,
    TON_PROOF_NOW,
    TON_PROOF_PAYLOAD,
    TON_PROOF_STATE_INIT,
    FakeChallengeConsumer,
    FakeTonWalletKeyResolver,
    build_ton_proof_vector,
)


def test_ton_proof_message_совпадает_с_fixed_vector() -> None:
    digest = build_ton_proof_message(
        address=parse_ton_address(TON_PROOF_ADDRESS),
        domain=TON_PROOF_DOMAIN,
        timestamp=int(TON_PROOF_NOW.timestamp()),
        payload=TON_PROOF_PAYLOAD,
    )
    assert digest.hex() == (
        "1ccc9f1b7c05c12f45cf0c9652098f03"
        "b4202284d0c8d61f964b71223bfa417b"
    )


def _service(
    *,
    consumer: FakeChallengeConsumer,
    resolver: FakeTonWalletKeyResolver,
) -> TonProofVerificationService:
    return TonProofVerificationService(
        challenge_consumer=consumer,
        key_resolver=resolver,
        configured_network="mainnet",
        clock=lambda: TON_PROOF_NOW,
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://tonapi.io",
        "https://user:pass@tonapi.io",
        "https://tonapi.io?query=1",
    ],
)
def test_tonapi_resolver_отклоняет_небезопасную_конфигурацию(base_url: str) -> None:
    with pytest.raises(TonProofVerificationError) as captured:
        TonApiStateInitResolver(
            base_url=base_url,
            api_key="",
            configured_network="mainnet",
        )
    assert captured.value.reason == "TON_API_CONFIG_INVALID"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resolved_address", "reason"),
    [
        (TON_PROOF_ADDRESS, None),
        ("0:" + ("22" * 32), "STATE_INIT_ADDRESS_MISMATCH"),
    ],
)
async def test_tonapi_resolver_проверяет_authoritative_address(
    monkeypatch: pytest.MonkeyPatch,
    resolved_address: str,
    reason: str | None,
) -> None:
    vector = build_ton_proof_vector()
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {
                "address": resolved_address,
                "public_key": vector.public_key.hex(),
            }

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            json: dict[str, str],
            headers: dict[str, str],
        ) -> FakeResponse:
            captured.update(
                {"url": url, "json": json, "headers": headers}
            )
            return FakeResponse()

    monkeypatch.setattr(proof_module.httpx, "AsyncClient", FakeClient)
    resolver = TonApiStateInitResolver(
        base_url="https://tonapi.io",
        api_key="unit-key",
        configured_network="mainnet",
    )
    if reason is not None:
        with pytest.raises(TonProofVerificationError) as error:
            await resolver.resolve(
                state_init=TON_PROOF_STATE_INIT,
                address=TON_PROOF_ADDRESS,
                network="mainnet",
            )
        assert error.value.reason == reason
        return

    result = await resolver.resolve(
        state_init=TON_PROOF_STATE_INIT,
        address=TON_PROOF_ADDRESS,
        network="mainnet",
    )
    assert result.address == TON_PROOF_ADDRESS
    assert result.public_key == vector.public_key
    assert captured["url"] == (
        "https://tonapi.io/v2/tonconnect/stateinit"
    )
    assert captured["headers"] == {
        "Authorization": "Bearer unit-key"
    }
    assert repr(result).count("<redacted>") == 2


@pytest.mark.asyncio
async def test_valid_ton_proof_проверяет_crypto_и_consumes_exact_id() -> None:
    vector = build_ton_proof_vector()
    consumer = FakeChallengeConsumer()
    resolver = FakeTonWalletKeyResolver(public_key=vector.public_key)

    result = await _service(
        consumer=consumer,
        resolver=resolver,
    ).verify(
        challenge_id=TON_PROOF_CHALLENGE_ID,
        address=TON_PROOF_ADDRESS,
        network=TON_MAINNET_CHAIN,
        public_key=vector.public_key.hex(),
        proof=vector.proof,
        expected_domain=TON_PROOF_DOMAIN,
    )

    assert result.challenge_id == TON_PROOF_CHALLENGE_ID
    assert result.ton_wallet_id == TON_PROOF_ADDRESS
    assert result.verified_identity.provider is AuthProvider.TON
    assert result.network == "mainnet"
    assert consumer.calls[0]["token"] == TON_PROOF_PAYLOAD
    assert consumer.calls[0]["expected_challenge_id"] == (
        TON_PROOF_CHALLENGE_ID
    )
    assert TON_PROOF_PAYLOAD not in repr(result)


def _invalid_case(
    case: str,
) -> tuple[
    object,
    str,
    str,
    str,
    FakeTonWalletKeyResolver,
    str,
]:
    vector = build_ton_proof_vector()
    proof = vector.proof
    address = TON_PROOF_ADDRESS
    network = TON_MAINNET_CHAIN
    public_key = vector.public_key.hex()
    resolver = FakeTonWalletKeyResolver(public_key=vector.public_key)
    expected_domain = TON_PROOF_DOMAIN

    if case == "domain":
        proof = replace(proof, domain="evil.example")
    elif case == "domain_length":
        proof = replace(proof, domain_length_bytes=1)
    elif case == "expired":
        proof = replace(
            proof,
            timestamp=int(
                (
                    TON_PROOF_NOW - timedelta(minutes=16)
                ).timestamp()
            ),
        )
    elif case == "future":
        proof = replace(
            proof,
            timestamp=int(
                (
                    TON_PROOF_NOW + timedelta(seconds=61)
                ).timestamp()
            ),
        )
    elif case == "network":
        network = "-3"
    elif case == "public_key":
        public_key = "22" * 32
    elif case == "signature":
        proof = replace(
            proof,
            signature=base64.b64encode(b"0" * 64).decode("ascii"),
        )
    elif case == "state_init":
        proof = replace(proof, state_init="AAAA")
    elif case == "payload":
        proof = replace(proof, payload="Ж" * 43)
    elif case == "resolver_address":
        resolver = FakeTonWalletKeyResolver(
            public_key=vector.public_key,
            address="0:" + ("22" * 32),
        )
    elif case == "resolver_network":
        resolver = FakeTonWalletKeyResolver(
            public_key=vector.public_key,
            network="testnet",
        )
    else:  # pragma: no cover - ошибка таблицы теста
        raise AssertionError(case)
    return proof, address, network, public_key, resolver, expected_domain


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("domain", "DOMAIN_MISMATCH"),
        ("domain_length", "DOMAIN_LENGTH_MISMATCH"),
        ("expired", "TIMESTAMP_EXPIRED"),
        ("future", "TIMESTAMP_IN_FUTURE"),
        ("network", "NETWORK_MISMATCH"),
        ("public_key", "PUBLIC_KEY_MISMATCH"),
        ("signature", "SIGNATURE_INVALID"),
        ("state_init", "STATE_INIT_INVALID"),
        ("payload", "PAYLOAD_INVALID"),
        ("resolver_address", "STATE_INIT_ADDRESS_MISMATCH"),
        ("resolver_network", "NETWORK_MISMATCH"),
    ],
)
async def test_невалидные_ton_proof_vectors_отклоняются(
    case: str,
    reason: str,
) -> None:
    proof, address, network, public_key, resolver, domain = (
        _invalid_case(case)
    )
    consumer = FakeChallengeConsumer()
    with pytest.raises(TonProofVerificationError) as captured:
        await _service(consumer=consumer, resolver=resolver).verify(
            challenge_id=TON_PROOF_CHALLENGE_ID,
            address=address,
            network=network,
            public_key=public_key,
            proof=proof,  # type: ignore[arg-type]
            expected_domain=domain,
        )
    assert captured.value.reason == reason
    assert consumer.calls == []


@pytest.mark.asyncio
async def test_replay_отклоняется_после_успешной_crypto_verification() -> None:
    vector = build_ton_proof_vector()
    consumer = FakeChallengeConsumer(consumable=False)
    resolver = FakeTonWalletKeyResolver(public_key=vector.public_key)
    with pytest.raises(TonProofVerificationError) as captured:
        await _service(consumer=consumer, resolver=resolver).verify(
            challenge_id=TON_PROOF_CHALLENGE_ID,
            address=TON_PROOF_ADDRESS,
            network=TON_MAINNET_CHAIN,
            public_key=vector.public_key.hex(),
            proof=vector.proof,
            expected_domain=TON_PROOF_DOMAIN,
        )
    assert captured.value.reason == "CHALLENGE_NOT_CONSUMABLE"
    assert len(consumer.calls) == 1


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("proof", "timestamp"), True),
        (("proof", "domain", "lengthBytes"), True),
        (("ton_wallet_id",), 42),
        (("public_key",), 42),
        (("proof", "payload"), 42),
    ],
)
def test_ton_proof_http_schema_не_выполняет_type_coercion(
    path: tuple[str, ...],
    value: object,
) -> None:
    vector = build_ton_proof_vector()
    data: dict[str, object] = {
        "challenge_id": str(TON_PROOF_CHALLENGE_ID),
        "ton_wallet_id": TON_PROOF_ADDRESS,
        "network": TON_MAINNET_CHAIN,
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
    target = data
    for key in path[:-1]:
        target = target[key]  # type: ignore[assignment,index]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        TonLoginProofIn.model_validate(data)


def test_ton_proof_machine_contract_запрещает_auth_side_effects() -> None:
    contract = build_ton_proof_verification_contract()
    assert contract["цикл"] == 1616
    assert contract["проверки"]["ed25519_signature"] is True
    assert contract["side_effects"] == {
        "account_creation": False,
        "identity_storage": False,
        "session_issue": False,
        "auto_merge": False,
        "financial_update": False,
    }
