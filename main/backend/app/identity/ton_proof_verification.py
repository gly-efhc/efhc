"""Provider-neutral TON Proof verification цикла 1616.

Модуль проверяет domain, timestamp, network, state-init,
Ed25519 signature и одноразовое consumption challenge.
Account, identity и session здесь не создаются.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Final, Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from app.identity.auth_errors import AuthChallengeNotConsumable
from app.identity.auth_provider import AuthProvider
from app.identity.auth_runtime_services import ConsumedAuthChallenge
from app.identity.provider_registry import (
    finalize_verified_provider_subject,
)
from app.identity.ton_login_challenge import (
    TON_LOGIN_PURPOSE,
    canonicalize_ton_login_domain,
)
from app.identity.verified_identity import VerifiedIdentity
from app.lib.time import utcnow
from app.lib.ton_address import ParsedAddress, parse_ton_address
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

TonNetwork = Literal["mainnet", "testnet"]

TON_MAINNET_CHAIN: Final[str] = "-239"
TON_TESTNET_CHAIN: Final[str] = "-3"
TON_PROOF_MAX_AGE_SECONDS: Final[int] = 15 * 60
TON_PROOF_MAX_FUTURE_SKEW_SECONDS: Final[int] = 60
TON_PROOF_STATE_INIT_MAX_BYTES: Final[int] = 64 * 1024
TON_PROOF_PREFIX: Final[bytes] = b"ton-proof-item-v2/"
TON_CONNECT_PREFIX: Final[bytes] = b"ton-connect"
_NETWORK_BY_CHAIN: Final[dict[str, TonNetwork]] = {
    TON_MAINNET_CHAIN: "mainnet",
    TON_TESTNET_CHAIN: "testnet",
}
_PUBLIC_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{64}$"
)
_BOC_MAGIC: Final[bytes] = bytes.fromhex("b5ee9c72")


class TonProofVerificationError(ValueError):
    """TON Proof отклонён без раскрытия proof."""

    code = "auth.ton_proof_invalid"
    message = "TON Proof недействителен"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class TonProofData:
    """Строгие поля TON Proof после HTTP validation."""

    timestamp: int
    domain_length_bytes: int
    domain: str
    signature: str
    payload: str
    state_init: str


@dataclass(frozen=True, slots=True)
class TonWalletKeyMaterial:
    """Authoritative key/address из state-init."""

    address: str
    public_key: bytes
    network: TonNetwork
    source: str

    def __repr__(self) -> str:
        return (
            "TonWalletKeyMaterial("
            "address='<redacted>', public_key='<redacted>', "
            f"network={self.network!r}, source={self.source!r})"
        )


@dataclass(frozen=True, slots=True)
class VerifiedTonProof:
    """Cryptographic result без account/session side effects."""

    challenge_id: UUID
    verified_identity: VerifiedIdentity
    network: TonNetwork
    verified_at: datetime
    key_source: str

    @property
    def ton_wallet_id(self) -> str:
        """Вернуть ``ton_wallet_id`` — канонический адрес TON-кошелька."""

        return str(self.verified_identity.provider_subject)

    def __repr__(self) -> str:
        return (
            "VerifiedTonProof("
            f"challenge_id={self.challenge_id!r}, "
            "ton_wallet_id='<redacted>', "
            f"network={self.network!r}, "
            f"key_source={self.key_source!r})"
        )


class ChallengeConsumer(Protocol):
    """Порт атомарного consumption challenge."""

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
        """Потребить challenge ровно один раз."""


class TonWalletKeyResolver(Protocol):
    """Доверенный resolver state-init → address/public key."""

    async def resolve(
        self,
        *,
        state_init: str,
        address: str,
        network: TonNetwork,
    ) -> TonWalletKeyMaterial:
        """Вернуть authoritative key material из state-init."""


def canonicalize_ton_network(value: object) -> TonNetwork:
    """Преобразовать chain id в network name."""

    if not isinstance(value, str) or value not in _NETWORK_BY_CHAIN:
        raise TonProofVerificationError("NETWORK_INVALID")
    return _NETWORK_BY_CHAIN[value]


def canonicalize_configured_ton_network(
    value: object,
) -> TonNetwork:
    """Проверить configured network без wire coercions."""

    if not isinstance(value, str):
        raise TonProofVerificationError("NETWORK_CONFIG_INVALID")
    network = value.strip().lower()
    if network not in {"mainnet", "testnet"}:
        raise TonProofVerificationError("NETWORK_CONFIG_INVALID")
    if network == "mainnet":
        return "mainnet"
    return "testnet"


def _decode_base64_strict(
    value: object,
    *,
    reason: str,
) -> bytes:
    if not isinstance(value, str) or not value or not value.isascii():
        raise TonProofVerificationError(reason)
    padded = value + ("=" * (-len(value) % 4))
    try:
        return base64.b64decode(
            padded.encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise TonProofVerificationError(reason) from exc


def validate_ton_state_init(value: object) -> str:
    """Проверить bounded Base64 BoC state-init."""

    if not isinstance(value, str):
        raise TonProofVerificationError("STATE_INIT_INVALID")
    decoded = _decode_base64_strict(
        value,
        reason="STATE_INIT_INVALID",
    )
    if (
        len(decoded) < len(_BOC_MAGIC)
        or len(decoded) > TON_PROOF_STATE_INIT_MAX_BYTES
        or not decoded.startswith(_BOC_MAGIC)
    ):
        raise TonProofVerificationError("STATE_INIT_INVALID")
    return value


def parse_ton_public_key(value: object) -> bytes:
    """Разобрать exact 32-byte Ed25519 public key hex."""

    if not isinstance(value, str):
        raise TonProofVerificationError("PUBLIC_KEY_INVALID")
    if _PUBLIC_KEY_PATTERN.fullmatch(value) is None:
        raise TonProofVerificationError("PUBLIC_KEY_INVALID")
    return bytes.fromhex(value)


def decode_ton_signature(value: object) -> bytes:
    """Разобрать exact 64-byte Ed25519 signature."""

    signature = _decode_base64_strict(
        value,
        reason="SIGNATURE_INVALID",
    )
    if len(signature) != 64:
        raise TonProofVerificationError("SIGNATURE_INVALID")
    return signature


def build_ton_proof_message(
    *,
    address: ParsedAddress,
    domain: str,
    timestamp: int,
    payload: str,
) -> bytes:
    """Построить TON Connect v2 proof digest."""

    domain_bytes = domain.encode("utf-8")
    payload_bytes = payload.encode("utf-8")
    message = b"".join(
        [
            TON_PROOF_PREFIX,
            int(address.workchain).to_bytes(4, "big", signed=True),
            address.account_id,
            len(domain_bytes).to_bytes(4, "little", signed=False),
            domain_bytes,
            int(timestamp).to_bytes(8, "little", signed=False),
            payload_bytes,
        ]
    )
    prefix = b"\xff\xff" + TON_CONNECT_PREFIX
    return sha256(prefix + sha256(message).digest()).digest()


def verify_ton_signature(
    *,
    public_key: bytes,
    signature: bytes,
    message: bytes,
) -> None:
    """Проверить Ed25519 signature fail closed."""

    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            message,
        )
    except (InvalidSignature, ValueError) as exc:
        raise TonProofVerificationError("SIGNATURE_INVALID") from exc


def _parse_state_init_response(data: object) -> tuple[str, str]:
    variants = [data]
    if isinstance(data, dict):
        variants.append(data.get("result"))
    for item in variants:
        if not isinstance(item, dict):
            continue
        address = item.get("address")
        public_key = item.get("public_key")
        if isinstance(address, str) and isinstance(public_key, str):
            return address, public_key
    raise TonProofVerificationError("STATE_INIT_RESOLUTION_INVALID")


class TonApiStateInitResolver:
    """Проверить state-init через TonAPI fail closed."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        configured_network: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        parsed = urlsplit(base_url.strip().rstrip("/"))
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise TonProofVerificationError("TON_API_CONFIG_INVALID")
        self._base_url = base_url.strip().rstrip("/")
        self._api_key = api_key.strip()
        self._configured_network = canonicalize_configured_ton_network(
            configured_network
        )
        self._timeout_seconds = timeout_seconds

    async def resolve(
        self,
        *,
        state_init: str,
        address: str,
        network: TonNetwork,
    ) -> TonWalletKeyMaterial:
        state_init_value = validate_ton_state_init(state_init)
        if network != self._configured_network:
            raise TonProofVerificationError("NETWORK_MISMATCH")
        endpoint = self._base_url
        if not endpoint.endswith("/v2"):
            endpoint += "/v2"
        endpoint += "/tonconnect/stateinit"
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds
            ) as client:
                response = await client.post(
                    endpoint,
                    json={"state_init": state_init_value},
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TonProofVerificationError(
                "STATE_INIT_RESOLUTION_FAILED"
            ) from exc
        resolved_address, public_key_text = (
            _parse_state_init_response(data)
        )
        try:
            canonical_resolved = parse_ton_address(
                resolved_address
            ).raw
        except ValueError as exc:
            raise TonProofVerificationError(
                "STATE_INIT_RESOLUTION_INVALID"
            ) from exc
        if canonical_resolved != address:
            raise TonProofVerificationError(
                "STATE_INIT_ADDRESS_MISMATCH"
            )
        return TonWalletKeyMaterial(
            address=canonical_resolved,
            public_key=parse_ton_public_key(public_key_text),
            network=network,
            source="tonapi_state_init",
        )


class TonProofVerificationService:
    """Проверить proof и закрыть challenge."""

    def __init__(
        self,
        *,
        challenge_consumer: ChallengeConsumer,
        key_resolver: TonWalletKeyResolver,
        configured_network: str,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._challenge_consumer = challenge_consumer
        self._key_resolver = key_resolver
        self._configured_network = canonicalize_configured_ton_network(
            configured_network
        )
        self._clock = clock

    async def verify(
        self,
        *,
        challenge_id: UUID,
        address: str,
        network: str,
        public_key: str,
        proof: TonProofData,
        expected_domain: str,
    ) -> VerifiedTonProof:
        if not isinstance(challenge_id, UUID):
            raise TonProofVerificationError("CHALLENGE_ID_INVALID")
        canonical_network = canonicalize_ton_network(network)
        if canonical_network != self._configured_network:
            raise TonProofVerificationError("NETWORK_MISMATCH")
        canonical_domain = canonicalize_ton_login_domain(
            expected_domain
        )
        proof_domain = canonicalize_ton_login_domain(proof.domain)
        if proof_domain != canonical_domain:
            raise TonProofVerificationError("DOMAIN_MISMATCH")
        if (
            isinstance(proof.domain_length_bytes, bool)
            or proof.domain_length_bytes
            != len(proof_domain.encode("utf-8"))
        ):
            raise TonProofVerificationError("DOMAIN_LENGTH_MISMATCH")
        now = self._clock()
        if now.tzinfo is None:
            raise TonProofVerificationError("CLOCK_INVALID")
        now_ts = int(now.timestamp())
        if isinstance(proof.timestamp, bool) or proof.timestamp <= 0:
            raise TonProofVerificationError("TIMESTAMP_INVALID")
        if proof.timestamp < now_ts - TON_PROOF_MAX_AGE_SECONDS:
            raise TonProofVerificationError("TIMESTAMP_EXPIRED")
        if proof.timestamp > now_ts + TON_PROOF_MAX_FUTURE_SKEW_SECONDS:
            raise TonProofVerificationError("TIMESTAMP_IN_FUTURE")
        if (
            not isinstance(proof.payload, str)
            or not proof.payload.isascii()
        ):
            raise TonProofVerificationError("PAYLOAD_INVALID")
        state_init = validate_ton_state_init(proof.state_init)
        try:
            parsed_address = parse_ton_address(address)
        except ValueError as exc:
            raise TonProofVerificationError("ADDRESS_INVALID") from exc
        authoritative = await self._key_resolver.resolve(
            state_init=state_init,
            address=parsed_address.raw,
            network=canonical_network,
        )
        if authoritative.network != canonical_network:
            raise TonProofVerificationError("NETWORK_MISMATCH")
        if authoritative.address != parsed_address.raw:
            raise TonProofVerificationError(
                "STATE_INIT_ADDRESS_MISMATCH"
            )
        client_key = parse_ton_public_key(public_key)
        if client_key != authoritative.public_key:
            raise TonProofVerificationError("PUBLIC_KEY_MISMATCH")
        message = build_ton_proof_message(
            address=parsed_address,
            domain=proof_domain,
            timestamp=proof.timestamp,
            payload=proof.payload,
        )
        verify_ton_signature(
            public_key=authoritative.public_key,
            signature=decode_ton_signature(proof.signature),
            message=message,
        )
        try:
            consumed = await self._challenge_consumer.consume(
                proof.payload,
                provider=AuthProvider.TON,
                purpose=TON_LOGIN_PURPOSE,
                domain=canonical_domain,
                expected_challenge_id=challenge_id,
            )
        except AuthChallengeNotConsumable as exc:
            raise TonProofVerificationError(
                "CHALLENGE_NOT_CONSUMABLE"
            ) from exc
        identity = finalize_verified_provider_subject(
            AuthProvider.TON,
            parsed_address.raw,
        )
        return VerifiedTonProof(
            challenge_id=consumed.challenge_id,
            verified_identity=identity,
            network=canonical_network,
            verified_at=now,
            key_source=authoritative.source,
        )


def build_ton_proof_verification_contract() -> dict[str, object]:
    """Сформировать machine contract цикла 1616."""

    return {
        "схема": "EFHC_TON_PROOF_VERIFICATION_V1",
        "цикл": 1616,
        "provider": AuthProvider.TON.value,
        "provider_subject_field": "ton_wallet_id",
        "provider_subject_semantics": "TON wallet address",
        "ton_wallet_id": "<workchain>:<64 lowercase hex account_id>",
        "проверки": {
            "domain": True,
            "timestamp": True,
            "network": True,
            "state_init": True,
            "public_key_authoritative": True,
            "ed25519_signature": True,
            "challenge_ttl": True,
            "replay": "atomic_postgresql_consume",
        },
        "side_effects": {
            "account_creation": False,
            "identity_storage": False,
            "session_issue": False,
            "auto_merge": False,
            "financial_update": False,
        },
    }


__all__ = [
    "TON_MAINNET_CHAIN",
    "TON_PROOF_MAX_AGE_SECONDS",
    "TON_PROOF_MAX_FUTURE_SKEW_SECONDS",
    "TON_TESTNET_CHAIN",
    "TonApiStateInitResolver",
    "TonProofData",
    "TonProofVerificationError",
    "TonNetwork",
    "TonProofVerificationService",
    "TonWalletKeyMaterial",
    "TonWalletKeyResolver",
    "VerifiedTonProof",
    "build_ton_proof_message",
    "build_ton_proof_verification_contract",
    "canonicalize_configured_ton_network",
    "canonicalize_ton_network",
    "decode_ton_signature",
    "parse_ton_public_key",
    "validate_ton_state_init",
    "verify_ton_signature",
]
