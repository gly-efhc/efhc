"""Канонические тесты provider-independent типов ``global_id``."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import get_type_hints

import pytest
from app.identity import (
    ApiExternalGlobalId,
    ExternalGlobalId,
    GlobalId,
    GlobalIdDisplay,
    GlobalIdRequest,
    GlobalIdResponse,
    InvalidGlobalId,
    InvalidTelegramId,
    PydanticGlobalId,
    TelegramId,
    format_global_id,
    global_id_from_database,
    global_id_to_database,
    is_global_id,
    is_tg_id,
    parse_global_id,
    validate_global_id,
    validate_global_id_display,
    validate_tg_id,
)
from pydantic import TypeAdapter, ValidationError


def test_проверка_global_id_round_trip_preserves_external_width() -> None:
    value = validate_global_id(42)
    assert value == GlobalId(42)
    assert global_id_to_database(value) == 42
    assert global_id_from_database(42) == value
    assert format_global_id(value) == "0000000042"
    assert parse_global_id("0000000042") == value
    assert str(value) == "0000000042"


@pytest.mark.parametrize(
    "value",
    [0, -1, 10_000_000_000, True, 1.0, "42", TelegramId(42)],
)
def test_проверка_internal_global_id_rejects_invalid_or_provider_values(
    value: object,
) -> None:
    with pytest.raises(InvalidGlobalId):
        validate_global_id(value)


@pytest.mark.parametrize(
    "value",
    [
        "0000000000",
        "1",
        "000000001",
        "00000000001",
        "+000000001",
        " 0000000001",
        "0000000001 ",
        "00000000a1",
        "１２３４５６７８９０",
        1,
        GlobalId(1),
    ],
)
def test_проверка_external_global_id_rejects_noncanonical_values(
    value: object,
) -> None:
    with pytest.raises(InvalidGlobalId):
        parse_global_id(value)


def test_проверка_global_id_is_immutable_hashable_and_not_integer_alias() -> None:
    value = GlobalId(7)
    assert value != 7
    assert value != TelegramId(7)
    assert {value: "ok"}[GlobalId(7)] == "ok"
    with pytest.raises(FrozenInstanceError):
        value.value = 8  # type: ignore[misc]


def test_проверка_display_contract_is_ten_ascii_digits() -> None:
    value = GlobalIdDisplay("0000000001")
    assert validate_global_id_display(value) is value
    with pytest.raises(InvalidGlobalId):
        GlobalIdDisplay("0000000000")


def test_проверка_provider_and_global_identity_types_are_separate() -> None:
    telegram_id = validate_tg_id(123)
    assert isinstance(telegram_id, TelegramId)
    assert telegram_id.to_provider_value() == 123
    with pytest.raises(InvalidTelegramId):
        validate_tg_id(GlobalId(123))
    assert is_global_id(GlobalId(1))
    assert not is_global_id(TelegramId(1))
    assert is_tg_id(TelegramId(1))
    assert not is_tg_id(GlobalId(1))


def test_проверка_boundary_functions_expose_nominal_types() -> None:
    assert get_type_hints(format_global_id) == {
        "value": GlobalId,
        "return": GlobalIdDisplay,
    }
    assert get_type_hints(parse_global_id)["return"] is GlobalId
    assert get_type_hints(global_id_from_database)["return"] is GlobalId
    assert get_type_hints(global_id_to_database) == {
        "value": GlobalId,
        "return": int,
    }
    assert get_type_hints(validate_global_id)["return"] is GlobalId
    assert get_type_hints(validate_tg_id)["return"] is TelegramId


def test_проверка_pydantic_global_id_uses_string_wire_contract() -> None:
    adapter = TypeAdapter(PydanticGlobalId)
    value = adapter.validate_python("0000000042")
    assert value == GlobalId(42)
    assert adapter.dump_python(value) == "0000000042"
    assert adapter.dump_json(value) == b'"0000000042"'
    with pytest.raises(ValidationError):
        adapter.validate_python(42)
    with pytest.raises(ValidationError):
        adapter.validate_python(TelegramId(42))


def test_проверка_global_id_envelopes_use_canonical_field_only() -> None:
    request = GlobalIdRequest(global_id="0000000042")
    response = GlobalIdResponse.from_global_id(GlobalId(42))
    assert request.model_dump() == {"global_id": "0000000042"}
    assert response.model_dump() == {"global_id": "0000000042"}
    assert TypeAdapter(ApiExternalGlobalId).validate_python(
        "0000000042"
    ) == "0000000042"
    assert TypeAdapter(ExternalGlobalId).validate_python(
        "0000000042"
    ) == "0000000042"
