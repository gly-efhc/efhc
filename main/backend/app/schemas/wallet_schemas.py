from __future__ import annotations

from datetime import datetime

from app.schemas.common_schemas import CursorPage, EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import Field


class WalletItemOut(EfhcBaseModel):
    id: ApiLifetimeId
    wallet_address: str
    wallet_app: str | None
    is_primary: bool
    is_active: bool
    proof_verified: bool
    created_at: str


class WalletMeOut(EfhcBaseModel):
    is_connected: bool
    wallets: list[WalletItemOut]


class WalletConnectIn(EfhcBaseModel):
    address: str = Field(..., min_length=1, max_length=256)
    wallet_app: str | None = Field(default=None, max_length=32)
    payload_token: str = Field(..., min_length=20, max_length=2048)
    proof: WalletTonProofProofIn
    public_key: str = Field(..., min_length=64, max_length=64)
    network: str = Field(..., pattern=r"^(?:-239|-3)$")


class WalletConnectOut(EfhcBaseModel):
    wallet_id: ApiLifetimeId
    wallet_address: str
    is_connected: bool


class WalletBalanceHistoryItem(EfhcBaseModel):
    id: ApiLifetimeId
    amount_efhc: str
    direction: str
    balance_type: str
    reason: str
    created_at: datetime


WalletBalanceHistoryOut = CursorPage[WalletBalanceHistoryItem]


class WalletTonProofPayloadOut(EfhcBaseModel):
    ton_proof_payload: str
    payload_token: str
    expires_at: datetime
    domain: str


class WalletTonProofDomainIn(EfhcBaseModel):
    lengthBytes: int
    value: str


class WalletTonProofProofIn(EfhcBaseModel):
    timestamp: int
    domain: WalletTonProofDomainIn
    signature: str
    payload: str
    state_init: str = Field(..., min_length=1, max_length=131072)


class WalletTonProofCheckIn(EfhcBaseModel):
    address: str = Field(..., min_length=20, max_length=256)
    payload_token: str = Field(..., min_length=20, max_length=2048)
    proof: WalletTonProofProofIn
    network: str = Field(..., pattern=r"^(?:-239|-3)$")
    public_key: str = Field(..., min_length=64, max_length=64)


class WalletTonProofCheckOut(EfhcBaseModel):
    accepted: bool
    cryptographically_verified: bool
    reason: str
