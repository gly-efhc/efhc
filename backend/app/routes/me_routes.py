# КАНОН: этот модуль намеренно не имеет prefix.
# me_routes: маршруты /me смонтированы без /me-prefix; итоговые пути
# задаются include-слоем API router. Не добавлять prefix без
# согласования
# с архитектором EFHC Bot.
# backend/app/routes/me_routes.py
# =====================================================================
# GET /v1/me — локальный путь роутера.
# Финальный runtime путь задаётся через API_PREFIX.
# Безопасная витрина профиля для Telegram WebApp.
# • Идентификация: verified server-side auth session (initData/заголовки).
# • Денежных операций нет.
# • Если пользователя нет — маршрут завершается fail-closed; создание
#   допускается только через first-creation onboarding в /start.
# =====================================================================

from __future__ import annotations

from datetime import timedelta

from app.core.logging_core import get_logger
from app.deps import get_db
from app.identity.financial_owner import FinancialReadOwner
from app.identity.financial_read_dependency import (
    get_financial_read_owner,
)
from app.lib.time import utcnow
from app.models.user_models import User
from app.schemas.id_schemas import ApiLifetimeId
from app.schemas.outcome_schemas import WithdrawOutcomeBundleSchema
from app.services.nft_check_service import check_user_vip_once
from app.services.outcome_service import get_withdraw_outcome_bundle
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

router = APIRouter(tags=["me"])

@router.get("/v1/me")
async def me(
    db: AsyncSession = Depends(get_db),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> dict:
    user = (
        await db.execute(
            select(User).where(
                User.global_id == int(owner.global_id)
            )
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user_not_onboarded",
        )

    try:
        now = utcnow()
        last_checked = getattr(user, "vip_checked_at", None)
        stale = (last_checked is None) or (
            now - last_checked > timedelta(seconds=600)
        )
        if stale:
            await check_user_vip_once(
                db,
                global_id=int(user.global_id),
                force_refresh=False,
            )
            await db.commit()
            await db.refresh(user)
    except Exception:
        logger.warning("me: vip refresh failed", exc_info=True)

    return {
        "global_id": (
            f"{int(user.global_id):010d}"
            if getattr(user, "global_id", None) is not None
            else None
        ),
        "username": user.username,
        "vip": bool(user.is_vip),
    }


@router.get(
    "/v1/me/withdraw-outcomes/{request_id}",
    response_model=WithdrawOutcomeBundleSchema,
)
async def me_withdraw_outcome(
    request_id: ApiLifetimeId,
    db: AsyncSession = Depends(get_db),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> WithdrawOutcomeBundleSchema:
    bundle = await get_withdraw_outcome_bundle(
        db,
        request_id=int(request_id),
        global_id=owner.global_id,
    )
    promo = None
    if bundle.promo is not None:
        promo = {
            "enabled": bundle.promo.enabled,
            "key": bundle.promo.key,
            "title": bundle.promo.title,
            "body": bundle.promo.body,
            "cta_label": bundle.promo.cta_label,
            "cta_url": bundle.promo.cta_url,
            "source": bundle.promo.source,
        }
    return WithdrawOutcomeBundleSchema(
        request_id=bundle.request_id,
        global_id=f"{int(bundle.global_id):010d}",
        outcome_kind=bundle.outcome_kind,
        locale=bundle.locale,
        comment={
            "text": bundle.comment.text,
            "template_key": bundle.comment.template_key,
            "source": bundle.comment.source,
            "locale": bundle.comment.locale,
            "manual_override_used": (
                bundle.comment.manual_override_used
            ),
            "auto_translated": bundle.comment.auto_translated,
        },
        promo=promo,
        top_zone_enabled=bool(bundle.promo),
        metadata=bundle.metadata,
    )
