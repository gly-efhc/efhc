"""HTTP schemas Telegram initData session цикла 1619."""

from __future__ import annotations

from typing import Literal

from app.identity.auth_provider import AuthProvider
from app.schemas.auth_ton_schemas import AuthSessionCredentialOut
from app.schemas.common_schemas import EfhcBaseModel
from pydantic import ConfigDict, Field, StrictStr


class TelegramAuthSessionIn(EfhcBaseModel):
    """Необязательный transport без owner semantics."""

    model_config = ConfigDict(extra="forbid")

    referral_start_param: StrictStr | None = Field(
        default=None,
        max_length=128,
    )


class TelegramAuthSessionOut(EfhcBaseModel):
    """Безопасный результат Telegram adapter и session issue."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["telegram"] = AuthProvider.TELEGRAM.value
    global_id: str = Field(pattern=r"^[0-9]{10}$")
    account_outcome: Literal[
        "existing_identity",
        "registered",
    ]
    session: AuthSessionCredentialOut


__all__ = ["TelegramAuthSessionIn", "TelegramAuthSessionOut"]
