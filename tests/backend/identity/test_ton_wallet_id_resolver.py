from __future__ import annotations

import base64

import pytest
from app.identity.ton_wallet_id_resolver import (
    CanonicalTonWalletIdResolver,
    TonWalletIdResolutionError,
)
from app.lib import ton_address
from app.lib.ton_address import (
    canonicalize_ton_address,
    to_friendly_ton_address,
)

RAW = "0:" + ("AB" * 32)
CANONICAL = "0:" + ("ab" * 32)


def test_raw_и_friendly_формы_дают_единый_canonical_subject() -> None:
    forms = (
        RAW,
        to_friendly_ton_address(RAW, bounceable=True, url_safe=True),
        to_friendly_ton_address(RAW, bounceable=False, url_safe=True),
        to_friendly_ton_address(RAW, bounceable=True, url_safe=False),
        to_friendly_ton_address(RAW, testnet=True),
    )
    assert {canonicalize_ton_address(value) for value in forms} == {
        CANONICAL
    }


def test_resolver_возвращает_canonical_ton_wallet_id() -> None:
    result = CanonicalTonWalletIdResolver().resolve(RAW)
    assert result.raw == CANONICAL
    assert result.ton_wallet_id == CANONICAL
    assert result.workchain == 0
    assert result.account_id_hex == "ab" * 32
    assert "ab" * 8 not in repr(result)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        1,
        "+0:" + ("11" * 32),
        "00:" + ("11" * 32),
        "0:" + ("11" * 31),
        "0:" + ("11" * 32) + " ",
        "0:" + ("1 " * 32),
    ],
)
def test_неоднозначные_и_преобразованные_inputs_fail_closed(value: object) -> None:
    with pytest.raises(TonWalletIdResolutionError):
        CanonicalTonWalletIdResolver().resolve(value)


def test_friendly_с_неизвестным_tag_отклоняется_при_valid_checksum() -> None:
    parsed = ton_address.parse_ton_address(CANONICAL)
    body = bytes([0x31, 0]) + parsed.account_id
    checksum = ton_address._crc16_xmodem(body).to_bytes(2, "big")
    value = base64.urlsafe_b64encode(body + checksum).decode("ascii")
    with pytest.raises(
        TonWalletIdResolutionError,
        match="TON-адрес недействителен",
    ) as error:
        CanonicalTonWalletIdResolver().resolve(value)
    assert error.value.reason == "ADDRESS_TAG_INVALID"
