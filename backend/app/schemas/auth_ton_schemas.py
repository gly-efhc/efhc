"""HTTP schemas provider-neutral TON login циклов 1615–1618."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.identity.auth_provider import AuthProvider
from app.identity.ton_login_challenge import (
    TON_LOGIN_CANONICAL_FORMAT,
    TON_LOGIN_PURPOSE,
)
from app.schemas.common_schemas import EfhcBaseModel
from pydantic import ConfigDict, Field, StrictInt, StrictStr


class TonLoginChallengeOut(EfhcBaseModel):
    """One-time challenge для последующего TON Proof."""

    challenge_id: UUID
    payload: str = Field(min_length=32, max_length=128)
    expires_at: datetime
    domain: str = Field(min_length=1, max_length=255)
    provider: Literal["ton"] = AuthProvider.TON.value
    purpose: Literal["ton.login"] = TON_LOGIN_PURPOSE
    canonical_address_format: str = TON_LOGIN_CANONICAL_FORMAT


class TonProofDomainIn(EfhcBaseModel):
    """Exact domain contract без coercions."""

    model_config = ConfigDict(extra="forbid")

    length_bytes: StrictInt = Field(
        ge=1,
        le=255,
        validation_alias="lengthBytes",
        serialization_alias="lengthBytes",
    )
    value: StrictStr = Field(min_length=1, max_length=255)


class TonProofDataIn(EfhcBaseModel):
    """TON Proof wire payload после Pydantic type validation."""

    model_config = ConfigDict(extra="forbid")

    timestamp: StrictInt = Field(gt=0)
    domain: TonProofDomainIn
    signature: StrictStr = Field(min_length=1, max_length=256)
    payload: StrictStr = Field(min_length=32, max_length=128)
    state_init: StrictStr = Field(min_length=8, max_length=131072)


class TonLoginProofIn(EfhcBaseModel):
    """Запрос cryptographic TON Proof verification."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    ton_wallet_id: StrictStr = Field(min_length=48, max_length=128)
    network: Literal["-239", "-3"]
    public_key: StrictStr = Field(min_length=64, max_length=64)
    proof: TonProofDataIn
    referral_start_param: StrictStr | None = Field(
        default=None,
        max_length=128,
    )


class AuthSessionCredentialOut(EfhcBaseModel):
    """Одноразовый bearer credential без хранения raw token в БД."""

    model_config = ConfigDict(extra="forbid")

    access_token: StrictStr = Field(
        min_length=32,
        max_length=128,
        repr=False,
    )
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: datetime


class TonLoginProofOut(EfhcBaseModel):
    """Результат proof, account resolution и одноразовой session."""

    verified: Literal[True] = True
    challenge_id: UUID
    provider: Literal["ton"] = AuthProvider.TON.value
    ton_wallet_id: str = Field(min_length=66, max_length=76)
    network: Literal["mainnet", "testnet"]
    verified_at: datetime
    global_id: str = Field(pattern=r"^[0-9]{10}$")
    account_outcome: Literal[
        "existing_identity",
        "existing_binding",
        "registered",
    ]
    session: AuthSessionCredentialOut


__all__ = [
    "AuthSessionCredentialOut",
    "TonLoginChallengeOut",
    "TonLoginProofIn",
    "TonLoginProofOut",
    "TonProofDataIn",
    "TonProofDomainIn",
]
