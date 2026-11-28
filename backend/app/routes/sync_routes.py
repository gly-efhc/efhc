# backend/app/routes/sync_routes.py
# ======================================================================
# EFHC Bot — единый синхро-роут для фронта (сверка «на входе в экран»)
# ----------------------------------------------------------------------
# Назначение:
# • По запросу фронта (например, при открытии раздела) быстро «догоняет»
# посекундную генерацию конкретного пользователя (идемпотентно),
# затем возвращает единый снапшот для UI:
# - профиль и балансы,
# - сводку панелей,
# - предпросмотр обмена,
# - производную метрику gen_per_sec_effective (для анимации),
# - server_now и next_scheduler_eta_sec (когда тикнет планировщик).
#
# ИИ-защита / автономность:
# • Если догон генерации временно не удался (timeout/lock/network),
# мы НЕ роняем запрос — возвращаем актуальные на сейчас данные,
# параллельно ставим задачу в scheduler_task_log на авто-повтор
# ('resync_user_energy') и отдаём caller'у fallback_task_id.
# • Никаких денежных операций — только энергия (безопасно).
#
# Контракт:
# POST /sync/me?fresh=1
# fresh=1 — попытаться догнать генерацию перед сбором снапшота.
# Ответ: см. SyncSnapshotOut ниже.
# ======================================================================

from __future__ import annotations

import hashlib
from decimal import ROUND_DOWN, Decimal
from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.system_locks import get_rate_base_d8, get_rate_vip_d8
from app.deps import get_db
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.schemas.id_schemas import ApiLifetimeId
from app.services.energy_service import (
    generate_energy_for_user as svc_generate_for_user,
)
from app.services.exchange_service import (
    preview_exchange as svc_preview_exchange,
)
from app.services.panels_service import (
    panels_summary as svc_panels_summary,
)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()

EFHC_DECIMALS: int = int(getattr(settings, "EFHC_DECIMALS", 8) or 8)
Q8 = Decimal(1).scaleb(-EFHC_DECIMALS)

GEN_PER_SEC_BASE_KWH = get_rate_base_d8()
GEN_PER_SEC_VIP_KWH = get_rate_vip_d8()

TICK_SECONDS = 600  # плановый ритм планировщика 10 минут


def d8(x: Any) -> Decimal:
    """Привести Decimal к d8 с округлением вниз."""
    return Decimal(str(x)).quantize(Q8, rounding=ROUND_DOWN)


router = APIRouter(prefix="/sync", tags=["sync"])

# ----------------------------------------------------------------------
# Модели ответа
# ----------------------------------------------------------------------


class ProfilePart(BaseModel):
    global_id: str
    username: str | None
    is_vip: bool
    has_activ: bool
    main_balance: str
    bonus_balance: str
    available_kwh: str
    total_generated_kwh: str
    gen_per_sec_base: str
    gen_per_sec_vip: str


class PanelsPart(BaseModel):
    active_count: int
    total_generated_by_panels: str
    nearest_expire_at: str | None = None


class ExchangePart(BaseModel):
    ok: bool
    available_kwh: str
    max_exchangeable_kwh: str
    rate_kwh_to_efhc: str
    detail: str


class SyncMeta(BaseModel):
    server_now_iso: str = Field(..., description="Время сервера")
    generation_checkpoint_at_iso: str | None = Field(
        None,
        description="Точная UTC-граница подтверждённого начисления kWh",
    )
    gen_per_sec_effective: str = Field(
        ...,
        description="Скорость генерации (кВт·ч/сек)",
    )
    next_scheduler_eta_sec: int = Field(
        ...,
        description="Секунд до следующего тика планировщика",
    )
    fallback_task_id: ApiLifetimeId | None = Field(
        None,
        description="Если догон не удался — id постановки в очередь",
    )


class SyncSnapshotOut(BaseModel):
    profile: ProfilePart
    panels: PanelsPart
    exchange_preview: ExchangePart
    meta: SyncMeta


# ----------------------------------------------------------------------
# Вспомогательные функции
# ----------------------------------------------------------------------


async def _enqueue_resync_energy(
    db: AsyncSession,
    *,
    global_id: int,
    reason: str,
    minutes: int = 10,
) -> int:
    """Ставит задачу на догон генерации в scheduler_task_log."""
    row = await db.execute(
        text("""
            INSERT INTO efhc_core.scheduler_task_log
                (
                    task_name,
                    status,
                    error_text,
                    payload,
                    retry_time,
                    executed_at,
                    duration_sec,
                    created_at,
                    updated_at
                )
            VALUES
                ('resync_user_energy', 'queued', :err,
                 jsonb_build_object('global_id', :global_id),
                 NOW() + (:min || ' minutes')::interval,
                 NULL, NULL, NOW(), NOW())
            RETURNING id
            """),
        {
            "err": reason[:500],
            "global_id": int(global_id),
            "min": int(minutes),
        },
    )
    rid = row.fetchone()
    await db.commit()
    return int(rid[0]) if rid else 0


def _is_transient_error(e: Exception) -> bool:
    """Определяет временную (транзиентную) ошибку."""
    s = f"{type(e).__name__}: {e}".lower()
    signs = (
        "timeout",
        "temporar",
        "connection",
        "too many",
        "locked",
        "deadlock",
        "network",
        "server error",
    )
    return any(sign in s for sign in signs)


def _calc_next_tick_eta_sec(server_now_epoch: int) -> int:
    """
    Считает, сколько секунд до ближайшего «кратного 600» момента.
    Например, если TICK_SECONDS=600, то тики: 00:00, 00:10, 00:20, ...
    """
    r = server_now_epoch % TICK_SECONDS
    return 0 if r == 0 else (TICK_SECONDS - r)


