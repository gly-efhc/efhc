from __future__ import annotations

import base64
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

import httpx
from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.security_core import _get_secret_key
from app.core.utils_core import hmac_sha256_hex
from app.identity.ton_login_challenge import (
    TonLoginDomainError,
    resolve_ton_login_domain,
)
from app.identity.ton_proof_verification import (
    TonApiStateInitResolver,
    TonProofVerificationError,
    build_ton_proof_message,
    canonicalize_configured_ton_network,
    canonicalize_ton_network,
    decode_ton_signature,
    parse_ton_public_key,
    verify_ton_signature,
)
from app.integrations.ton_api_urls import ton_api_v2
from app.lib.time import utcnow
from app.lib.ton_address import ParsedAddress, TonAddressError
from app.lib.ton_address import (
    parse_ton_address as parse_canonical_ton_address,
)
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

TTL_MINUTES = 10
MAX_CLOCK_SKEW_SECONDS = 15 * 60
logger = get_logger(__name__)


class TonProofError(Exception):
    pass


class TonProofExpired(TonProofError):
    pass


class TonProofInvalid(TonProofError):
    pass


@dataclass(slots=True)
class TonProofPayloadOut:
    payload: str
    payload_token: str
    expires_at: datetime
    domain: str


@dataclass(slots=True)
class TonProofCheckOut:
    accepted: bool
    cryptographically_verified: bool
    reason: str


def _utcnow() -> datetime:
    return cast(datetime, utcnow())


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64u_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + pad).encode("utf-8"))


def _try_b64_decode(
    value: bytes,
    decoder: Callable[[bytes], bytes],
) -> bytes | None:
    try:
        return decoder(value)
    except (TypeError, ValueError):
        return None


def _b64_any_decode(value: str) -> bytes:
    txt = str(value or "").strip()
    if not txt:
        raise TonProofInvalid("BASE64_REQUIRED")
    padded = (txt + ("=" * (-len(txt) % 4))).encode("utf-8")
    decoders = (base64.b64decode, base64.urlsafe_b64decode)
    for decoder in decoders:
        decoded = _try_b64_decode(padded, decoder)
        if decoded is not None:
            return decoded
    raise TonProofInvalid("BASE64_INVALID")


def _resolve_domain(host: str | None) -> str:
    settings = get_settings()
    try:
        domain = resolve_ton_login_domain(
            environment=getattr(settings, "env_normalized", "local"),
            app_url=getattr(settings, "APP_URL", None),
            frontend_url=getattr(settings, "FRONTEND_URL", None),
            request_hostname=host,
        )
        return str(domain)
    except TonLoginDomainError as exc:
        raise TonProofInvalid(exc.reason) from exc


def _sign_payload(data: dict[str, object]) -> str:
    body = json.dumps(data, sort_keys=True, separators=(",", ":"))
    sig = hmac_sha256_hex(_get_secret_key(), body)
    enc = _b64u_encode(body.encode("utf-8"))
    return f"{enc}.{sig}"


def _unsign_payload(token: str) -> dict[str, object]:
    try:
        enc, sig = str(token).split(".", 1)
        raw = _b64u_decode(enc).decode("utf-8")
    except Exception as err:
        raise TonProofInvalid("INVALID_TOKEN") from err
    wanted = hmac_sha256_hex(_get_secret_key(), raw)
    if wanted != sig:
        raise TonProofInvalid("INVALID_TOKEN_SIG")
    try:
        data = json.loads(raw)
    except Exception as err:
        raise TonProofInvalid("INVALID_TOKEN_BODY") from err
    if not isinstance(data, dict):
        raise TonProofInvalid("INVALID_TOKEN_BODY")
    return {str(key): value for key, value in data.items()}


def parse_ton_address(value: object) -> ParsedAddress:
    """Использовать единый TON address resolver."""

    try:
        return parse_canonical_ton_address(value)
    except TonAddressError as exc:
        reason = str(exc) or "ADDRESS_INVALID"
        raise TonProofInvalid(reason) from exc


def _parse_public_key(value: str | None) -> bytes:
    txt = str(value or "").strip().lower()
    if txt.startswith("0x"):
        txt = txt[2:]
    if not txt:
        raise TonProofInvalid("PUBLIC_KEY_REQUIRED")
    try:
        out = bytes.fromhex(txt)
    except ValueError as err:
        raise TonProofInvalid("PUBLIC_KEY_INVALID") from err
    if len(out) != 32:
        raise TonProofInvalid("PUBLIC_KEY_INVALID")
    return out


