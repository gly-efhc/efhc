"""Ограниченные unit-контракты общего ядра регистрации."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from app.identity.account_registration import (
    AccountRegistrationError,
    NewAccountRequest,
    NewAccountResult,
    build_account_registration_contract,
    normalize_referral_start_param,
)
from app.identity.auth_provider import AuthProvider
from app.identity.types import GlobalId


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("ABCD2345", "ABCD2345"),
        (" ref_ABCD2345 ", "ABCD2345"),
        ("REF_ABCD_2345", "ABCD_2345"),
        ("bad code", None),
        ("ref_", None),
        ("abc", None),
        ("A" * 65, None),
    ],
)
def test_нормализация_referral_start_param(
    raw: str | None,
    expected: str | None,
) -> None:
    assert normalize_referral_start_param(raw) == expected


def test_request_и_result_неизменяемы() -> None:
    request = NewAccountRequest(
        provider=AuthProvider.TELEGRAM,
        tg_id=123456789,
        referral_start_param="ref_ABCD2345",
        username="efhc_user",
    )
    result = NewAccountResult(
        global_id=GlobalId(123),
        tg_id=123456789,
        referral_attached=True,
        referral_reason="attached",
    )

    with pytest.raises(FrozenInstanceError):
        request.tg_id = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.referral_attached = False  # type: ignore[misc]


def test_ошибка_регистрации_имеет_стабильный_reason() -> None:
    error = AccountRegistrationError("TRANSACTION_REQUIRED")
    assert error.reason == "TRANSACTION_REQUIRED"
    assert error.code == "account.registration_rejected"
    assert str(error) == "Новый аккаунт не может быть создан"


def test_контракт_1636_фиксирует_all_provider_migration() -> None:
    contract = build_account_registration_contract()
    assert contract["cycle"] == 1636
    assert contract["account_owner"] == "global_id"
    assert contract["transaction_required"] is True
    assert contract["commits_inside_service"] is False
    assert contract["creates"] == ["users", "referral_links"]
    assert contract["caller_migration"] == "bot_webapp_ton"
    assert contract["ton_referral_supported"] is True
    assert contract["invalid_referral"] == "fail_closed"
    assert contract["late_referral_binding"] == "forbidden"
