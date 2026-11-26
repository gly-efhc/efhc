# backend/app/routes/user_routes.py
# ======================================================================
# EFHC Bot — пользовательские ручки.
# Профиль, балансы, подсказки для UI.
#
# Канон:
# - Только чтение. Денежные операции выполняют сервисы.
# - Все суммы наружу: Decimal с 8 знаками, округление вниз (d8).
# - Посекундные ставки генерации передаются фронту как источник истины.
# ======================================================================

from __future__ import annotations

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.sql_aliases_core import canon_schema
from app.core.system_locks import get_rate_base_d8, get_rate_vip_d8
from app.deps import d8, get_db
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.services.panels_service import (
    panels_summary as svc_panels_summary,
)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()
SCHEMA = canon_schema(
    getattr(settings, "DB_SCHEMA_CORE", "efhc_core"),
)
GEN_PER_SEC_BASE_KWH = get_rate_base_d8()
GEN_PER_SEC_VIP_KWH = get_rate_vip_d8()


class UserProfileOut(BaseModel):
    global_id: str | None = Field(
        None, description="Канонический global_id пользователя"
    )
    username: str | None = Field(
        None,
        description="Никнейм в Telegram (если есть)",
    )
    is_vip: bool = Field(
        ...,
        description="Флаг VIP статуса (по NFT)",
    )
    main_balance: str = Field(
        ...,
        description="Основной баланс EFHC (d8 строкой)",
    )
    bonus_balance: str = Field(
        ...,
        description="Бонусный баланс EFHC (d8 строкой)",
    )
    available_kwh: str = Field(
        ...,
        description="Доступная к обмену энергия (kWh)",
    )
    total_generated_kwh: str = Field(
        ...,
        description="Общая сгенерированная энергия (для рейтинга)",
    )
    gen_per_sec_base_kwh: str = Field(
        ...,
        description="Ставка без VIP, kWh/сек (канон)",
    )
    gen_per_sec_vip_kwh: str = Field(
        ...,
        description="Ставка VIP, kWh/сек (канон)",
    )


class PanelsSummaryOut(BaseModel):
    active_count: int
    total_generated_by_panels: str
    nearest_expire_at: str | None = None


router = APIRouter(prefix="/user", tags=["user"])


async def get_user_profile(
    db: AsyncSession,
    *,
    global_id: int,
) -> UserProfileOut:
    """Вернуть профиль по canonical account owner ``global_id``."""

    q = text(
        "\n".join(
            [
                "SELECT",
                "  u.global_id,",
                "  u.username,",
                "  COALESCE(u.is_vip, FALSE) AS is_vip,",
                "  COALESCE(u.main_balance, 0)::numeric AS main_balance,",
                "  COALESCE(u.bonus_balance, 0)::numeric AS bonus_balance,",
                "  COALESCE(u.available_kwh, 0)::numeric AS available_kwh,",
                "  COALESCE(u.total_generated_kwh, 0)::numeric",
                "    AS total_generated_kwh",
                f"FROM {SCHEMA}.users u",
                "WHERE u.global_id = :global_id",
                "LIMIT 1",
            ]
        )
    )
    rec = (
        await db.execute(q, {"global_id": int(global_id)})
    ).first()
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден.",
        )

    return UserProfileOut(
        global_id=f"{int(rec[0]):010d}",
        username=(str(rec[1]) if rec[1] is not None else None),
        is_vip=bool(rec[2]),
        main_balance=format(d8(rec[3]), "f"),
        bonus_balance=format(d8(rec[4]), "f"),
        available_kwh=format(d8(rec[5]), "f"),
        total_generated_kwh=format(d8(rec[6]), "f"),
        gen_per_sec_base_kwh=format(d8(GEN_PER_SEC_BASE_KWH), "f"),
        gen_per_sec_vip_kwh=format(d8(GEN_PER_SEC_VIP_KWH), "f"),
    )


@router.get(
    "/me",
    response_model=UserProfileOut,
    summary="Профиль текущего пользователя",
)
async def get_me(
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
) -> UserProfileOut:
    return await get_user_profile(db, global_id=owner.global_id)


@router.get(
    "/me/panels-summary",
    response_model=PanelsSummaryOut,
    summary="Сводка по панелям текущего пользователя",
)
async def get_my_panels_summary(
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
) -> PanelsSummaryOut:
    try:
        s = await svc_panels_summary(db, global_id=owner.global_id)
    except Exception as exc:
        logger.warning(
            "panels_summary failed global_id=%s: %s",
            owner.global_id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Временная ошибка. Повторите попытку.",
        ) from exc

    nearest = (
        s.nearest_expire_at.isoformat()
        if s.nearest_expire_at
        else None
    )
    return PanelsSummaryOut(
        active_count=int(s.active_count),
        total_generated_by_panels=format(d8(s.total_generated_by_panels), "f"),
        nearest_expire_at=nearest,
    )

