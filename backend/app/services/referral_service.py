"""Provider-neutral реферальный сервис EFHC.

Канонический ``global_id`` является владельцем business-операций.
Канон: канонический global_id используется после provider resolution.
``tg_id`` допустим только на Telegram ingress и как historical
idempotency/provider metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.crud.referrals_crud import activate_referral
from app.deps import d8
from app.identity.account_registration import (
    AccountRegistrationError,
    NewAccountRequest,
    create_new_account,
)
from app.identity.auth_provider import AuthProvider
from app.identity.telegram_channel import (
    resolve_verified_telegram_subject,
)
from app.identity.user_identities_storage_contract import (
    USER_IDENTITY_DEFAULT_TENANT,
    UserIdentityStatus,
)
from app.models.identity_models import UserIdentity
from app.models.referral_codes_models import ReferralCode
from app.models.referral_models import ReferralLink
from app.models.transactions_models import EfhcTransferLog
from app.models.user_models import User
from app.services.transactions_service import (
    credit_user_bonus_from_bank_nocommit,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()

REF_BONUS_PER_ACTIVE_UNIT = d8(
    getattr(settings, "REFERRAL_BONUS_PER_ACTIVE_UNIT", "0.1") or "0.1"
)
REF_MAX_ACTIVE_FOR_UNIT_BONUS = int(
    getattr(settings, "REFERRAL_MAX_ACTIVE_FOR_UNIT_BONUS", 10_000)
    or 10_000
)
REFERRAL_BONUS_ASSET = "EFHCb"
BOT_USERNAME = str(getattr(settings, "BOT_USERNAME", "") or "")


@dataclass(frozen=True)
class ReferralLevelConfig:
    level: int
    required_active: int
    bonus: Decimal


# Экономика первого уровня: 10 × 0.1 + 1 = 2 EFHCb.
REF_LEVELS: tuple[ReferralLevelConfig, ...] = (
    ReferralLevelConfig(1, 10, d8("1")),
    ReferralLevelConfig(2, 100, d8("10")),
    ReferralLevelConfig(3, 1000, d8("100")),
    ReferralLevelConfig(4, 3000, d8("300")),
    ReferralLevelConfig(5, 10000, d8("1000")),
)


@dataclass(frozen=True)
class ReferralLevelStep:
    level: int
    required_active: int
    level_bonus: Decimal
    direct_bonus_total: Decimal
    cumulative_level_bonus: Decimal
    cumulative_total_reward: Decimal


def get_referral_level_steps() -> tuple[ReferralLevelStep, ...]:
    cumulative = d8("0")
    steps: list[ReferralLevelStep] = []
    for cfg in REF_LEVELS:
        cumulative = d8(cumulative + cfg.bonus)
        direct = d8(
            REF_BONUS_PER_ACTIVE_UNIT * Decimal(cfg.required_active)
        )
        steps.append(
            ReferralLevelStep(
                level=cfg.level,
                required_active=cfg.required_active,
                level_bonus=cfg.bonus,
                direct_bonus_total=direct,
                cumulative_level_bonus=cumulative,
                cumulative_total_reward=d8(direct + cumulative),
            )
        )
    return tuple(steps)


@dataclass
class ReferralItem:
    child_global_id: int
    global_id: int
    username: str | None
    joined_at: datetime
    is_active: bool
    total_generated_kwh: Decimal
    panels_count: int
    invited_at: datetime
    activated_at: datetime | None


CursorTuple = tuple[str, int]


@dataclass
class ReferralStats:
    inviter_global_id: int
    total_referrals: int
    active_referrals: int
    level: int
    next_level: int | None
    current_level_min: int
    next_level_min: int | None
    refs_to_next: int
    progress: float
    referral_code: str
    referral_link: str | None


@dataclass
class ReferralPageStats:
    inviter_global_id: int
    bonus_balance: Decimal
    referrals_bonus_total: Decimal
    total_referrals: int
    active_referrals: int
    inactive_referrals: int
    level: int
    current_level_min: int
    next_level: int | None
    next_level_min: int | None
    refs_to_next: int
    progress: float
    unit_bonus_per_active: Decimal
    max_active_for_unit_bonus: int
    bonus_asset: str
    full_cycle_direct_bonus: Decimal
    full_cycle_level_bonus: Decimal
    full_cycle_total_bonus: Decimal
    level_steps: tuple[ReferralLevelStep, ...]
    referral_code: str
    referral_link: str | None


@dataclass
class ReferralsPage:
    items: list[ReferralItem]
    next_cursor: str | None


@dataclass
class ReferralCounters:
    total: int
    active: int
    inactive: int


def _parse_cursor_str(cursor: str | None) -> CursorTuple | None:
    if not cursor:
        return None
    raw = str(cursor).strip()
    sep = "|" if "|" in raw else ("," if "," in raw else None)
    if not sep:
        return None
    left, right = raw.split(sep, 1)
    try:
        return left.strip(), int(right.strip())
    except (TypeError, ValueError):
        return None


def _format_cursor(cursor: CursorTuple | None) -> str | None:
    if cursor is None:
        return None
    return f"{cursor[0]}|{int(cursor[1])}"


def _normalize_cursor(
    cursor: CursorTuple | None,
) -> tuple[datetime | None, int | None]:
    if cursor is None:
        return None, None
    raw_ts, raw_id = cursor
    try:
        return datetime.fromisoformat(raw_ts), int(raw_id)
    except (TypeError, ValueError):
        return None, None


def _next_cursor(items: list[ReferralItem]) -> CursorTuple | None:
    if not items:
        return None
    last = items[-1]
    return last.invited_at.isoformat(), int(last.global_id)


def build_referral_link(code: str) -> str:
    username = BOT_USERNAME.lstrip("@").strip()
    return f"https://t.me/{username}?start=ref_{code}"


def _generate_referral_code(length: int = 10) -> str:
    import secrets
    import string

    alphabet = string.ascii_uppercase + string.digits
    size = max(6, min(32, int(length)))
    return "".join(secrets.choice(alphabet) for _ in range(size))


SQL_LIST_REFERRALS_GLOBAL = """
WITH ref AS (
    SELECT
        rl.invitee_global_id AS ref_global,
        rl.created_at AS invited_at,
        rl.activated_at AS activated_at
    FROM efhc_core.referral_links rl
    WHERE rl.inviter_global_id = :inviter_global_id
),
panel_counts AS (
    SELECT p.global_id, COUNT(p.id)::BIGINT AS panels_count
    FROM efhc_core.panels p
    INNER JOIN ref ON ref.ref_global = p.global_id
    WHERE COALESCE(p.meta ->> 'protectively_voided', 'false') <> 'true'
    GROUP BY p.global_id
)
SELECT
    u.global_id AS child_global_id,
    u.global_id AS global_id,
    u.username,
    u.created_at,
    (ref.activated_at IS NOT NULL) AS is_active,
    COALESCE(u.total_generated_kwh, 0),
    COALESCE(pc.panels_count, 0),
    ref.invited_at,
    ref.activated_at