def _verify_signature(
    *,
    public_key: bytes,
    signature: str,
    message_hash: bytes,
) -> None:
    sig = _b64_any_decode(signature)
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            sig,
            message_hash,
        )
    except InvalidSignature as err:
        raise TonProofInvalid("SIGNATURE_INVALID") from err
    except ValueError as err:
        raise TonProofInvalid("PUBLIC_KEY_INVALID") from err


def _candidate_api_bases() -> list[str]:
    settings = get_settings()
    seq: list[str] = []
    primary = ton_api_v2(settings.TON_API_BASE_URL)
    if primary:
        seq.append(primary)
    fb = str(getattr(settings, "TON_API_FALLBACK_URLS", "") or "")
    seq.extend([u.strip() for u in fb.split(",") if u.strip()])
    seq.extend(
        [
            "https://tonapi.io/v2",
            "https://toncenter.com/api/v2",
            "https://testnet.toncenter.com/api/v2",
        ]
    )
    out: list[str] = []
    for item in seq:
        url = item.rstrip("/")
        if url and url not in out:
            out.append(url)
    return out


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    key = str(getattr(settings, "TON_API_KEY", "") or "").strip()
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


def _extract_nested(obj: object, keys: tuple[str, ...]) -> str | None:
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    if cur is None:
        return None
    txt = str(cur).strip()
    return txt or None


def _object_to_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            return None
        try:
            return int(txt)
        except ValueError:
            return None
    return None


def _parse_tonapi_stateinit(
    data: dict[str, object],
) -> tuple[str, str] | None:
    variants = [data, data.get("result")]
    for item in variants:
        if not isinstance(item, dict):
            continue
        addr = _extract_nested(item, ("address",))
        pub = _extract_nested(item, ("public_key",))
        if addr and pub:
            return addr, pub
    return None


def _parse_toncenter_pubkey(data: dict[str, object]) -> str | None:
    stack = data.get("result")
    if isinstance(stack, dict):
        stack = stack.get("stack")
    if not isinstance(stack, list):
        return None
    for item in stack:
        if not isinstance(item, list) or len(item) < 2:
            continue
        value = str(item[1] or "").strip().lower()
        if value.startswith("0x"):
            value = value[2:]
        if value:
            return value.zfill(64)
    return None


async def _tonapi_stateinit_lookup(
    *,
    base: str,
    state_init: str,
) -> tuple[str, str] | None:
    if "tonapi" not in base:
        return None
    endpoint = base.rstrip("/")
    if not endpoint.endswith("/v2"):
        endpoint = endpoint + "/v2"
    url = endpoint + "/tonconnect/stateinit"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            url,
            json={"state_init": state_init},
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    return _parse_tonapi_stateinit(data)


async def _toncenter_get_public_key(
    *,
    base: str,
    address: str,
) -> str | None:
    if "toncenter" not in base:
        return None
    url = base.rstrip("/") + "/runGetMethod"
    params = {
        "address": address,
        "method": "get_public_key",
        "stack": "[]",
    }
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return _parse_toncenter_pubkey(data)


async def _resolve_public_key(
    *,
    address: str,
    state_init: str | None,
) -> tuple[bytes | None, str]:
    """Получить authoritative public key только из verified state-init."""
    if not state_init:
        raise TonProofInvalid("STATE_INIT_REQUIRED")
    settings = get_settings()
    try:
        configured_network = canonicalize_configured_ton_network(
            settings.TON_NETWORK
        )
        resolver = TonApiStateInitResolver(
            base_url=str(settings.TON_API_BASE_URL),
            api_key=str(settings.TON_API_KEY or ""),
            configured_network=str(settings.TON_NETWORK),
        )
        material = await resolver.resolve(
            state_init=state_init,
            address=parse_ton_address(address).raw,
            network=configured_network,
        )
    except TonProofVerificationError as err:
        raise TonProofInvalid(err.reason) from err
    return material.public_key, material.source


