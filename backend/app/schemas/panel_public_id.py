"""Single API contract for the immutable eight-digit global panel identifier."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

PNL_PUBLIC_ID_PATTERN = re.compile(r"^PNL-[0-9]{8}$")


def is_valid_panel_public_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and PNL_PUBLIC_ID_PATTERN.fullmatch(value) is not None
        and value != "PNL-00000000"
    )


class PanelPublicIdMixin(BaseModel):
    """Reject missing, zero or legacy public identity in confirmed API rows."""

    public_id: str = Field(
        min_length=12,
        max_length=12,
        pattern=r"^PNL-[0-9]{8}$",
    )

    @field_validator("public_id")
    @classmethod
    def require_issued_number(cls, value: str) -> str:
        if not is_valid_panel_public_id(value):
            raise ValueError("Panel public_id is not an issued PNL.")
        return value
