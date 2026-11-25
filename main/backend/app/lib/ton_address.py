"""Строгая канонизация TON-адресов без внешних зависимостей.

Внутренний owner/identity формат EFHC:
``<workchain>:<64 lowercase hex account_id>``.

Friendly base64/base64url формы принимаются только при корректном tag,
длине и CRC16-XMODEM. Любая неоднозначная либо частично разобранная
строка завершается fail closed.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from typing import Final

_RAW_ADDRESS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<workchain>-?(?:0|[1-9][0-9]*)):(?P<account>[0-9A-Fa-f]{64})$"
)
_ALLOWED_FRIENDLY_TAGS: Final[frozenset[int]] = frozenset(
    {0x11, 0x51, 0x91, 0xD1}
)
_INT32_MIN: Final[int] = -(2**31)
_INT32_MAX: Final[int] = (2**31) - 1


class TonAddressError(ValueError):
    """TON-адрес не прошёл строгую канонизацию."""


@dataclass(frozen=True, slots=True)
class ParsedAddress:
    """Однозначно разобранный TON-адрес."""

    workchain: int
    account_id: bytes
    raw: str

    @property
    def account_id_hex(self) -> str:
        """Вернуть 64 lowercase hex символа account id."""

        return self.account_id.hex()


def _crc16_xmodem(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _require_text(value: object) -> str:
    if not isinstance(value, str):
        raise TonAddressError("ADDRESS_TYPE_INVALID")
    address = value.strip()
    if not address or address != value:
        raise TonAddressError("ADDRESS_INVALID")
    if not address.isascii():
        raise TonAddressError("ADDRESS_NON_ASCII")
    return address


def _strict_friendly_decode(value: str) -> bytes:
    if len(value) != 48:
        raise TonAddressError("ADDRESS_INVALID")
    try:
        return base64.b64decode(
            value.encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise TonAddressError("ADDRESS_BASE64_INVALID") from exc


def _parse_raw_address(value: str) -> ParsedAddress:
    match = _RAW_ADDRESS_PATTERN.fullmatch(value)
    if match is None:
        raise TonAddressError("ADDRESS_INVALID")
    workchain = int(match.group("workchain"))
    if not _INT32_MIN <= workchain <= _INT32_MAX:
        raise TonAddressError("WORKCHAIN_OUT_OF_RANGE")
    account_id = bytes.fromhex(match.group("account"))
    return ParsedAddress(
        workchain=workchain,
        account_id=account_id,
        raw=f"{workchain}:{account_id.hex()}",
    )


def _parse_friendly_address(value: str) -> ParsedAddress:
    raw = _strict_friendly_decode(value)
    if len(raw) != 36:
        raise TonAddressError("ADDRESS_INVALID")
    body = raw[:34]
    tag = body[0]
    if tag not in _ALLOWED_FRIENDLY_TAGS:
        raise TonAddressError("ADDRESS_TAG_INVALID")
    checksum = int.from_bytes(raw[34:], "big")
    wanted = _crc16_xmodem(body)
    if checksum != wanted:
        raise TonAddressError("ADDRESS_CHECKSUM_INVALID")
    workchain = int.from_bytes(body[1:2], "big", signed=True)
    account_id = body[2:34]
    return ParsedAddress(
        workchain=workchain,
        account_id=account_id,
        raw=f"{workchain}:{account_id.hex()}",
    )


def parse_ton_address(value: object) -> ParsedAddress:
    """Разобрать raw или friendly TON-адрес без неявных coercions."""

    address = _require_text(value)
    if ":" in address:
        return _parse_raw_address(address)
    return _parse_friendly_address(address)


def canonicalize_ton_address(address: str) -> str:
    """Вернуть единственный внутренний формат TON-адреса EFHC."""

    return parse_ton_address(address).raw


def to_friendly_ton_address(
    address: object,
    *,
    bounceable: bool = True,
    url_safe: bool = True,
    testnet: bool = False,
) -> str:
    """Построить корректную friendly форму для отображения/тестов."""

    parsed = parse_ton_address(address)
    if not -128 <= parsed.workchain <= 127:
        raise TonAddressError("FRIENDLY_WORKCHAIN_OUT_OF_RANGE")
    tag = 0x11 if bounceable else 0x51
    if testnet:
        tag |= 0x80
    body = (
        bytes([tag])
        + parsed.workchain.to_bytes(1, "big", signed=True)
        + parsed.account_id
    )
    checksum = _crc16_xmodem(body).to_bytes(2, "big")
    encoded = base64.b64encode(body + checksum).decode("ascii")
    if url_safe:
        encoded = encoded.replace("+", "-").replace("/", "_")
    return encoded


__all__ = [
    "ParsedAddress",
    "TonAddressError",
    "canonicalize_ton_address",
    "parse_ton_address",
    "to_friendly_ton_address",
]
