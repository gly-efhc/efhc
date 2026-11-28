# backend/app/schemas/tasks_schemas.py
# ----------------------------------------------------------------------
# Pydantic-схемы для задач и отправок выполнения.
# ----------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.identity.api_contract import ApiExternalGlobalId
from app.schemas.common_schemas import (
    CursorPage,
    EfhcBaseModel,
    IdempotencyContract,
    OkMeta,
    d8_str,
)
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import (
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
)


class TaskBase(EfhcBaseModel):
    """Базовое описание задания (create/update)."""

    code: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    type: str = Field("custom", min_length=1, max_length=50)
    active: bool = True

    bonus_efhc: Decimal = Field(
        Decimal("0.00000000"),
        serialization_alias="bonus_efhc",
    )
    price_usd_hint: Decimal | None = None

    limit_per_user: int = Field(1, ge=0)
    total_limit: int | None = Field(None, ge=0)

    proof_type: str | None = Field(None, max_length=50)
    proof_hint: str | None = Field(None, max_length=255)

    model_config = ConfigDict(extra="ignore")


class TaskCreate(TaskBase):
    """Создание задания (админ)."""


class TaskUpdate(EfhcBaseModel):
    """Изменение задания (админ). Все поля опциональны."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    type: str | None = Field(None, min_length=1, max_length=50)
    active: bool | None = None
    bonus_efhc: Decimal | None = Field(
        None,
        serialization_alias="bonus_efhc",
    )
    price_usd_hint: Decimal | None = None
    limit_per_user: int | None = Field(None, ge=0)
    total_limit: int | None = Field(None, ge=0)
    proof_type: str | None = Field(None, max_length=50)
    proof_hint: str | None = Field(None, max_length=255)

    model_config = ConfigDict(extra="ignore")


class TaskOut(EfhcBaseModel):
    """Витринная карточка задания (денежные поля: str, 8)."""

    id: ApiLifetimeId
    code: str
    title: str
    description: str | None = None
    type: str
    active: bool

    bonus_efhc: str
    price_usd_hint: str | None = None

    limit_per_user: int
    total_limit: int | None = None

    performed_count: int
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "bonus_efhc",
        "price_usd_hint",
        mode="before",
    )
    def _q8(cls, v: Any) -> str | None:
        if v is None:
            return None
        return str(d8_str(v))

    model_config = ConfigDict(extra="ignore")


TasksPage = CursorPage[TaskOut]


class TasksQueryIn(EfhcBaseModel):
    """Параметры курсорного листинга задач."""

    next_cursor: str | None = Field(
        None,
        description="Курсор следующей страницы (base64).",
    )
    limit: int | None = Field(
        None,
        ge=1,
        le=200,
        description="Размер страницы (1..200).",
    )
    only_active: bool | None = Field(
        None,
        description="Если true - только активные задания.",
    )

    model_config = ConfigDict(extra="ignore")


class SubmissionCreate(EfhcBaseModel):
    """Пользователь отправляет выполнение задания."""

    proof_text: str | None = None
    proof_url: HttpUrl | None = None

    model_config = ConfigDict(extra="ignore")


class SubmissionOut(EfhcBaseModel):
    """Витринная карточка отправки (bonus_amount_efhc - str, 8)."""

    id: ApiLifetimeId
    task_id: ApiLifetimeId
    global_id: ApiExternalGlobalId
    status: str
    proof_text: str | None = None
    proof_url: str | None = None

    bonus_amount_efhc: str
    paid: bool
    paid_tx_id: ApiLifetimeId | None = None
    moderator_global_id: ApiExternalGlobalId | None = None

    created_at: datetime
    updated_at: datetime

    @field_validator("bonus_amount_efhc", mode="before")
    def _q8(cls, v: Any) -> str:
        return str(d8_str(v))

    model_config = ConfigDict(extra="ignore")


SubmissionsPage = CursorPage[SubmissionOut]


class SubmissionsQueryIn(EfhcBaseModel):
    """Параметры курсорного листинга отправок."""

    next_cursor: str | None = Field(
        None,
        description="Курсор следующей страницы (base64).",
    )
    limit: int | None = Field(
        None,
        ge=1,
        le=200,
        description="Размер страницы (1..200).",
    )
    status: str | None = Field(None, max_length=32)

    model_config = ConfigDict(extra="ignore")


class SubmissionModerateIn(IdempotencyContract):
    """Решение по заявке (approve=True -> выплата через банк)."""

    approve: bool
    moderator_global_id: ApiExternalGlobalId
    bonus_override_efhc: Decimal | None = Field(
        None,
        serialization_alias="bonus_override_efhc",
    )


class TasksSyncOut(EfhcBaseModel):
    """Служебная синхронизация витрины задач."""

    meta: OkMeta = Field(default_factory=OkMeta)
    refreshed: int = Field(..., ge=0, description="Сколько освежено.")
    errors: int = Field(..., ge=0, description="Сколько ошибок.")
    note: str | None = Field(
        None,
        description="Короткий комментарий ('ok'/'partial').",
    )

    model_config = ConfigDict(extra="ignore")


class SubmissionsSyncOut(EfhcBaseModel):
    """Служебная синхронизация витрины отправок."""

    meta: OkMeta = Field(default_factory=OkMeta)
    refreshed: int = Field(..., ge=0)
    errors: int = Field(..., ge=0)
    note: str | None = None

    model_config = ConfigDict(extra="ignore")