FROM ref
INNER JOIN efhc_core.users u ON u.global_id = ref.ref_global
LEFT JOIN panel_counts pc ON pc.global_id = ref.ref_global
WHERE (
    CAST(:cursor_ts AS TIMESTAMPTZ) IS NULL
    OR (ref.invited_at, u.global_id) < (
        CAST(:cursor_ts AS TIMESTAMPTZ),
        CAST(:cursor_id AS BIGINT)
    )
)
AND (
    (CAST(:want_active AS BOOLEAN) AND ref.activated_at IS NOT NULL)
    OR (
        NOT CAST(:want_active AS BOOLEAN)
        AND ref.activated_at IS NULL
    )
)
ORDER BY ref.invited_at DESC, u.global_id DESC
LIMIT CAST(:fetch_limit AS INTEGER)
"""


async def _svc_list_referrals_global(
    db: AsyncSession,
    *,
    inviter_global_id: int,
    limit: int,
    cursor: CursorTuple | None,
    want_active: bool,
) -> tuple[list[ReferralItem], CursorTuple | None]:
    safe_limit = max(1, min(int(limit), 200))
    cursor_ts, cursor_id = _normalize_cursor(cursor)
    rows = await db.execute(
        text(SQL_LIST_REFERRALS_GLOBAL),
        {
            "inviter_global_id": int(inviter_global_id),
            "cursor_ts": cursor_ts,
            "cursor_id": cursor_id,
            "want_active": bool(want_active),
            "fetch_limit": safe_limit + 1,
        },
    )
    fetched = rows.fetchall()
    page_rows = fetched[:safe_limit]
    items = [
        ReferralItem(
            child_global_id=int(row[0]),
            global_id=int(row[1]),
            username=(str(row[2]) if row[2] is not None else None),
            joined_at=row[3],
            is_active=bool(row[4]),
            total_generated_kwh=Decimal(str(row[5])),
            panels_count=int(row[6]),
            invited_at=row[7],
            activated_at=row[8],
        )
        for row in page_rows
    ]
    next_cursor = (
        _next_cursor(items) if len(fetched) > safe_limit else None
    )
    return items, next_cursor


async def list_active_referrals_global(
    db: AsyncSession,
    *,
    parent_global_id: int,
    limit: int = 100,
    cursor: str | None = None,
) -> ReferralsPage:
    items, next_cursor = await _svc_list_referrals_global(
        db,
        inviter_global_id=int(parent_global_id),
        limit=int(limit),
        cursor=_parse_cursor_str(cursor),
        want_active=True,
    )
    return ReferralsPage(items, _format_cursor(next_cursor))


async def list_inactive_referrals_global(
    db: AsyncSession,
    *,
    parent_global_id: int,
    limit: int = 100,
    cursor: str | None = None,
) -> ReferralsPage:
    items, next_cursor = await _svc_list_referrals_global(
        db,
        inviter_global_id=int(parent_global_id),
        limit=int(limit),
        cursor=_parse_cursor_str(cursor),
        want_active=False,
    )
    return ReferralsPage(items, _format_cursor(next_cursor))


async def _count_total_referrals(
    db: AsyncSession,
    inviter_global_id: int,
) -> int:
    value = await db.scalar(
        select(func.count(ReferralLink.id)).where(
            ReferralLink.inviter_global_id == int(inviter_global_id)
        )
    )
    return int(value or 0)


async def _count_active_referrals(
    db: AsyncSession,
    inviter_global_id: int,
) -> int:
    value = await db.scalar(
        select(func.count(ReferralLink.id)).where(
            ReferralLink.inviter_global_id == int(inviter_global_id),
            ReferralLink.activated_at.isnot(None),
        )
    )
    return int(value or 0)



async def get_counters_global(
    db: AsyncSession,
    *,
    parent_global_id: int,
) -> ReferralCounters:
    total = await _count_total_referrals(db, int(parent_global_id))
    active = await _count_active_referrals(db, int(parent_global_id))
    return ReferralCounters(total, active, max(total - active, 0))


def _compute_level_and_progress(
    active_refs: int,
) -> tuple[int, int, int | None, int | None, int, float]:
    active = max(0, int(active_refs))
    current_level = 0
    current_min = 0
    for cfg in REF_LEVELS:
        if active >= cfg.required_active:
            current_level = cfg.level
            current_min = cfg.required_active
        else:
            break
    next_cfg = next(
        (cfg for cfg in REF_LEVELS if cfg.required_active > active),
        None,
    )
    if next_cfg is None:
        return current_level, current_min, None, None, 0, 1.0
    refs_to_next = max(0, next_cfg.required_active - active)
    span = max(1, next_cfg.required_active - current_min)
    progress = min(1.0, max(0.0, (active - current_min) / span))
    return (
        current_level,
        current_min,
        next_cfg.level,
        next_cfg.required_active,
        refs_to_next,
        progress,
    )


async def ensure_referral_codes_table(db: AsyncSession) -> None:
    del db


async def get_or_create_referral_code(
    db: AsyncSession,
    *,
    inviter_global_id: int,
) -> str:
    gid = int(inviter_global_id)
    owner = await db.scalar(
        select(User.global_id).where(User.global_id == gid).limit(1)
    )
    if owner is None:
        raise ValueError("referral owner not found")
    existing = await db.scalar(
        select(ReferralCode.code)
        .where(ReferralCode.inviter_global_id == gid)
        .limit(1)
    )
    if existing:
        return str(existing)
    for _ in range(10):
        code = _generate_referral_code()
        try:
            async with db.begin_nested():
                db.add(
                    ReferralCode(
                        code=code,
                        inviter_global_id=gid,
                    )
                )
                await db.flush()
            return code
        except IntegrityError:
            existing = await db.scalar(
                select(ReferralCode.code)
                .where(ReferralCode.inviter_global_id == gid)
                .limit(1)
            )
            if existing:
                return str(existing)
    raise RuntimeError("failed_to_generate_referral_code")


async def get_referral_stats(
    db: AsyncSession,
    *,
    inviter_global_id: int,
) -> ReferralStats:
    total = await _count_total_referrals(db, int(inviter_global_id))
    active = await _count_active_referrals(db, int(inviter_global_id))
    level_data = _compute_level_and_progress(active)
    code = await get_or_create_referral_code(
        db,
        inviter_global_id=int(inviter_global_id),
    )
    return ReferralStats(
        inviter_global_id=int(inviter_global_id),
        total_referrals=total,
        active_referrals=active,
        level=level_data[0],
        current_level_min=level_data[1],
        next_level=level_data[2],
        next_level_min=level_data[3],
        refs_to_next=level_data[4],
        progress=level_data[5],
        referral_code=code,
        referral_link=(
            build_referral_link(code) if BOT_USERNAME else None
        ),
    )


async def _get_user_bonus_balance(
    db: AsyncSession,
    *,
    inviter_global_id: int,
) -> Decimal:
    value = await db.scalar(
        select(User.bonus_balance)
        .where(User.global_id == int(inviter_global_id))
        .limit(1)
    )
    result: Decimal = d8(value or 0)
    return result


async def _sum_referrals_bonus_total(
    db: AsyncSession,
    *,
    inviter_global_id: int,
) -> Decimal:
    value = await db.scalar(
        select(
            func.coalesce(func.sum(EfhcTransferLog.amount), 0)
        ).where(
            EfhcTransferLog.global_id == int(inviter_global_id),
            EfhcTransferLog.direction == "credit",
            EfhcTransferLog.balance_type == "bonus",
            EfhcTransferLog.reason.in_(
                ["referral_active_unit", "referral_level_bonus"]
            ),
        )
    )
    result: Decimal = d8(value or 0)
    return result


async def get_referrals_page_stats_global(
    db: AsyncSession,
    *,
    inviter_global_id: int,
) -> ReferralPageStats:
    base = await get_referral_stats(
        db,
        inviter_global_id=int(inviter_global_id),
    )
    balance = await _get_user_bonus_balance(
        db,
        inviter_global_id=int(inviter_global_id),
    )
    total_bonus = await _sum_referrals_bonus_total(
        db,
        inviter_global_id=int(inviter_global_id),
    )
    steps = get_referral_level_steps()
    full_cycle = steps[-1]
    return ReferralPageStats(
        inviter_global_id=int(inviter_global_id),
        bonus_balance=balance,
        referrals_bonus_total=total_bonus,
        total_referrals=base.total_referrals,
        active_referrals=base.active_referrals,
        inactive_referrals=max(
            base.total_referrals - base.active_referrals,
            0,
        ),
        level=base.level,
        current_level_min=base.current_level_min,
        next_level=base.next_level,
        next_level_min=base.next_level_min,
        refs_to_next=base.refs_to_next,
        progress=base.progress,
        unit_bonus_per_active=REF_BONUS_PER_ACTIVE_UNIT,
        max_active_for_unit_bonus=REF_MAX_ACTIVE_FOR_UNIT_BONUS,
        bonus_asset=REFERRAL_BONUS_ASSET,
        full_cycle_direct_bonus=full_cycle.direct_bonus_total,
        full_cycle_level_bonus=full_cycle.cumulative_level_bonus,
        full_cycle_total_bonus=full_cycle.cumulative_total_reward,
        level_steps=steps,
        referral_code=base.referral_code,
        referral_link=base.referral_link,
    )


async def ensure_consistency(
    db: AsyncSession,
    *,
    parent_global_id: int,
) -> None:
    await get_or_create_referral_code(
        db,
        inviter_global_id=int(parent_global_id),
    )


@dataclass(frozen=True)
class ReferralOnboardingResult:
    created: bool
    referral_attached: bool
    reason: str
    inviter_global_id: int | None = None


class ReferralOnboardingRejected(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def _create_bot_user_identity(
    db: AsyncSession,
    *,
    global_id: int,
    tg_id: int,
    verified_at: datetime,
) -> None:
    db.add(
        UserIdentity(
            global_id=int(global_id),
            provider=AuthProvider.TELEGRAM.value,
            provider_tenant=USER_IDENTITY_DEFAULT_TENANT,
            provider_subject=str(int(tg_id)),
            status=UserIdentityStatus.ACTIVE.value,
            is_primary=True,
            is_verified=True,
            verified_at=verified_at,
            provider_metadata={
                "source": "telegram_bot_start",
                "cycle": 1685,
            },
        )
    )
    await db.flush()


async def _tg_identity_exists_after_storage_conflict(
    db: AsyncSession,
    *,
    tg_id: int,
) -> bool:
    existing = await db.scalar(
        select(UserIdentity.id)
        .where(
            UserIdentity.provider == AuthProvider.TELEGRAM.value,
            UserIdentity.provider_tenant == USER_IDENTITY_DEFAULT_TENANT,
            UserIdentity.provider_subject == str(int(tg_id)),
            UserIdentity.status == UserIdentityStatus.ACTIVE.value,
            UserIdentity.is_verified.is_(True),
        )
        .limit(1)
    )
    return existing is not None


async def onboard_user_at_first_creation_in_transaction(
    db: AsyncSession,
    *,
    tg_id: int,
    username: str | None = None,
    start_param: str | None = None,
    created_at: datetime | None = None,
) -> ReferralOnboardingResult:
    """Создать Telegram account внутри транзакции вызывающей стороны.

    Функция не завершает root transaction через commit/rollback.
    Recoverable storage conflicts изолируются savepoint-ом.
    """
    user_tg_id = int(tg_id)
    # Отсутствующую строку нельзя защитить через ``FOR UPDATE``.
    # Advisory xact lock остаётся собственностью root transaction caller.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:provider_subject)"),
        {"provider_subject": user_tg_id},
    )
    existing = await db.scalar(
        select(UserIdentity.id)
        .where(
            UserIdentity.provider == AuthProvider.TELEGRAM.value,
            UserIdentity.provider_tenant == USER_IDENTITY_DEFAULT_TENANT,
            UserIdentity.provider_subject == str(user_tg_id),
            UserIdentity.status == UserIdentityStatus.ACTIVE.value,
            UserIdentity.is_verified.is_(True),
        )
        .limit(1)
        .with_for_update()
    )
    if existing is not None:
        return ReferralOnboardingResult(
            created=False,
            referral_attached=False,
            reason="existing_user_locked",
        )

    registration = None
    inviter_global_id: int | None = None
    try:
        async with db.begin_nested():
            registration = await create_new_account(
                db,
                NewAccountRequest(
                    provider=AuthProvider.TELEGRAM,
                    tg_id=user_tg_id,
                    referral_start_param=start_param,
                    username=username,
                ),
            )
            await _create_bot_user_identity(
                db,
                global_id=registration.global_id.value,
                tg_id=user_tg_id,
                verified_at=created_at or datetime.now(tz=UTC),
            )
            if registration.referral_attached:
                link = await db.scalar(
                    select(ReferralLink)
                    .where(
                        ReferralLink.invitee_global_id
                        == registration.global_id.value
                    )
                    .limit(1)
                )
                if link is None:
                    raise RuntimeError("referral_link_not_created")
                inviter_global_id = int(link.inviter_global_id)
    except AccountRegistrationError as exc:
        if exc.reason in {"invalid_code", "code_not_found", "self_ref"}:
            raise ReferralOnboardingRejected(exc.reason) from exc
        if exc.reason == "ACCOUNT_ALREADY_EXISTS":
            return ReferralOnboardingResult(
                created=False,
                referral_attached=False,
                reason="existing_user_locked",
            )
        if (
            exc.reason == "STORAGE_CONFLICT"
            and await _tg_identity_exists_after_storage_conflict(
                db,
                tg_id=user_tg_id,
            )
        ):
            return ReferralOnboardingResult(
                created=False,
                referral_attached=False,
                reason="existing_user_locked",
            )
        raise

    if registration is None:
        raise RuntimeError("registration_result_missing")
    return ReferralOnboardingResult(
        created=True,
        referral_attached=registration.referral_attached,
        reason=(
            "created_with_referral"
            if registration.referral_attached
            else "created_zero_user"
        ),
        inviter_global_id=inviter_global_id,
    )


async def onboard_user_at_first_creation(
    db: AsyncSession,
    *,
    tg_id: int,
    username: str | None = None,
    start_param: str | None = None,
    created_at: datetime | None = None,
) -> ReferralOnboardingResult:
    """Compatibility wrapper с явным владением root transaction."""

    try:
        result = await onboard_user_at_first_creation_in_transaction(
            db,
            tg_id=tg_id,
            username=username,
            start_param=start_param,
            created_at=created_at,
        )
        await db.commit()
        return result
    except BaseException:
        await db.rollback()
        raise


@dataclass(frozen=True, slots=True)
class _ReferralOwner:
    global_id: int


async def _load_referral_owner(
    db: AsyncSession,
    *,
    global_id: int,
) -> _ReferralOwner | None:
    row = (
        await db.execute(
            select(User.global_id)
            .where(User.global_id == int(global_id))
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    return _ReferralOwner(global_id=int(row.global_id))


async def on_user_first_panel_activation(
    db: AsyncSession,
    *,
    buyer_global_id: int,
    activation_dt: datetime | None = None,
) -> None:
    buyer = await _load_referral_owner(
        db,
        global_id=int(buyer_global_id),
    )
    if buyer is None:
        return
    activation = await activate_referral(
        db,
        invitee_global_id=buyer.global_id,
        activation_dt=activation_dt,
    )
    link = activation.link
    if link is None or not activation.activated_now:
        return
    inviter = await _load_referral_owner(
        db,
        global_id=int(link.inviter_global_id),
    )
    if inviter is None:
        return
    await _award_first_panel_referral_rewards(
        db=db,
        inviter_global_id=inviter.global_id,
        buyer_global_id=buyer.global_id,
    )


async def _award_first_panel_referral_rewards(
    *,
    db: AsyncSession,
    inviter_global_id: int,
    buyer_global_id: int,
) -> None:
    """Run both rewards in the caller transaction and fail through."""
    try:
        await _maybe_reward_active_unit_bonus(
            db,
            inviter_global_id=int(inviter_global_id),
            buyer_global_id=int(buyer_global_id),
        )
        await _sync_inviter_level_rewards(
            db,
            inviter_global_id=int(inviter_global_id),
        )
    except Exception:
        logger.exception(
            "referral_bonus_transaction_rolled_back "
            "inviter_global_id=%s buyer_global_id=%s "
            "canonical_owner_only=true",
            int(inviter_global_id),
            int(buyer_global_id),
        )
        raise


async def _reserve_direct_reward_slot(
    db: AsyncSession,
    *,
    inviter_global_id: int,
    buyer_global_id: int,
) -> int | None:
    """Атомарно закрепить номерной direct-reward slot за referral link."""

    await db.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(:lock_key, 0))"
        ),
        {"lock_key": f"efhc.referral.unit:{int(inviter_global_id)}"},
    )
    link = (
        await db.execute(
            select(ReferralLink)
            .where(
                ReferralLink.inviter_global_id == int(inviter_global_id),
                ReferralLink.invitee_global_id == int(buyer_global_id),
                ReferralLink.activated_at.isnot(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if link is None:
        return None
    if link.unit_reward_no is not None:
        return int(link.unit_reward_no)

    max_slot = int(
        (
            await db.scalar(
                select(func.coalesce(func.max(ReferralLink.unit_reward_no), 0))
                .where(
                    ReferralLink.inviter_global_id == int(inviter_global_id)
                )
            )
        )
        or 0
    )
    legacy_paid_count = int(
        (
            await db.scalar(
                select(func.count(EfhcTransferLog.id)).where(
                    EfhcTransferLog.global_id == int(inviter_global_id),
                    EfhcTransferLog.direction == "credit",
                    EfhcTransferLog.balance_type == "bonus",
                    EfhcTransferLog.reason == "referral_active_unit",
                )
            )
        )
        or 0
    )
    reward_no = max(max_slot, legacy_paid_count) + 1
    if reward_no > REF_MAX_ACTIVE_FOR_UNIT_BONUS:
        return None
    link.unit_reward_no = int(reward_no)
    await db.flush()
    return int(reward_no)


async def _maybe_reward_active_unit_bonus(
    db: AsyncSession,
    *,
    inviter_global_id: int,
    buyer_global_id: int,
) -> None:
    reward_no = await _reserve_direct_reward_slot(
        db,
        inviter_global_id=int(inviter_global_id),
        buyer_global_id=int(buyer_global_id),
    )
    if reward_no is None:
        return

    canonical = (
        f"REF_ACT_UNIT:G{int(inviter_global_id):010d}:N{int(reward_no):05d}"
    )
    inviter_owner = await _load_referral_owner(
        db,
        global_id=int(inviter_global_id),
    )
    buyer_owner = await _load_referral_owner(
        db,
        global_id=int(buyer_global_id),
    )
    inviter_provider_tg_id = (
        await resolve_verified_telegram_subject(
            db, global_id=inviter_owner.global_id
        )
        if inviter_owner is not None
        else None
    )
    buyer_provider_tg_id = (
        await resolve_verified_telegram_subject(
            db, global_id=buyer_owner.global_id
        )
        if buyer_owner is not None
        else None
    )
    await credit_user_bonus_from_bank_nocommit(
        db=db,
        global_id=int(inviter_global_id),
        amount=REF_BONUS_PER_ACTIVE_UNIT,
        reason="referral_active_unit",
        idempotency_key=canonical,
        meta={
            "inviter_global_id": int(inviter_global_id),
            "buyer_global_id": int(buyer_global_id),
            "reward_no": int(reward_no),
            "provider_tg_id": inviter_provider_tg_id,
            "buyer_provider_tg_id": buyer_provider_tg_id,
            "canonical_idempotency_key": canonical,
        },
    )


async def _sync_inviter_level_rewards(
    db: AsyncSession,
    *,
    inviter_global_id: int,
) -> None:
    active = await _count_active_referrals(db, int(inviter_global_id))
    inviter_owner = await _load_referral_owner(
        db,
        global_id=int(inviter_global_id),
    )
    inviter_provider_tg_id = (
        await resolve_verified_telegram_subject(
            db, global_id=inviter_owner.global_id
        )
        if inviter_owner is not None
        else None
    )
    for cfg in REF_LEVELS:
        if active < cfg.required_active:
            continue
        canonical = (
            f"REF_LVL:G{int(inviter_global_id):010d}:L{cfg.level}"
        )
        previous_global = (
            f"REF_LVL:G{int(inviter_global_id):010d}:{cfg.level}"
        )
        legacy_tg = (
            f"REF_LVL:{int(inviter_provider_tg_id)}:{cfg.level}"
            if inviter_provider_tg_id is not None
            else None
        )
        historical_keys = [previous_global]
        if legacy_tg is not None:
            historical_keys.append(legacy_tg)
        existing_key = await db.scalar(
            select(EfhcTransferLog.idempotency_key)
            .where(
                EfhcTransferLog.idempotency_key.in_(
                    [canonical, *historical_keys]
                )
            )
            .order_by(
                (EfhcTransferLog.idempotency_key == canonical).desc(),
                EfhcTransferLog.id.asc(),
            )
            .limit(1)
        )
        selected_key = str(existing_key or canonical)
        await credit_user_bonus_from_bank_nocommit(
            db=db,
            global_id=int(inviter_global_id),
            amount=cfg.bonus,
            reason="referral_level_bonus",
            idempotency_key=selected_key,
            meta={
                "inviter_global_id": int(inviter_global_id),
                "provider_tg_id": inviter_provider_tg_id,
                "level": cfg.level,
                "required_active": cfg.required_active,
                "active_refs": active,
                "canonical_idempotency_key": canonical,
                "previous_global_idempotency_key": previous_global,
                "legacy_tg_idempotency_key": legacy_tg,
            },
        )


async def admin_summary(
    db: AsyncSession,
    *,
    limit: int = 50,
    after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lim = max(1, min(int(limit), 200))
    after_gid: int | None = None
    if after and after.get("after_inviter_global_id") is not None:
        after_gid = int(after["after_inviter_global_id"])
    bonus_totals = (
        select(
            EfhcTransferLog.global_id.label("global_id"),
            func.coalesce(func.sum(EfhcTransferLog.amount), 0).label(
                "total_bonus"
            ),
        )
        .where(
            EfhcTransferLog.direction == "credit",
            EfhcTransferLog.balance_type == "bonus",
            EfhcTransferLog.reason.in_(
                ["referral_active_unit", "referral_level_bonus"]
            ),
        )
        .group_by(EfhcTransferLog.global_id)
        .subquery()
    )
    stmt = (
        select(
            ReferralLink.inviter_global_id.label("inviter_global_id"),
            func.count()
            .filter(ReferralLink.activated_at.isnot(None))
            .label("active_count"),
            func.count()
            .filter(ReferralLink.activated_at.is_(None))
            .label("inactive_count"),
            func.max(ReferralLink.created_at).label("last_invited_at"),
            func.coalesce(bonus_totals.c.total_bonus, 0).label("total_bonus"),
        )
        .outerjoin(
            bonus_totals,
            bonus_totals.c.global_id == ReferralLink.inviter_global_id,
        )
        .group_by(
            ReferralLink.inviter_global_id,
            bonus_totals.c.total_bonus,
        )
        .order_by(ReferralLink.inviter_global_id.asc())
        .limit(lim)
    )
    if after_gid is not None:
        stmt = stmt.where(ReferralLink.inviter_global_id > after_gid)
    rows = (await db.execute(stmt)).mappings().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        gid = int(row["inviter_global_id"])
        items.append(
            {
                "inviter_global_id": gid,
                "active_count": int(row["active_count"] or 0),
                "inactive_count": int(row["inactive_count"] or 0),
                "total_bonus_efhc": str(d8(row["total_bonus"] or 0)),
                "last_invited_at": (
                    row["last_invited_at"].isoformat()
                    if row["last_invited_at"]
                    else None
                ),
            }
        )
    next_after = None
    if len(rows) == lim and rows:
        next_after = {
            "after_inviter_global_id": int(
                rows[-1]["inviter_global_id"]
            )
        }
    return {"items": items, "next_after": next_after}


__all__ = [
    "BOT_USERNAME",
    "REFERRAL_BONUS_ASSET",
    "REF_BONUS_PER_ACTIVE_UNIT",
    "REF_LEVELS",
    "REF_MAX_ACTIVE_FOR_UNIT_BONUS",
    "ReferralCounters",
    "ReferralItem",
    "ReferralLevelConfig",
    "ReferralLevelStep",
    "ReferralOnboardingRejected",
    "ReferralOnboardingResult",
    "ReferralPageStats",
    "ReferralStats",
    "ReferralsPage",
    "SQL_LIST_REFERRALS_GLOBAL",
    "_count_active_referrals",
    "_maybe_reward_active_unit_bonus",
    "_sync_inviter_level_rewards",
    "admin_summary",
    "build_referral_link",
    "ensure_consistency",
    "get_counters_global",
    "get_or_create_referral_code",
    "get_referral_level_steps",
    "get_referral_stats",
    "get_referrals_page_stats_global",
    "list_active_referrals_global",
    "list_inactive_referrals_global",
    "on_user_first_panel_activation",
    "onboard_user_at_first_creation",
]

# Canonical short public names. Все принимают только global_id.
async def svc_list_referrals_active(
    db: AsyncSession,
    inviter_global_id: int,
    limit: int,
    cursor: CursorTuple | None,
) -> tuple[list[ReferralItem], CursorTuple | None]:
    return await _svc_list_referrals_global(
        db,
        inviter_global_id=int(inviter_global_id),
        limit=int(limit),
        cursor=cursor,
        want_active=True,
    )


async def svc_list_referrals_inactive(
    db: AsyncSession,
    inviter_global_id: int,
    limit: int,
    cursor: CursorTuple | None,
) -> tuple[list[ReferralItem], CursorTuple | None]:
    return await _svc_list_referrals_global(
        db,
        inviter_global_id=int(inviter_global_id),
        limit=int(limit),
        cursor=cursor,
        want_active=False,
    )


async def list_active_referrals(
    db: AsyncSession,
    *,
    parent_global_id: int,
    limit: int = 100,
    cursor: str | None = None,
) -> ReferralsPage:
    return await list_active_referrals_global(
        db,
        parent_global_id=int(parent_global_id),
        limit=int(limit),
        cursor=cursor,
    )


async def list_inactive_referrals(
    db: AsyncSession,
    *,
    parent_global_id: int,
    limit: int = 100,
    cursor: str | None = None,
) -> ReferralsPage:
    return await list_inactive_referrals_global(
        db,
        parent_global_id=int(parent_global_id),
        limit=int(limit),
        cursor=cursor,
    )


async def get_counters(
    db: AsyncSession,
    *,
    parent_global_id: int,
) -> ReferralCounters:
    return await get_counters_global(
        db,
        parent_global_id=int(parent_global_id),
    )


__all__.extend(
    [
        "get_counters",
        "list_active_referrals",
        "list_inactive_referrals",
        "svc_list_referrals_active",
        "svc_list_referrals_inactive",
    ]
)
