# backend/app/routes/admin_users_routes.py
# ======================================================================
# Админские HTTP-ручки «Пользователи» EFHC Bot.
#
# Назначение:
# - поиск пользователей по global_id (prefix search) для админ-панели;
# - read-only reverse lookup Global ID по связанному identity/provider identifier;
# - просмотр карточки пользователя;
# - безопасные админ-действия (VIP/активность/сброс TON-кошелька).
#
# Канон:
# - Global ID остаётся канонической идентичностью пользователя;
# - provider identifiers разрешаются только через bounded read-only exact lookup;
# - require_admin для всех ручек;
# - Idempotency-Key для любых изменений;
# - запись действия в admin_logs.
# ======================================================================

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.config_core import get_settings
from app.core.sql_aliases_core import canon_schema
from app.core.utils_core import format_decimal_str
from app.deps import d8, get_db, require_admin, require_admin_write
from app.identity.api_contract import ApiExternalGlobalId
from app.identity.types import global_id_to_database, parse_global_id
from app.schemas.profile_history_schemas import (
    ProfileHistoryItemOut,
    ProfileHistoryPageOut,
)
from app.services import panels_service, wallets_service
from app.services.admin.admin_logging import AdminLogger
from app.services.admin.admin_vip_nft_service import (
    check_all_vip_nft_now,
    check_user_vip_nft_now,
)
from app.services.profile_history_service import (
    PROFILE_HISTORY_PAGE_SIZE,
    ProfileHistoryRecord,
    list_profile_history_page,
)
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

S = get_settings()
SCHEMA_CORE: str = canon_schema(
    getattr(S, "DB_SCHEMA_CORE", "efhc_core") or "efhc_core",
)

router = APIRouter(prefix="/admin/users", tags=["admin:users"])


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _wire_history_item(item: ProfileHistoryRecord) -> ProfileHistoryItemOut:
    return ProfileHistoryItemOut(
        id=item.id,
        source=item.source,
        kind=item.kind,
        occurred_at=item.occurred_at.astimezone(UTC).isoformat(),
        status=item.status,
        direction=item.direction,
        balance_type=item.balance_type,
        amount_efhc=item.amount_efhc,
        amount_asset=item.amount_asset,
        asset=item.asset,
        reason=item.reason,
    )


class UserItem(BaseModel):
    global_id: ApiExternalGlobalId = Field(
        ...,
        description="global_id пользователя: десять ASCII-цифр",
    )
    username: str | None = None
    is_active: bool
    is_vip: bool
    ton_wallet: str | None = None
    main_balance: str
    bonus_balance: str
    available_kwh: str
    total_generated_kwh: str
    active_panels_count: int
    last_seen_at: str | None = None


class UserDetail(UserItem):
    created_at: str
    updated_at: str
    vip_checked_at: str | None = None
    vip_since: str | None = None
    last_sync_at: str | None = None


class ProviderIdentityResolveOut(BaseModel):
    global_id: ApiExternalGlobalId


class _PatchVipIn(BaseModel):
    is_vip: bool


class _PatchActiveIn(BaseModel):
    is_active: bool


class VipNftCheckOut(BaseModel):
    ok: bool
    state: str
    global_id: str
    is_vip: bool
    has_admin_nft: bool
    message: str
    checked_at: str | None = None


class VipNftBatchOut(BaseModel):
    ok: bool
    checked: int
    changed: int
    message: str


def _require_idempotency(idem: str | None) -> str:
    k = (idem or "").strip()
    if not k:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )
    return k


