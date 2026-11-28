from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest
from app.services import tonconnect_proof_service as service
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)


@pytest.mark.asyncio
async def test_tonproof_verifies_domain_network_message_and_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(service, "_utcnow", lambda: now)
    monkeypatch.setattr(service, "_get_secret_key", lambda: "unit-secret")
    issued = service.issue_payload(tg_id=1001, host="efhc.app")
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    address = "0:" + ("11" * 32)
    parsed = service.parse_ton_address(address)
    timestamp = int(now.timestamp())
    message = service.build_ton_proof_message(
        address=parsed,
        domain="efhc.app",
        timestamp=timestamp,
        payload=issued.payload,
    )
    signature = base64.b64encode(
        private_key.sign(message),
    ).decode("ascii")

    async def resolve_public_key(**_kwargs):
        return public_key, "unit_resolved_key"

    monkeypatch.setattr(
        service,
        "_resolve_public_key",
        resolve_public_key,
    )
    out = await service.check_proof(
        tg_id=1001,
        host="efhc.app",
        address=address,
        payload_token=issued.payload_token,
        proof={
            "timestamp": timestamp,
            "domain": {
                "lengthBytes": len("efhc.app"),
                "value": "efhc.app",
            },
            "signature": signature,
            "payload": issued.payload,
            "state_init": None,
        },
        public_key=public_key.hex(),
    )
    assert out.accepted is True
    assert out.cryptographically_verified is True
    assert out.reason == "PROOF_VERIFIED:unit_resolved_key"


@pytest.mark.asyncio
async def test_tonproof_rejects_wrong_domain_before_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(service, "_utcnow", lambda: now)
    monkeypatch.setattr(service, "_get_secret_key", lambda: "unit-secret")
    issued = service.issue_payload(tg_id=1001, host="efhc.app")
    with pytest.raises(
        service.TonProofInvalid,
        match="PROOF_DOMAIN_MISMATCH",
    ):
        await service.check_proof(
            tg_id=1001,
            host="efhc.app",
            address="0:" + ("11" * 32),
            payload_token=issued.payload_token,
            proof={
                "timestamp": int(now.timestamp()),
                "domain": {
                    "lengthBytes": len("evil.example"),
                    "value": "evil.example",
                },
                "signature": base64.b64encode(b"0" * 64).decode(),
                "payload": issued.payload,
                "state_init": None,
            },
            public_key="22" * 32,
        )
