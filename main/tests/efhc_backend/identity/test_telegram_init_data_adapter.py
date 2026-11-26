"""Узкие tests Telegram initData adapter цикла 1619."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from app.identity.auth_provider import AuthProvider
from app.identity.telegram_init_data import (
    TelegramInitDataAdapter,
    TelegramInitDataError,
)

NOW = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)


def _hash(label: str = "valid") -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _parsed(
    *,
    provider_tg_id: object = 777,
    auth_date: object | None = None,
    received_hash: object | None = None,
) -> dict[str, object]:
    return {
        "auth_date": (
            str(int(NOW.timestamp()))
            if auth_date is None
            else auth_date
        ),
        "hash": _hash() if received_hash is None else received_hash,
        "user": {"id": provider_tg_id},
    }


def _adapter(payload: dict[str, object]) -> TelegramInitDataAdapter:
    return TelegramInitDataAdapter(
        lambda _raw: payload,
        clock=lambda: NOW,
    )


def test_adapter_возвращает_verified_telegram_identity() -> None:
    result = _adapter(_parsed()).verify(
        "auth_date=1&hash=x&user=y"
    )
    assert result.tg_id.value == 777
    assert result.verified_identity.provider is AuthProvider.TELEGRAM
    assert result.verified_identity.provider_subject == "777"
    assert _adapter(_parsed()).verify_subject(
        "auth_date=1&hash=x&user=y"
    ) == "777"
    assert len(result.replay_key) == 64
    rendered = repr(result)
    assert "777" not in rendered
    assert _hash() not in rendered


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (_parsed(provider_tg_id=True), "TG_ID_INVALID"),
        (_parsed(provider_tg_id=0), "TG_ID_INVALID"),
        (_parsed(provider_tg_id="777"), "TG_ID_INVALID"),
        (_parsed(auth_date="not-a-number"), "AUTH_DATE_INVALID"),
        (
            _parsed(
                auth_date=str(
                    int((NOW - timedelta(minutes=11)).timestamp())
                )
            ),
            "AUTH_DATE_EXPIRED",
        ),
        (
            _parsed(
                auth_date=str(
                    int((NOW + timedelta(minutes=1)).timestamp())
                )
            ),
            "AUTH_DATE_IN_FUTURE",
        ),
        (_parsed(received_hash="x"), "HASH_INVALID"),
    ],
)
def test_adapter_отклоняет_невалидные_provider_vectors(
    payload: dict[str, object],
    reason: str,
) -> None:
    with pytest.raises(TelegramInitDataError) as captured:
        _adapter(payload).verify("auth_date=1&hash=x&user=y")
    assert captured.value.reason == reason


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, "RAW_TYPE_INVALID"),
        ("", "RAW_FORMAT_INVALID"),
        (" a=1", "RAW_FORMAT_INVALID"),
        ("a=1&a=2", "DUPLICATE_FIELD"),
        ("ключ=1", "RAW_ASCII_REQUIRED"),
    ],
)
def test_adapter_отклоняет_нестрогий_raw_boundary(
    raw: object,
    reason: str,
) -> None:
    with pytest.raises(TelegramInitDataError) as captured:
        _adapter(_parsed()).verify(raw)
    assert captured.value.reason == reason


def test_adapter_переводит_ошибку_hmac_verifier_fail_closed() -> None:
    def reject(_raw: str) -> dict[str, object]:
        raise ValueError("raw secret must not escape")

    adapter = TelegramInitDataAdapter(reject, clock=lambda: NOW)
    with pytest.raises(TelegramInitDataError) as captured:
        adapter.verify("auth_date=1&hash=x&user=y")
    assert captured.value.reason == "SIGNATURE_OR_TTL_INVALID"
    assert "raw secret" not in str(captured.value)