@router.get("/search", response_model=list[UserItem])
async def admin_users_search(
    q: str = Query("", max_length=64),
    limit: int = Query(50, ge=1, le=100),
    ctx=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserItem]:
    prefix = q.strip()
    is_empty = prefix == ""

    sql = text("""
        SELECT
            u.global_id,
            u.username,
            COALESCE(u.is_active, TRUE) AS is_active,
            COALESCE(u.is_vip, FALSE) AS is_vip,
            wallet.wallet_address AS ton_wallet,
            COALESCE(u.main_balance, 0) AS main_balance,
            COALESCE(u.bonus_balance, 0) AS bonus_balance,
            COALESCE(u.available_kwh, 0) AS available_kwh,
            COALESCE(u.total_generated_kwh, 0) AS total_generated_kwh,
            COALESCE(panel_stats.active_panels_count, 0) AS active_panels_count,
            u.last_seen_at
        FROM efhc_core.users u
        LEFT JOIN LATERAL (
            SELECT wb.wallet_address
            FROM efhc_core.wallet_bindings wb
            WHERE wb.global_id = u.global_id
              AND wb.is_active = TRUE
              AND wb.proof_verified = TRUE
            ORDER BY wb.is_primary DESC, wb.id ASC
            LIMIT 1
        ) wallet ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS active_panels_count
            FROM efhc_core.panels p
            WHERE p.global_id = u.global_id
              AND p.is_active = TRUE
              AND p.expires_at > CURRENT_TIMESTAMP
              AND COALESCE(p.meta ->> 'protectively_voided', 'false') <> 'true'
        ) panel_stats ON TRUE
        WHERE
            :is_empty = TRUE
            OR CAST(u.global_id AS TEXT) LIKE :pref
            OR COALESCE(u.username, '') ILIKE :username_pref
        ORDER BY u.global_id DESC
        LIMIT :limit
        """)
    r: Result = await db.execute(
        sql,
        {
            "is_empty": is_empty,
            "pref": f"{prefix}%",
            "username_pref": f"{prefix}%",
            "limit": int(limit),
        },
    )

    out: list[UserItem] = []
    for row in r.fetchall():
        out.append(
            UserItem(
                global_id=f"{int(row.global_id):010d}",
                username=row.username,
                is_active=bool(row.is_active),
                is_vip=bool(row.is_vip),
                ton_wallet=row.ton_wallet,
                main_balance=format_decimal_str(d8(row.main_balance)),
                bonus_balance=format_decimal_str(d8(row.bonus_balance)),
                available_kwh=format_decimal_str(d8(row.available_kwh)),
                total_generated_kwh=format_decimal_str(
                    d8(row.total_generated_kwh)
                ),
                active_panels_count=int(row.active_panels_count or 0),
                last_seen_at=_iso(row.last_seen_at),
            )
        )
    return out


@router.get(
    "/resolve-provider",
    response_model=ProviderIdentityResolveOut,
    summary="Найти Global ID по любому связанному идентификатору",
)
async def admin_users_resolve_provider(
    q: str = Query(..., min_length=1, max_length=512),
    ctx=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ProviderIdentityResolveOut:
    """Разрешить Global ID/username/provider subject/TON wallet в Global ID.

    Один exact-match запрос объединяет канонические identity sources.
    Provider metadata не раскрывается. При конфликте разных владельцев
    возвращается 409 вместо выбора произвольного пользователя.
    """

    subject = q.strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="identifier is required",
        )

    username = subject[1:] if subject.startswith("@") else subject
    global_id_value: int | None = None
    if len(subject) == 10 and subject.isascii() and subject.isdigit():
        try:
            global_id_value = global_id_to_database(parse_global_id(subject))
        except (TypeError, ValueError):
            global_id_value = None

    sql = text(
        """
        WITH identity_matches AS (
            SELECT u.global_id
              FROM efhc_core.users u
             WHERE :global_id_value IS NOT NULL
               AND u.global_id = :global_id_value
            UNION
            SELECT u.global_id
              FROM efhc_core.users u
             WHERE COALESCE(u.username, '') <> ''
               AND LOWER(u.username) = LOWER(:username)
            UNION
            SELECT ui.global_id
              FROM efhc_core.user_identities ui
             WHERE ui.provider_subject = :subject
               AND ui.status = 'active'
               AND ui.is_verified = TRUE
               AND ui.verified_at IS NOT NULL
            UNION
            SELECT wb.global_id
              FROM efhc_core.wallet_bindings wb
             WHERE wb.wallet_address = :subject
               AND wb.is_active = TRUE
               AND wb.proof_verified = TRUE
        )
        SELECT DISTINCT global_id
          FROM identity_matches
         ORDER BY global_id
         LIMIT 2
        """
    )
    result = await db.execute(
        sql,
        {
            "subject": subject,
            "username": username,
            "global_id_value": global_id_value,
        },
    )
    rows = [int(row.global_id) for row in result.fetchall()]

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    if len(rows) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="identity conflict",
        )

    return ProviderIdentityResolveOut(global_id=f"{rows[0]:010d}")