def issue_payload(
    *,
    tg_id: int,
    host: str | None,
) -> TonProofPayloadOut:
    now = _utcnow()
    exp = now + timedelta(minutes=TTL_MINUTES)
    payload = f"efhc_tp_{secrets.token_urlsafe(18)}"
    domain = _resolve_domain(host)
    token = _sign_payload(
        {
            "v": 1,
            "tg_id": int(tg_id),
            "payload": payload,
            "domain": domain,
            "exp": int(exp.timestamp()),
        }
    )
    return TonProofPayloadOut(
        payload=payload,
        payload_token=token,
        expires_at=exp,
        domain=domain,
    )


async def check_proof(
    *,
    tg_id: int,
    host: str | None,
    address: str,
    payload_token: str,
    proof: dict[str, object],
    public_key: str | None,
    network: str | None = None,
) -> TonProofCheckOut:
    token = _unsign_payload(payload_token)
    exp = _object_to_int(token.get("exp", 0))
    if exp is None:
        raise TonProofInvalid("INVALID_TOKEN_BODY")
    token_tg_id = _object_to_int(token.get("tg_id", 0))
    if token_tg_id is None:
        raise TonProofInvalid("INVALID_TOKEN_BODY")
    now_ts = int(_utcnow().timestamp())
    if token_tg_id != int(tg_id):
        raise TonProofInvalid("TG_ID_MISMATCH")
    if exp < now_ts:
        raise TonProofExpired("TOKEN_EXPIRED")
    expected_domain = str(token.get("domain", "") or "")
    host_domain = _resolve_domain(host)
    if (
        expected_domain
        and host_domain
        and host_domain != expected_domain
    ):
        raise TonProofInvalid("DOMAIN_MISMATCH")
    parsed_addr = parse_ton_address(address)
    settings = get_settings()
    try:
        configured_network = canonicalize_configured_ton_network(
            settings.TON_NETWORK
        )
        if network is None:
            canonical_network = configured_network
        else:
            canonical_network = canonicalize_ton_network(network)
        if canonical_network != configured_network:
            raise TonProofInvalid("NETWORK_MISMATCH")
    except TonProofVerificationError as err:
        raise TonProofInvalid(err.reason) from err
    payload = str(proof.get("payload", "") or "")
    if payload != str(token.get("payload", "") or ""):
        raise TonProofInvalid("PAYLOAD_MISMATCH")
    domain = proof.get("domain")
    if not isinstance(domain, dict):
        raise TonProofInvalid("DOMAIN_REQUIRED")
    proof_domain = str(domain.get("value", "") or "").lower().strip()
    if expected_domain and proof_domain != expected_domain:
        raise TonProofInvalid("PROOF_DOMAIN_MISMATCH")
    length_bytes = _object_to_int(domain.get("lengthBytes", 0))
    if length_bytes is None:
        raise TonProofInvalid("PROOF_DOMAIN_LENGTH_MISMATCH")
    if length_bytes != len(proof_domain.encode("utf-8")):
        raise TonProofInvalid("PROOF_DOMAIN_LENGTH_MISMATCH")
    timestamp = _object_to_int(proof.get("timestamp", 0))
    if timestamp is None:
        raise TonProofInvalid("TIMESTAMP_INVALID")
    if abs(now_ts - timestamp) > MAX_CLOCK_SKEW_SECONDS:
        raise TonProofInvalid("TIMESTAMP_EXPIRED")
    signature = str(proof.get("signature", "") or "")
    if not signature:
        raise TonProofInvalid("SIGNATURE_REQUIRED")
    state_init = str(proof.get("state_init", "") or "").strip() or None
    resolved_key, source = await _resolve_public_key(
        address=address,
        state_init=state_init,
    )
    if resolved_key is None:
        raise TonProofInvalid("PUBLIC_KEY_UNRESOLVED")
    try:
        client_key = parse_ton_public_key(public_key)
    except TonProofVerificationError as err:
        raise TonProofInvalid(err.reason) from err
    if resolved_key != client_key:
        raise TonProofInvalid("PUBLIC_KEY_MISMATCH")
    msg_hash = build_ton_proof_message(
        address=parsed_addr,
        domain=proof_domain,
        timestamp=timestamp,
        payload=payload,
    )
    try:
        verify_ton_signature(
            public_key=resolved_key,
            signature=decode_ton_signature(signature),
            message=msg_hash,
        )
    except TonProofVerificationError as err:
        raise TonProofInvalid(err.reason) from err
    return TonProofCheckOut(
        accepted=True,
        cryptographically_verified=True,
        reason="PROOF_VERIFIED:" + source,
    )
