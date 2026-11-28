# backend/app/schemas/referral_schemas.py
# ----------------------------------------------------------------------
# Pydantic-схемы для раздела "Рефералы": витрины, курсоры, sync-ответы.
# ----------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, cast

from app.schemas.common_schemas import (
    CursorPage,
    EfhcBaseModel,
    IdempotencyContract,
    OkMeta,
    d8_str,
)
from app.schemas.id_schemas import ApiDatabaseGlobalId
from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)

TabName = Literal["active", "inactive"]


class ReferralRow(EfhcBaseModel):
    """Карточка реферала в списках "Активные/Неактивные"."""

    referee_global_id: str = Field(
        ...,
        description="global_id реферала как строка.",
    )
    username: str | None = Field(
        None,
        description="Никнейм (если есть).",
    )
    is_active: bool = Field(
        ...,
        description=(
            "Флаг Activ: True после первой активации панели навсегда; "
            "не зависит от текущего наличия панелей."
        ),
    )
    joined_at: datetime | None = Field(
        None,
        description="Когда реферал присоединился.",
    )
    became_active_at: datetime | None = Field(
        None,
        description="Когда реферал стал активным.",
    )
    panels_count: int = Field(
        ...,
        ge=0,
        description=(
            "Текущее число панелей, только для отображения. "
            "Не влияет на постоянный флаг Activ."
        ),
    )
    total_bonus_earned_by_referrer: str = Field(
        ...,
        description="Сколько бонусов начислено пригласившему (str, 8).",
    )

    @field_validator("total_bonus_earned_by_referrer", mode="before")
    def _q8(cls, v: Any) -> str:
        return cast(str, d8_str(v))

    model_config = ConfigDict(extra="ignore")


ActiveReferralsPage = CursorPage[ReferralRow]
InactiveReferralsPage = CursorPage[ReferralRow]


class MyReferralInfoOut(EfhcBaseModel):
    """Шапка раздела: код/ссылка + агрегаты."""

    meta: OkMeta = Field(default_factory=OkMeta)
    my_global_id: str = Field(
        ...,
        description="global_id текущего пользователя как строка.",
    )
    referral_code: str = Field(
        ...,
        description="Мой рефкод (стабилен).",
    )
    deep_link: str = Field(
        ...,
        description="Готовая deeplink-ссылка для приглашения.",
    )
    active_count: int = Field(
        ...,
        ge=0,
        description="Активных рефералов.",
    )
    inactive_count: int = Field(
        ...,
        ge=0,
        description="Неактивных рефералов.",
    )
    total_bonus_earned: str = Field(
        ...,
        description="Суммарно бонусов начислено мне (str, 8).",
    )
    last_bonus_at: datetime | None = Field(
        None,
        description="Когда последний раз начисляли бонус.",
    )

    @field_validator("total_bonus_earned", mode="before")
    def _q8(cls, v: Any) -> str:
        return cast(str, d8_str(v))

    model_config = ConfigDict(extra="ignore")


class ReferralsQueryIn(EfhcBaseModel):
    """Запрос списка рефералов для вкладки."""

    tab: TabName = Field(..., description="active | inactive.")
    next_cursor: str | None = Field(
        None,
        description="Курсор следующей страницы (base64).",
    )
    limit: int | None = Field(
        None,
        description="Размер страницы (1..200).",
    )

    model_config = ConfigDict(extra="ignore")


class ReferralsSyncOut(EfhcBaseModel):
    """Служебная синхронизация при открытии раздела."""

    meta: OkMeta = Field(default_factory=OkMeta)
    refreshed: int = Field(..., ge=0, description="Сколько освежено.")
    errors: int = Field(..., ge=0, description="Сколько ошибок.")
    note: str | None = Field(
        None,
        description="Короткая приметка ('ok'/'partial').",
    )

    model_config = ConfigDict(extra="ignore")


class ReferralClaimIn(IdempotencyContract):
    """Идемпотентный клейм (если такая механика появится)."""

    claim_code: str = Field(
        ...,
        description="Идентификатор клейма/условия.",
    )


class ReferralClaimOut(EfhcBaseModel):
    meta: OkMeta = Field(default_factory=OkMeta)
    claimed: bool = Field(
        ...,
        description="True, если клейм состоялся.",
    )
    detail: str | None = Field(
        None,
        description="Короткое пояснение (already_claimed/ok и т.п.).",
    )

    model_config = ConfigDict(extra="ignore")


class BonusRecordCreate(EfhcBaseModel):
    """Запись в журнал бонусов (НЕ баланс и НЕ банковская операция)."""

    global_id: ApiDatabaseGlobalId
    amount_efhc: Decimal
    kind: str = Field(..., description="Тип записи (например 'rank').")
    meta: dict[str, Any] | None = None

    model_config = ConfigDict(extra="ignore")