# ----------------------------------------------------------------------
# POST /sync/me?fresh=1 — «жёсткая» сверка снапшота для UI
# ----------------------------------------------------------------------


async def _build_sync_snapshot(
    *,
    global_id: int,
    request: Request,
    response: Response,
    fresh: bool,
    db: AsyncSession,
) -> SyncSnapshotOut | Response:
    """Собрать provider-neutral snapshot canonical account owner."""

    fallback_task_id: int | None = None
    generation_checkpoint_iso: str | None = None
    if fresh:
        try:
            generation_result = await svc_generate_for_user(
                db, global_id=int(global_id)
            )
            generation_checkpoint_iso = generation_result.get("checkpoint_at")
        except Exception as exc:
            logger.warning(
                "sync: generate_for_user failed global_id=%s: %s",
                global_id,
                exc,
            )
            if _is_transient_error(exc):
                try:
                    reason = f"transient: {type(exc).__name__}: {exc}"
                    fallback_task_id = await _enqueue_resync_energy(
                        db,
                        global_id=int(global_id),
                        reason=reason,
                        minutes=10,
                    )
                except Exception as enqueue_error:
                    logger.warning(
                        "sync: enqueue resync failed: %s",
                        enqueue_error,
                    )

    row = await db.execute(
        text(
            """
            SELECT
              u.username,
              COALESCE(u.is_vip, FALSE) AS is_vip,
              EXISTS(
                SELECT 1
                FROM efhc_core.panels p
                WHERE p.global_id = u.global_id
                  AND p.is_active = TRUE
                  AND COALESCE(p.meta ->> 'protectively_voided', 'false') <> 'true'
                LIMIT 1
              ) AS has_activ,
              COALESCE(u.main_balance, 0) AS main_balance,
              COALESCE(u.bonus_balance, 0) AS bonus_balance,
              COALESCE(u.available_kwh, 0) AS available_kwh,
              COALESCE(u.total_generated_kwh, 0)
                AS total_generated_kwh,
              u.global_id
            FROM efhc_core.users u
            WHERE u.global_id = :global_id
            LIMIT 1
            """
        ),
        {"global_id": int(global_id)},
    )
    record = row.fetchone()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user_not_found",
        )

    is_vip = bool(record[1])
    has_activ = bool(record[2])
    gen_rate = (
        GEN_PER_SEC_VIP_KWH if is_vip else GEN_PER_SEC_BASE_KWH
    )
    profile = ProfilePart(
        global_id=f"{int(record[7]):010d}",
        username=record[0],
        is_vip=is_vip,
        has_activ=has_activ,
        main_balance=str(d8(record[3])),
        bonus_balance=str(d8(record[4])),
        available_kwh=str(d8(record[5])),
        total_generated_kwh=str(d8(record[6])),
        gen_per_sec_base=str(GEN_PER_SEC_BASE_KWH),
        gen_per_sec_vip=str(GEN_PER_SEC_VIP_KWH),
    )

    panel_summary = await svc_panels_summary(
        db,
        global_id=int(global_id),
    )
    active_count = int(panel_summary.active_count)
    gen_per_sec_effective = d8(Decimal(active_count) * gen_rate)
    nearest = panel_summary.nearest_expire_at
    panels = PanelsPart(
        active_count=active_count,
        total_generated_by_panels=str(
            d8(panel_summary.total_generated_by_panels)
        ),
        nearest_expire_at=(nearest.isoformat() if nearest else None),
    )

    exchange = await svc_preview_exchange(
        db,
        global_id=int(global_id),
    )
    exchange_preview = ExchangePart(
        ok=bool(exchange.ok),
        available_kwh=str(d8(exchange.available_kwh)),
        max_exchangeable_kwh=str(d8(exchange.max_exchangeable_kwh)),
        rate_kwh_to_efhc=str(d8(exchange.rate_kwh_to_efhc)),
        detail=exchange.detail,
    )

    now_row = await db.execute(
        text(
            "SELECT EXTRACT(EPOCH FROM NOW())::bigint, "
            "NOW()::timestamptz"
        )
    )
    now_pair = now_row.fetchone()
    if now_pair is None:
        raise HTTPException(status_code=500, detail="db_now_failed")
    epoch_value, now_timestamp = now_pair
    meta = SyncMeta(
        server_now_iso=str(now_timestamp.isoformat()),
        generation_checkpoint_at_iso=generation_checkpoint_iso,
        gen_per_sec_effective=str(gen_per_sec_effective),
        next_scheduler_eta_sec=int(
            _calc_next_tick_eta_sec(int(epoch_value))
        ),
        fallback_task_id=fallback_task_id,
    )
    output = SyncSnapshotOut(
        profile=profile,
        panels=panels,
        exchange_preview=exchange_preview,
        meta=meta,
    )

    try:
        payload = jsonable_encoder(output)
        etag = hashlib.sha256(str(payload).encode("utf-8")).hexdigest()
        response.headers["ETag"] = etag
        if request.headers.get("If-None-Match") == etag:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED)
    except Exception as exc:
        logger.warning(
            "sync: etag compute failed: %s",
            exc,
            exc_info=True,
        )
    return output


@router.post(
    "/me",
    response_model=SyncSnapshotOut,
    summary="Provider-neutral синхро-снапшот текущего account",
)
async def sync_current_owner_snapshot(
    request: Request,
    response: Response,
    fresh: bool = Query(
        True,
        description="Попытаться догнать генерацию перед snapshot",
    ),
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
) -> SyncSnapshotOut | Response:
    """Собрать snapshot через canonical global_id auth owner."""

    return await _build_sync_snapshot(
        global_id=int(owner.global_id),
        request=request,
        response=response,
        fresh=fresh,
        db=db,
    )
