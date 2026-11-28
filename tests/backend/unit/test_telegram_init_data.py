import hashlib
import hmac
import json
import time
import urllib.parse

import pytest
from app.core.config_core import get_settings
from app.core.security_core import validate_telegram__init__data
from fastapi import HTTPException


def _make__init__data(bot_token: str, payload: dict) -> str:
    """Сборка Telegram WebApp initData для unit-теста."""
    payload = dict(payload)

    user = payload.get("user")
    if isinstance(user, dict | list):
        payload["user"] = json.dumps(user, separators=(",", ":"))

    items = [(k, str(v)) for k, v in payload.items() if k != "hash"]
    items.sort(key=lambda x: x[0])
    check_string = "\n".join([f"{k}={v}" for k, v in items])

    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    calc_hash = hmac.new(
        secret_key,
        check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    payload_with_hash = dict(payload)
    payload_with_hash["hash"] = calc_hash
    return urllib.parse.urlencode(payload_with_hash)


@pytest.mark.unit
def test_validate_telegram__init__data_ok(monkeypatch):
    """Корректный initData проходит проверку."""
    bot_token = "TEST_BOT_TOKEN:123456"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", bot_token)

    # settings кэшируются — чистим
    get_settings.cache_clear()

    now = int(time.time())
    init_data = _make__init__data(
        bot_token,
        {
            "query_id": "AAEAAAE",
            "auth_date": str(now),
            "user": {"id": 777, "first_name": "Test"},
        },
    )

    parsed = validate_telegram__init__data(init_data)
    assert isinstance(parsed, dict)
    assert parsed.get("user", {}).get("id") == 777


@pytest.mark.unit
def test_validate_telegram__init__data_invalid_hash(monkeypatch):
    """Некорректный hash должен приводить к ошибке."""
    bot_token = "TEST_BOT_TOKEN:123456"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", bot_token)

    get_settings.cache_clear()

    now = int(time.time())
    init_data = _make__init__data(
        bot_token,
        {
            "query_id": "AAEAAAE",
            "auth_date": str(now),
            "user": {"id": 777, "first_name": "Test"},
        },
    )

    init_data += "x"

    with pytest.raises(HTTPException):
        validate_telegram__init__data(init_data)


@pytest.mark.unit
def test_validate_telegram__init__data_ttl_expired(monkeypatch):
    """Просроченный auth_date должен приводить к ошибке."""
    bot_token = "TEST_BOT_TOKEN:123456"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", bot_token)

    get_settings.cache_clear()

    old = int(time.time()) - 3600
    init_data = _make__init__data(
        bot_token,
        {
            "query_id": "AAEAAAE",
            "auth_date": str(old),
            "user": {"id": 777, "first_name": "Test"},
        },
    )

    with pytest.raises(HTTPException):
        validate_telegram__init__data(init_data)


@pytest.mark.unit
def test_validate_telegram__init__data_missing_auth_date_fails(
    monkeypatch,
):
    """Отсутствующий auth_date должен fail-closed."""
    bot_token = "TEST_BOT_TOKEN:123456"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", bot_token)

    get_settings.cache_clear()

    init_data = _make__init__data(
        bot_token,
        {
            "query_id": "AAEAAAE",
            "user": {"id": 777, "first_name": "Test"},
        },
    )

    with pytest.raises(HTTPException):
        validate_telegram__init__data(init_data)


@pytest.mark.unit
def test_validate_telegram__init__data_non_numeric_auth_date_fails(
    monkeypatch,
):
    """Нечисловой auth_date должен fail-closed."""
    bot_token = "TEST_BOT_TOKEN:123456"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", bot_token)

    get_settings.cache_clear()

    init_data = _make__init__data(
        bot_token,
        {
            "query_id": "AAEAAAE",
            "auth_date": "not-a-number",
            "user": {"id": 777, "first_name": "Test"},
        },
    )

    with pytest.raises(HTTPException):
        validate_telegram__init__data(init_data)