@router.post("/vip/check-all", response_model=VipNftBatchOut)
async def admin_users_check_all_vip_nft(
    ctx=Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> VipNftBatchOut:
    """Проверить VIP/NFT для всех пользователей с подключёнными кошельками."""

    result = await check_all_vip_nft_now(
        db,
        actor_global_id=int(ctx.global_id),
    )
    return VipNftBatchOut.model_validate(result)


@router.get("/{global_id}", response_model=UserDetail)
async def admin_users_get(
    global_id: ApiExternalGlobalId,
    ctx=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserDetail:
    sql = text("""
        SELECT
            u.global_id,
            u.username,
            COALESCE(u.is_active, TRUE) AS is_active,
            COALESCE(u.is_vip, FALSE) AS is_vip,
            u.vip_since,
            u.vip_checked_at,
            wallet.wallet_address AS ton_wallet,
            COALESCE(u.main_balance, 0) AS main_balance,
            COALESCE(u.bonus_balance, 0) AS bonus_balance,
            COALESCE(u.available_kwh, 0) AS available_kwh,
            COALESCE(u.total_generated_kwh, 0) AS total_generated_kwh,
            COALESCE(panel_stats.active_panels_count, 0) AS active_panels_count,
            u.last_seen_at,
            u.last_sync_at,
            u.created_at,
            u.updated_at
        FROM efhc_core.users u
        LEFT JOIN LATERAL (
            SELECT wb.wallet_address
            FROM efhc_core.wallet_bindings wb
            WHERE wb.global_id = u.global_id
              AND wb.is_active = TRUE
              AND wb.proof_verified = TRUE
            ORDER BY wb.is_primary DESC, wb.id ASC
            LIMIT 1
        ) wallet ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS active_panels_count
            FROM efhc_core.panels p
            WHERE p.global_id = u.global_id
              AND p.is_active = TRUE
              AND p.expires_at > CURRENT_TIMESTAMP
              AND COALESCE(p.meta ->> 'protectively_voided', 'false') <> 'true'
        ) panel_stats ON TRUE
        WHERE u.global_id = :global_id
        LIMIT 1
        """)
    r: Result = await db.execute(sql, {"global_id": int(global_id)})
    row = r.first()
    if not row:
        raise HTTPException(status_code=404, detail="user not found")

    return UserDetail(
        global_id=f"{int(row.global_id):010d}",
        username=row.username,
        is_active=bool(row.is_active),
        is_vip=bool(row.is_vip),
        ton_wallet=row.ton_wallet,
        main_balance=format_decimal_str(d8(row.main_balance)),
        bonus_balance=format_decimal_str(d8(row.bonus_balance)),
        available_kwh=format_decimal_str(d8(row.available_kwh)),
        total_generated_kwh=format_decimal_str(
            d8(row.total_generated_kwh)
        ),
        active_panels_count=int(row.active_panels_count or 0),
        last_seen_at=_iso(row.last_seen_at),
        last_sync_at=_iso(row.last_sync_at),
        created_at=_iso(row.created_at) or "",
        updated_at=_iso(row.updated_at) or "",
        vip_checked_at=_iso(row.vip_checked_at),
        vip_since=_iso(row.vip_since),
    )


@router.get(
    "/{global_id}/history",
    response_model=ProfileHistoryPageOut,
    summary="История выбранного пользователя по Global ID",
)
async def admin_users_history(
    global_id: ApiExternalGlobalId,
    cursor: str | None = Query(None, max_length=2048),
    ctx=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ProfileHistoryPageOut:
    """Читать тот же Unified History stream для выбранного Global ID."""

    await admin_users_get(global_id=global_id, ctx=ctx, db=db)
    try:
        page = await list_profile_history_page(
            db,
            global_id=int(global_id),
            cursor=cursor,
            page_size=PROFILE_HISTORY_PAGE_SIZE,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PROFILE_HISTORY_CURSOR_INVALID",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PROFILE_HISTORY_UNAVAILABLE",
        ) from exc
    return ProfileHistoryPageOut(
        items=[_wire_history_item(item) for item in page.items],
        next_cursor=page.next_cursor,
        page_size=PROFILE_HISTORY_PAGE_SIZE,
    )


@router.post(
    "/{global_id}/panels/activate",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def admin_users_activate_paid_panel(
    global_id: ApiExternalGlobalId,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
    ctx=Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Активировать одну панель по обычной платной логике пользователя."""

    idem = _require_idempotency(idempotency_key)
    try:
        await panels_service.activate_panel(
            db,
            global_id=int(global_id),
            qty=1,
            idempotency_key=idem,
            admin_actor_global_id=int(ctx.global_id),
            admin_reason="Admin активация панели",
        )
    except panels_service.PanelPurchaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return None


@router.post("/{global_id}/vip/check", response_model=VipNftCheckOut)
async def admin_users_check_vip_nft(
    global_id: ApiExternalGlobalId,
    ctx=Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> VipNftCheckOut:
    """Проверить фактическое владение VIP/Admin NFT прямо сейчас."""

    result = await check_user_vip_nft_now(
        db,
        global_id=int(global_id),
        actor_global_id=int(ctx.global_id),
    )
    return VipNftCheckOut.model_validate(result)


@router.patch("/{global_id}/vip", response_model=UserDetail)
async def admin_users_set_vip(
    global_id: ApiExternalGlobalId,
    payload: _PatchVipIn,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
    ctx=Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> UserDetail:
    """Compatibility route: ручной VIP заменён фактической NFT-проверкой.

    Заглушка ручного переключателя сохранена как API boundary, потому что
    старые клиенты могут ещё обращаться к этому пути. Значение ``is_vip``
    намеренно не записывается в БД: VIP определяется только владением NFT.
    """

    _require_idempotency(idempotency_key)
    _ = payload.is_vip
    await check_user_vip_nft_now(
        db,
        global_id=int(global_id),
        actor_global_id=int(ctx.global_id),
    )
    return await admin_users_get(global_id=global_id, ctx=ctx, db=db)


@router.patch("/{global_id}/active", response_model=UserDetail)
async def admin_users_set_active(
    global_id: ApiExternalGlobalId,
    payload: _PatchActiveIn,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
    ctx=Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> UserDetail:
    idem = _require_idempotency(idempotency_key)
    is_active = bool(payload.is_active)

    sql = text("""
        UPDATE efhc_core.users
        SET
            is_active = :is_active,
            updated_at = NOW() AT TIME ZONE 'UTC'
        WHERE global_id = :global_id
        """)
    res = await db.execute(
        sql,
        {"global_id": int(global_id), "is_active": is_active},
    )
    if res.__dict__.get("rowcount") == 0:
        raise HTTPException(status_code=404, detail="user not found")

    if not is_active:
        await db.execute(
            text(
                """
                UPDATE efhc_core.auth_sessions
                   SET status = 'revoked',
                       revoked_at = NOW() AT TIME ZONE 'UTC',
                       updated_at = NOW() AT TIME ZONE 'UTC'
                 WHERE global_id = :global_id
                   AND status = 'active'
                   AND revoked_at IS NULL
                """
            ),
            {"global_id": int(global_id)},
        )

    await AdminLogger.write(
        db,
        actor_global_id=int(ctx.global_id),
        action="set_active",
        entity="user",
        entity_id=int(global_id),
        details=f"is_active={is_active}; idem={idem}",
    )
    await db.commit()

    return await admin_users_get(global_id=global_id, ctx=ctx, db=db)


@router.post("/{global_id}/wallet/reset", status_code=204)
async def admin_users_reset_wallet(
    global_id: ApiExternalGlobalId,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
    ctx=Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> None:
    idem = _require_idempotency(idempotency_key)

    global_id_text = str(parse_global_id(global_id))
    stored_global_id = await db.scalar(
        text(
            "SELECT global_id FROM efhc_core.users "
            "WHERE global_id = :global_id LIMIT 1"
        ),
        {"global_id": global_id_to_database(parse_global_id(global_id_text))},
    )
    if stored_global_id is None:
        raise HTTPException(status_code=404, detail="user not found")

    bindings_reset = await wallets_service.admin_reset_wallet_bindings(
        db,
        global_id=global_id_text,
    )

    await AdminLogger.write(
        db,
        actor_global_id=int(ctx.global_id),
        action="reset_wallet",
        entity="user",
        entity_id=int(global_id),
        details=(
            f"wallet_bindings_deactivated={bindings_reset}; "
            f"idem={idem}"
        ),
    )
    await db.commit()
    return None
