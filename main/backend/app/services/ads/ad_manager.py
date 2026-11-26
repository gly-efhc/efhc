"""Единый backend AdManager EFHC.

Архитектурные границы:
- Tasks определяет ``bonus_efhc`` и task-specific ADS policy;
- provider adapter только подтверждает/описывает рекламное событие;
- AdManager владеет server session, mediation/fallback, лимитом и verification;
- существующий ``tasks_service`` выполняет единственное EFHCb начисление.

Ни один provider callback не может задавать внутренний размер EFHCb.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Final, cast

from app.core.config_core import get_settings
from app.core.decimal_utils import d8
from app.core.logging_core import get_logger
from app.identity.types import (
    GlobalId,
    global_id_from_database,
    global_id_to_database,
    parse_global_id,
)
from app.integrations.ads.base import AdContext, ProviderVerification
from app.integrations.ads.registry import get_provider_adapter
from app.lib.time import utcnow
from app.models.ads_models import (
    AdDailyCounter,
    AdEvent,
    AdProviderClaim,
    AdProviderConfig,
    AdSession,
)
from app.models.tasks_models import Task
from app.services.ads.config_service import (
    ProviderRuntimeConfig,
    load_all_provider_configs,
    load_provider_config,
)
from app.services.ads.provider_registry import PRODUCTION_PROVIDER_CODES
from app.services.tasks_service import confirm_ad_view_and_credit
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()

NORMALIZED_ERRORS: Final[frozenset[str]] = frozenset({
    "NO_FILL",
    "NOT_CONFIGURED",
    "DISABLED",
    "NOT_SUPPORTED",
    "GEO_NOT_SUPPORTED",
    "LANG_NOT_SUPPORTED",
    "SDK_LOAD_FAILED",
    "TIMEOUT",
    "USER_SKIPPED",
    "PROVIDER_ERROR",
    "VERIFICATION_FAILED",
    "DAILY_LIMIT_REACHED",
    "SESSION_EXPIRED",
})

TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({
    "rewarded", "no_fill", "failed", "skipped", "expired", "fraud_rejected"
})

TECHNICAL_FAILURE_EVENTS: Final[tuple[str, ...]] = (
    "provider_error", "timeout", "preload_failed"
)


CLIENT_TELEMETRY_EVENTS: Final[frozenset[str]] = frozenset({
    "ad_requested", "preload_started", "preload_success", "preload_failed",
})

# Browser completion может разрешать EFHCb reward только если adapter
# независимо подтверждает событие через provider-side boundary.
CLIENT_REWARD_AUTHORITY_MODES: Final[frozenset[str]] = frozenset({
    "sdk_completion_plus_server_task_check",
})


class AdManagerError(RuntimeError):
    """Нормализованная business-ошибка рекламного mediation."""

    def __init__(self, code: str, *, status_code: int = 400) -> None:
        normalized = str(code or "PROVIDER_ERROR").strip().upper()
        super().__init__(normalized)
        self.code = normalized
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class AdTaskPolicy:
    task_code: str
    reward_snapshot_efhcb: Decimal
    primary_provider: str | None
    daily_limit: int
    fallback_enabled: bool
    required_format: str
    placement: str | None
    total_limit: int | None


@dataclass(frozen=True, slots=True)
class AdSessionView:
    session_id: str
    task_code: str
    status: str
    primary_provider: str | None
    actual_provider: str | None
    provider: dict[str, Any] | None
    reward_efhcb: str
    expires_at: str
    failure_code: str | None
    fallback_count: int
    verification_level: str | None
    estimated_revenue_usd: str | None
    actual_revenue_usd: str | None
    rewarded: bool
    test_mode: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_code": self.task_code,
            "status": self.status,
            "primary_provider": self.primary_provider,
            "actual_provider": self.actual_provider,
            "provider": self.provider,
            "reward_efhcb": self.reward_efhcb,
            "expires_at": self.expires_at,
            "failure_code": self.failure_code,
            "fallback_count": self.fallback_count,
            "verification_level": self.verification_level,
            "estimated_revenue_usd": self.estimated_revenue_usd,
            "actual_revenue_usd": self.actual_revenue_usd,
            "rewarded": self.rewarded,
            "test_mode": self.test_mode,
        }


def _now() -> datetime:
    return cast(datetime, utcnow())


def _gid(external_global_id: str) -> GlobalId:
    try:
        return parse_global_id(external_global_id)
    except Exception as exc:
        raise AdManagerError("VERIFICATION_FAILED", status_code=403) from exc


def _safe_metadata(values: dict[str, Any] | None) -> dict[str, Any]:
    """Удалить secret/token/credential-похожие ключи из append-only telemetry."""

    if not values:
        return {}
    out: dict[str, Any] = {}
    for key, value in values.items():
        name = str(key)
        lowered = name.lower()
        if any(marker in lowered for marker in ("secret", "token", "password", "api_key", "credential")):
            continue
        if isinstance(value, dict):
            out[name] = _safe_metadata(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[name] = value
    return out


def _task_ads_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(meta or {})
    nested = raw.get("ads")
    if isinstance(nested, dict):
        return dict(nested)
    # bounded compatibility: старые записи могли хранить ADS-поля top-level.
    return {
        key: raw[key]
        for key in (
            "primary_provider", "daily_limit", "fallback_enabled", "required_format",
            "placement", "provider_placement", "starts_at", "ends_at",
        )
        if key in raw
    }


async def _load_task_policy(db: AsyncSession, task_code: str) -> AdTaskPolicy:
    task = (
        await db.execute(select(Task).where(Task.code == str(task_code)).limit(1))
    ).scalar_one_or_none()
    if task is None:
        raise AdManagerError("NOT_SUPPORTED", status_code=404)
    if not bool(task.active):
        raise AdManagerError("DISABLED", status_code=409)
    if str(task.type or "") != "watch_ad":
        raise AdManagerError("NOT_SUPPORTED", status_code=409)
    if task.total_limit is not None and int(task.performed_count or 0) >= int(task.total_limit):
        raise AdManagerError("DAILY_LIMIT_REACHED", status_code=409)

    ads = _task_ads_meta(task.meta if isinstance(task.meta, dict) else None)
    primary = str(ads.get("primary_provider") or "").strip().lower() or None
    raw_daily = ads.get("daily_limit", 10)
    try:
        daily_limit = max(1, int(raw_daily))
    except (TypeError, ValueError):
        daily_limit = 10
    fallback_enabled = bool(ads.get("fallback_enabled", True))
    required_format = str(ads.get("required_format") or "rewarded").strip().lower()
    placement = str(ads.get("placement") or ads.get("provider_placement") or "").strip() or None

    def _schedule_time(value: Any) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AdManagerError("NOT_SUPPORTED", status_code=409) from exc
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

    starts_at = _schedule_time(ads.get("starts_at"))
    ends_at = _schedule_time(ads.get("ends_at"))
    now = _now()
    if starts_at is not None and now < starts_at:
        raise AdManagerError("DISABLED", status_code=409)
    if ends_at is not None and now >= ends_at:
        raise AdManagerError("DISABLED", status_code=409)
    if starts_at is not None and ends_at is not None and starts_at >= ends_at:
        raise AdManagerError("NOT_SUPPORTED", status_code=409)

    return AdTaskPolicy(
        task_code=str(task.code),
        reward_snapshot_efhcb=d8(task.bonus_efhc or Decimal("0")),
        primary_provider=primary,
        daily_limit=daily_limit,
        fallback_enabled=fallback_enabled,
        required_format=required_format,
        placement=placement,
        total_limit=int(task.total_limit) if task.total_limit is not None else None,
    )


async def _append_event(
    db: AsyncSession,
    session: AdSession,
    event_type: str,
    *,
    provider: str | None = None,
    provider_event_id: str | None = None,
    estimated_revenue_usd: Decimal | None = None,
    actual_revenue_usd: Decimal | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    event_provider = provider or session.actual_provider
    if provider_event_id is not None:
        exists = (
            await db.execute(
                select(AdEvent.id).where(
                    AdEvent.provider == event_provider,
                    AdEvent.provider_event_id == provider_event_id,
                    AdEvent.event_type == str(event_type),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if exists is not None:
            return
    db.add(
        AdEvent(
            session_id=str(session.session_id),
            provider=event_provider,
            task_code=str(session.task_code),
            event_type=str(event_type),
            provider_event_id=provider_event_id,
            estimated_revenue_usd=estimated_revenue_usd,
            actual_revenue_usd=actual_revenue_usd,
            metadata_json=_safe_metadata(metadata),
        )
    )



async def _claim_reward_authoritative_provider_event(
    db: AsyncSession,
    *,
    session: AdSession,
    provider_event_id: str | None,
) -> None:
    """Закрепить provider event за одной rewarded EFHC session."""

    provider = str(session.actual_provider or "").strip().lower()
    event_id = str(provider_event_id or "").strip()
    if not event_id:
        if provider == "adexium":
            session.status = "fraud_rejected"
            session.failure_code = "VERIFICATION_FAILED"
            await _append_event(
                db,
                session,
                "fraud_rejected",
                provider=provider,
                metadata={"reason": "missing_provider_financial_claim"},
            )
            await db.commit()
            raise AdManagerError("VERIFICATION_FAILED", status_code=409)
        return

    inserted = (
        await db.execute(
            pg_insert(AdProviderClaim)
            .values(
                provider=provider,
                provider_event_id=event_id,
                session_id=str(session.session_id),
                global_id=int(session.global_id),
            )
            .on_conflict_do_nothing(
                index_elements=["provider", "provider_event_id"]
            )
            .returning(AdProviderClaim.id)
        )
    ).scalar_one_or_none()
    if inserted is not None:
        return

    existing = (
        await db.execute(
            select(AdProviderClaim)
            .where(
                AdProviderClaim.provider == provider,
                AdProviderClaim.provider_event_id == event_id,
            )
            .with_for_update()
        )
    ).scalar_one()
    if (
        str(existing.session_id) == str(session.session_id)
        and int(existing.global_id) == int(session.global_id)
    ):
        return

    session.status = "fraud_rejected"
    session.failure_code = "VERIFICATION_FAILED"
    await _append_event(
        db,
        session,
        "fraud_rejected",
        provider=provider,
        provider_event_id=event_id,
        metadata={
            "reason": "provider_event_already_claimed",
            "claimed_session_id": str(existing.session_id),
        },
    )
    await db.commit()
    raise AdManagerError("VERIFICATION_FAILED", status_code=409)



def _require_session_status(session: AdSession, allowed: frozenset[str]) -> None:
    current = str(session.status or "")
    if current not in allowed:
        raise AdManagerError("VERIFICATION_FAILED", status_code=409)


async def _lock_daily_counter(
    db: AsyncSession,
    *,
    gid_db: int,
    task_code: str,
) -> AdDailyCounter:
    utc_day = _now().date()
    stmt = pg_insert(AdDailyCounter).values(
        global_id=gid_db,
        task_code=task_code,
        utc_date=utc_day,
        attempts=0,
        successful_views=0,
        rewards=0,
        reserved_rewards=0,
    ).on_conflict_do_nothing(
        index_elements=["global_id", "task_code", "utc_date"]
    )
    await db.execute(stmt)
    counter = (
        await db.execute(
            select(AdDailyCounter)
            .where(
                AdDailyCounter.global_id == gid_db,
                AdDailyCounter.task_code == task_code,
                AdDailyCounter.utc_date == utc_day,
            )
            .with_for_update()
        )
    ).scalar_one()
    return counter


async def _record_attempt_and_check_limit(
    db: AsyncSession,
    *,
    gid_db: int,
    task_code: str,
    daily_limit: int,
) -> None:
    counter = await _lock_daily_counter(db, gid_db=gid_db, task_code=task_code)
    if int(counter.successful_views or 0) >= int(daily_limit):
        raise AdManagerError("DAILY_LIMIT_REACHED", status_code=429)
    counter.attempts = int(counter.attempts or 0) + 1


async def _circuit_open(db: AsyncSession, provider: str) -> bool:
    """DB-backed circuit breaker: технические отказы отделены от NO_FILL.

    После пяти минут без новых технических отказов провайдер допускается в
    состояние ``probe``. Первый успешный impression/completion снова делает
    его ``healthy`` через ``_set_provider_health``.
    """

    since = _now() - timedelta(minutes=5)
    failures = int(
        (
            await db.execute(
                select(func.count(AdEvent.id)).where(
                    AdEvent.provider == provider,
                    AdEvent.event_type.in_(TECHNICAL_FAILURE_EVENTS),
                    AdEvent.ts >= since,
                )
            )
        ).scalar_one()
        or 0
    )
    last_success = (
        await db.execute(
            select(func.max(AdEvent.ts)).where(
                AdEvent.provider == provider,
                AdEvent.event_type.in_(("impression", "completed", "verified", "reward_credited")),
                AdEvent.ts >= since,
            )
        )
    ).scalar_one_or_none()
    row = (
        await db.execute(
            select(AdProviderConfig).where(AdProviderConfig.code == provider).limit(1)
        )
    ).scalar_one_or_none()
    opened = failures >= 3 and last_success is None
    if row is not None:
        if opened:
            row.health_status = "circuit_open"
        elif row.health_status == "circuit_open":
            row.health_status = "probe"
    return opened


async def _rate_limit_session_creation(db: AsyncSession, *, gid_db: int) -> None:
    limit = max(1, int(getattr(settings, "ADS_SESSION_RATE_LIMIT_PER_MIN", 20) or 20))
    since = _now() - timedelta(minutes=1)
    count = int(
        (
            await db.execute(
                select(func.count(AdSession.session_id)).where(
                    AdSession.global_id == gid_db,
                    AdSession.started_at >= since,
                )
            )
        ).scalar_one()
        or 0
    )
    if count >= limit:
        raise AdManagerError("PROVIDER_ERROR", status_code=429)


def _candidate_codes(
    configs: list[ProviderRuntimeConfig],
    policy: AdTaskPolicy,
    *,
    test_mode: bool,
) -> list[str]:
    ordered = [item.code for item in configs]
    production = [code for code in ordered if code in PRODUCTION_PROVIDER_CODES]
    if test_mode and bool(getattr(settings, "ADS_BUILTIN_TIMER_ENABLED", False)):
        production.append("builtin_timer")
    if policy.primary_provider:
        result = [policy.primary_provider]
        if policy.fallback_enabled:
            result.extend(code for code in production if code != policy.primary_provider)
        return result
    return production




def _provider_supports_format(config: ProviderRuntimeConfig, required_format: str) -> bool:
    value = str(required_format or "rewarded").strip().lower()
    if value in {"", "rewarded"}:
        return "rewarded" in config.descriptor.capabilities
    aliases: dict[str, frozenset[str]] = {
        "rewarded_interstitial": frozenset({"adsgram", "monetag", "adexium"}),
        "rewarded_popup": frozenset({"monetag"}),
        "interstitial_video": frozenset({"richads", "adexium"}),
        "task_reward": frozenset({"admaven"}),
        "rewarded_video": frozenset({"adsgram", "tads", "mybid"}),
    }
    allowed = aliases.get(value)
    return config.code in allowed if allowed is not None else value in config.descriptor.capabilities


async def _set_provider_health(
    db: AsyncSession,
    provider: str,
    *,
    success: bool,
    error_code: str | None = None,
) -> None:
    row = (
        await db.execute(select(AdProviderConfig).where(AdProviderConfig.code == provider))
    ).scalar_one_or_none()
    if row is None:
        return
    if success:
        row.last_success_at = _now()
        row.last_error_code = None
        row.health_status = "healthy"
    else:
        if error_code == "NO_FILL":
            # NO_FILL — нормальная характеристика inventory, а не технический
            # отказ credentials/SDK. Он учитывается в analytics, но не портит
            # Обновить состояние health/circuit breaker провайдера.
            return
        row.last_error_at = _now()
        row.last_error_code = str(error_code or "PROVIDER_ERROR")[:64]
        row.health_status = "degraded"


def _view(session: AdSession) -> AdSessionView:
    provider = None
    if session.actual_provider:
        provider = {
            "code": str(session.actual_provider),
            "public_config": dict(session.provider_public_config or {}),
        }
    return AdSessionView(
        session_id=str(session.session_id),
        task_code=str(session.task_code),
        status=str(session.status),
        primary_provider=session.primary_provider,
        actual_provider=session.actual_provider,
        provider=provider,
        reward_efhcb=str(d8(session.reward_snapshot_efhcb or Decimal("0"))),
        expires_at=session.expires_at.isoformat(),
        failure_code=session.failure_code,
        fallback_count=int(session.fallback_count or 0),
        verification_level=session.verification_level,
        estimated_revenue_usd=(str(session.estimated_revenue_usd) if session.estimated_revenue_usd is not None else None),
        actual_revenue_usd=(str(session.actual_revenue_usd) if session.actual_revenue_usd is not None else None),
        rewarded=session.rewarded_at is not None,
        test_mode=bool(session.test_mode),
    )


async def create_session(
    db: AsyncSession,
    *,
    global_id: str,
    task_code: str,
    context: AdContext,
    test_mode: bool = False,
) -> AdSessionView:
    """Создать server-owned ad_session и выбрать первый доступный provider."""

    if not bool(getattr(settings, "ADS_ENABLED", True)) and not test_mode:
        raise AdManagerError("DISABLED", status_code=503)
    gid = _gid(global_id)
    gid_db = global_id_to_database(gid)
    await _rate_limit_session_creation(db, gid_db=gid_db)
    policy = await _load_task_policy(db, task_code)
    await _record_attempt_and_check_limit(
        db,
        gid_db=gid_db,
        task_code=policy.task_code,
        daily_limit=policy.daily_limit,
    )

    now = _now()
    session = AdSession(
        session_id=str(uuid.uuid4()),
        global_id=gid_db,
        task_code=policy.task_code,
        primary_provider=policy.primary_provider,
        status="created",
        app_language=str(context.app_language or "en"),
        country_code=(str(context.country_code).upper() if context.country_code else None),
        platform=context.platform,
        reward_snapshot_efhcb=policy.reward_snapshot_efhcb,
        attempted_providers=[],
        expires_at=now + timedelta(seconds=int(settings.ADS_SESSION_TTL_SEC)),
        test_mode=bool(test_mode),
    )
    db.add(session)
    await db.flush()
    await _append_event(db, session, "session_created", metadata={"daily_limit": policy.daily_limit})

    configs = await load_all_provider_configs(db)
    config_by_code = {item.code: item for item in configs}
    candidates = _candidate_codes(configs, policy, test_mode=test_mode)
    max_fallbacks = int(getattr(settings, "ADS_MAX_FALLBACKS", 10) or 10)
    if policy.primary_provider and not policy.fallback_enabled:
        max_attempts = 1
    else:
        max_attempts = min(len(candidates), max_fallbacks + 1)

    last_reason = "NO_FILL"
    for index, code in enumerate(candidates[:max_attempts]):
        attempted = list(session.attempted_providers or [])
        if code in attempted:
            continue
        attempted.append(code)
        session.attempted_providers = attempted
        cfg = config_by_code.get(code)
        if cfg is None:
            last_reason = "NOT_CONFIGURED"
            continue
        if code == "builtin_timer" and not test_mode:
            last_reason = "NOT_SUPPORTED"
            continue
        if await _circuit_open(db, code):
            last_reason = "PROVIDER_ERROR"
            await _append_event(db, session, "fallback", provider=code, metadata={"reason": "circuit_open"})
            continue
        adapter = get_provider_adapter(code)
        eligible, reason = adapter.is_eligible(cfg, context, surface="miniapp")
        if eligible and not _provider_supports_format(cfg, policy.required_format):
            eligible, reason = False, "NOT_SUPPORTED"
        if not eligible:
            last_reason = str(reason or "NOT_SUPPORTED")
            await _append_event(db, session, "fallback", provider=code, metadata={"reason": last_reason})
            continue
        await _append_event(
            db, session, "ad_requested", provider=code,
            metadata={"fallback_index": index},
        )
        try:
            preparation = await adapter.prepare(
                cfg,
                context,
                session_id=str(session.session_id),
                task_code=policy.task_code,
                placement=policy.placement,
                required_format=policy.required_format,
            )
        except Exception as exc:
            last_reason = adapter.normalize_error(exc)
            event_type = "no_fill" if last_reason == "NO_FILL" else ("timeout" if last_reason == "TIMEOUT" else "provider_error")
            await _append_event(db, session, event_type, provider=code, metadata={"reason": last_reason})
            await _set_provider_health(db, code, success=False, error_code=last_reason)
            if index + 1 < max_attempts:
                session.fallback_count = int(session.fallback_count or 0) + 1
                await _append_event(
                    db, session, "fallback_out", provider=code,
                    metadata={"reason": last_reason},
                )
            continue

        session.actual_provider = code
        session.provider_ref = preparation.provider_ref or str(session.session_id)
        session.provider_public_config = {
            **dict(preparation.public_config),
            "efhc_timeout_sec": int(getattr(settings, "ADS_PROVIDER_TIMEOUT_SEC", 8) or 8),
        }
        session.verification_level = cfg.verification_level
        session.status = "provider_selected"
        session.estimated_revenue_usd = preparation.estimated_revenue_usd
        await _append_event(
            db,
            session,
            "provider_selected",
            provider=code,
            estimated_revenue_usd=preparation.estimated_revenue_usd,
            metadata={"primary_provider": policy.primary_provider, "fallback_index": index},
        )
        if index > 0:
            await _append_event(
                db, session, "fallback_in", provider=code,
                metadata={"fallback_index": index},
            )
        await db.commit()
        return _view(session)

    session.status = "no_fill"
    session.failure_code = "NO_FILL" if last_reason in {"NO_FILL", "NOT_CONFIGURED", "DISABLED", "NOT_SUPPORTED", "GEO_NOT_SUPPORTED", "LANG_NOT_SUPPORTED", "PROVIDER_ERROR"} else last_reason
    await _append_event(db, session, "no_fill", metadata={"last_reason": last_reason})
    await db.commit()
    return _view(session)


async def _lock_owned_session(db: AsyncSession, *, session_id: str, global_id: str | None = None) -> AdSession:
    session = (
        await db.execute(
            select(AdSession).where(AdSession.session_id == str(session_id)).with_for_update()
        )
    ).scalar_one_or_none()
    if session is None:
        raise AdManagerError("SESSION_EXPIRED", status_code=404)
    if global_id is not None:
        gid = _gid(global_id)
        if global_id_to_database(global_id_from_database(session.global_id)) != global_id_to_database(gid):
            raise AdManagerError("VERIFICATION_FAILED", status_code=403)
    if session.expires_at <= _now() and session.status not in TERMINAL_STATUSES:
        session.status = "expired"
        session.failure_code = "SESSION_EXPIRED"
        await _append_event(db, session, "provider_error", metadata={"reason": "SESSION_EXPIRED"})
        await db.commit()
        raise AdManagerError("SESSION_EXPIRED", status_code=410)
    return session


async def fallback_session(
    db: AsyncSession,
    *,
    session_id: str,
    global_id: str,
    context: AdContext,
    reason: str,
) -> AdSessionView:
    """Продолжить ту же session следующим provider без второго клика."""

    session = await _lock_owned_session(db, session_id=session_id, global_id=global_id)
    if session.rewarded_at is not None:
        return _view(session)
    if session.status in {"fraud_rejected", "expired"}:
        raise AdManagerError("SESSION_EXPIRED", status_code=409)
    normalized_reason = str(reason or "PROVIDER_ERROR").strip().upper()
    if normalized_reason not in NORMALIZED_ERRORS:
        normalized_reason = "PROVIDER_ERROR"
    previous = session.actual_provider
    await _append_event(db, session, "fallback", provider=previous, metadata={"reason": normalized_reason})
    if previous:
        await _append_event(
            db, session, "fallback_out", provider=previous, metadata={"reason": normalized_reason}
        )
        await _set_provider_health(db, previous, success=False, error_code=normalized_reason)

    policy = await _load_task_policy(db, session.task_code)
    if not policy.fallback_enabled:
        session.status = "no_fill"
        session.failure_code = "NO_FILL"
        await db.commit()
        return _view(session)

    configs = await load_all_provider_configs(db)
    attempted = set(str(x) for x in (session.attempted_providers or []))
    candidates = _candidate_codes(configs, policy, test_mode=bool(session.test_mode))
    config_by_code = {item.code: item for item in configs}
    max_fallbacks = int(getattr(settings, "ADS_MAX_FALLBACKS", 10) or 10)
    for code in candidates:
        if code in attempted or int(session.fallback_count or 0) >= max_fallbacks:
            continue
        attempted.add(code)
        session.attempted_providers = list(attempted)
        cfg = config_by_code.get(code)
        if cfg is None or await _circuit_open(db, code):
            continue
        adapter = get_provider_adapter(code)
        eligible, _ = adapter.is_eligible(cfg, context, surface="miniapp")
        if eligible and not _provider_supports_format(cfg, policy.required_format):
            eligible = False
        if not eligible:
            continue
        await _append_event(
            db, session, "ad_requested", provider=code, metadata={"fallback": True}
        )
        try:
            prep = await adapter.prepare(
                cfg, context, session_id=session.session_id, task_code=session.task_code,
                placement=policy.placement, required_format=policy.required_format,
            )
        except Exception as exc:
            error = adapter.normalize_error(exc)
            await _append_event(db, session, "no_fill" if error == "NO_FILL" else "provider_error", provider=code, metadata={"reason": error})
            await _set_provider_health(db, code, success=False, error_code=error)
            session.fallback_count = int(session.fallback_count or 0) + 1
            await _append_event(
                db, session, "fallback_out", provider=code, metadata={"reason": error}
            )
            continue
        session.actual_provider = code
        session.provider_ref = prep.provider_ref or session.session_id
        session.provider_public_config = {
            **dict(prep.public_config),
            "efhc_timeout_sec": int(getattr(settings, "ADS_PROVIDER_TIMEOUT_SEC", 8) or 8),
        }
        session.verification_level = cfg.verification_level
        session.status = "provider_selected"
        session.failure_code = None
        session.fallback_count = int(session.fallback_count or 0) + 1
        session.estimated_revenue_usd = prep.estimated_revenue_usd
        await _append_event(db, session, "provider_selected", provider=code, metadata={"fallback": True})
        await _append_event(db, session, "fallback_in", provider=code, metadata={"source": "mediation"})
        await db.commit()
        return _view(session)

    session.status = "no_fill"
    session.failure_code = "NO_FILL"
    await _append_event(db, session, "no_fill", metadata={"reason": "fallback_exhausted"})
    await db.commit()
    return _view(session)


async def mark_shown(db: AsyncSession, *, session_id: str, global_id: str) -> AdSessionView:
    session = await _lock_owned_session(db, session_id=session_id, global_id=global_id)
    _require_session_status(session, frozenset({"provider_selected", "loading", "shown"}))
    if session.shown_at is None:
        session.shown_at = _now()
        session.status = "shown"
        await _append_event(db, session, "impression")
        if session.actual_provider:
            await _set_provider_health(db, session.actual_provider, success=True)
    await db.commit()
    return _view(session)


async def _reserve_task_total_slot(
    db: AsyncSession,
    *,
    session: AdSession,
) -> None:
    """Атомарно учесть completion в optional Task.total_limit.

    Для unlimited задания ``total_limit IS NULL`` счётчик всё равно растёт и
    остаётся полезным Admin analytics; для ограниченного задания UPDATE
    одновременно служит concurrency-safe guard.
    """

    if session.task_slot_reserved_at is not None:
        return
    result = await db.execute(
        update(Task)
        .where(
            Task.code == session.task_code,
            (Task.total_limit.is_(None)) | (Task.performed_count < Task.total_limit),
        )
        .values(performed_count=Task.performed_count + 1)
        .returning(Task.performed_count)
    )
    if result.scalar_one_or_none() is None:
        session.status = "failed"
        session.failure_code = "DAILY_LIMIT_REACHED"
        await _append_event(
            db, session, "fraud_rejected", metadata={"reason": "TASK_TOTAL_LIMIT_REACHED"}
        )
        await db.commit()
        raise AdManagerError("DAILY_LIMIT_REACHED", status_code=409)
    session.task_slot_reserved_at = _now()


async def _reserve_daily_reward_slot(
    db: AsyncSession,
    *,
    session: AdSession,
    daily_limit: int,
) -> None:
    """Атомарно зарезервировать максимум один reward slot этой session.

    ``tasks_service`` внутри canonical financial path делает commit, поэтому
    нельзя полагаться на удержание SELECT FOR UPDATE вокруг вызова. Отдельный
    DB counter reservation закрывает гонку двух подтверждений на 10-й слот.
    Повторный вызов той же session не резервирует слот второй раз.
    """

    if session.reward_slot_reserved_at is not None:
        return
    counter = await _lock_daily_counter(
        db,
        gid_db=global_id_to_database(global_id_from_database(session.global_id)),
        task_code=session.task_code,
    )
    result = await db.execute(
        update(AdDailyCounter)
        .where(
            AdDailyCounter.id == counter.id,
            AdDailyCounter.reserved_rewards < int(daily_limit),
        )
        .values(reserved_rewards=AdDailyCounter.reserved_rewards + 1)
        .returning(AdDailyCounter.reserved_rewards)
    )
    reserved = result.scalar_one_or_none()
    if reserved is None:
        session.status = "failed"
        session.failure_code = "DAILY_LIMIT_REACHED"
        await _append_event(
            db, session, "fraud_rejected", metadata={"reason": "DAILY_LIMIT_REACHED"}
        )
        await db.commit()
        raise AdManagerError("DAILY_LIMIT_REACHED", status_code=429)
    session.reward_slot_reserved_at = _now()


async def _finalize_verified_reward(
    db: AsyncSession,
    *,
    session: AdSession,
    verification: ProviderVerification,
) -> AdSessionView:
    if session.rewarded_at is not None:
        return _view(session)
    if bool(session.test_mode) or session.actual_provider == "builtin_timer":
        session.status = "verified"
        session.verified_at = session.verified_at or _now()
        await _append_event(
            db,
            session,
            "verified",
            provider_event_id=verification.provider_event_id,
            metadata={"test_mode": True},
        )
        await db.commit()
        return _view(session)

    await _claim_reward_authoritative_provider_event(
        db,
        session=session,
        provider_event_id=verification.provider_event_id,
    )

    policy = await _load_task_policy(db, session.task_code)
    await _reserve_daily_reward_slot(
        db, session=session, daily_limit=policy.daily_limit
    )
    await _reserve_task_total_slot(db, session=session)

    # Единственный финансовый путь: existing tasks_service + TaskCompleteLock.
    # Размер берётся только из immutable ad_session.reward_snapshot_efhcb.
    result = await confirm_ad_view_and_credit(
        db,
        global_id=global_id_to_database(global_id_from_database(session.global_id)),
        task_code=str(session.task_code),
        provider=str(session.actual_provider or "unknown"),
        provider_ref=str(session.provider_ref or session.session_id),
        bonus_efhc=d8(session.reward_snapshot_efhcb),
        idempotency_key=f"ads-session:{session.session_id}",
    )

    session = await _lock_owned_session(db, session_id=session.session_id)
    if session.rewarded_at is None:
        now = _now()
        session.completed_at = session.completed_at or now
        session.verified_at = session.verified_at or now
        session.rewarded_at = now
        session.status = "rewarded"
        session.failure_code = None
        session.estimated_revenue_usd = verification.estimated_revenue_usd or session.estimated_revenue_usd
        session.actual_revenue_usd = verification.actual_revenue_usd or session.actual_revenue_usd
        counter = await _lock_daily_counter(
            db,
            gid_db=global_id_to_database(global_id_from_database(session.global_id)),
            task_code=session.task_code,
        )
        # result.replayed означает, что reward уже был создан тем же session idk.
        # Счётчик session-level обновляем максимум один раз благодаря rewarded_at lock.
        counter.successful_views = int(counter.successful_views or 0) + 1
        counter.rewards = int(counter.rewards or 0) + 1
        counter.last_view_at = now
        await _append_event(
            db,
            session,
            "reward_credited",
            provider_event_id=verification.provider_event_id,
            estimated_revenue_usd=verification.estimated_revenue_usd,
            actual_revenue_usd=verification.actual_revenue_usd,
            metadata={"replayed_financial": bool(result.get("replayed", False))},
        )
    await db.commit()
    return _view(session)

async def reconcile_due_ad_rewards(
    db: AsyncSession,
    *,
    limit: int = 100,
) -> dict[str, int]:
    """Довести verified/completed ADS reward obligation ровно один раз."""
    safe_limit = max(1, min(int(limit), 500))
    session_ids = list(
        (
            await db.execute(
                select(AdSession.session_id)
                .where(
                    AdSession.completed_at.is_not(None),
                    AdSession.verified_at.is_not(None),
                    AdSession.rewarded_at.is_(None),
                    AdSession.test_mode.is_(False),
                    AdSession.actual_provider != "builtin_timer",
                )
                .order_by(AdSession.completed_at.asc(), AdSession.session_id.asc())
                .limit(safe_limit)
            )
        ).scalars()
    )
    credited = 0
    replayed = 0
    for session_id in session_ids:
        session = await _lock_owned_session(db, session_id=str(session_id))
        if session.rewarded_at is not None:
            continue
        if session.completed_at is None or session.verified_at is None:
            continue
        if bool(session.test_mode) or session.actual_provider == "builtin_timer":
            continue

        result = await confirm_ad_view_and_credit(
            db,
            global_id=global_id_to_database(
                global_id_from_database(session.global_id)
            ),
            task_code=str(session.task_code),
            provider=str(session.actual_provider or "unknown"),
            provider_ref=str(session.provider_ref or session.session_id),
            bonus_efhc=d8(session.reward_snapshot_efhcb),
            idempotency_key=f"ads-session:{session.session_id}",
        )

        session = await _lock_owned_session(db, session_id=str(session_id))
        if session.rewarded_at is not None:
            replayed += 1
            continue
        now = _now()
        session.rewarded_at = now
        session.status = "rewarded"
        session.failure_code = None
        counter = await _lock_daily_counter(
            db,
            gid_db=global_id_to_database(
                global_id_from_database(session.global_id)
            ),
            task_code=session.task_code,
        )
        counter.successful_views = int(counter.successful_views or 0) + 1
        counter.rewards = int(counter.rewards or 0) + 1
        counter.last_view_at = now
        await _append_event(
            db,
            session,
            "reward_credited",
            metadata={
                "reconciliation": True,
                "replayed_financial": bool(result.get("replayed", False)),
            },
        )
        await db.commit()
        credited += 1
    return {
        "scanned": len(session_ids),
        "credited": credited,
        "replayed": replayed,
    }


async def client_complete(
    db: AsyncSession,
    *,
    session_id: str,
    global_id: str,
    payload: dict[str, Any],
) -> AdSessionView:
    """Нормализовать SDK completion; уровень B ждёт server postback."""

    session = await _lock_owned_session(db, session_id=session_id, global_id=global_id)
    if session.rewarded_at is not None:
        return _view(session)
    _require_session_status(
        session, frozenset({"provider_selected", "loading", "shown", "completed", "verified"})
    )
    provider = str(session.actual_provider or "")
    if not provider:
        raise AdManagerError("NO_FILL", status_code=409)
    cfg = await load_provider_config(db, provider)
    adapter = get_provider_adapter(provider)
    try:
        verification = await adapter.verify_callback(cfg, dict(payload or {}), session_id=session.session_id)
    except Exception as exc:
        code = adapter.normalize_error(exc)
        session.failure_code = code
        await _append_event(db, session, "provider_error", provider=provider, metadata={"reason": code})
        await _set_provider_health(db, provider, success=False, error_code=code)
        await db.commit()
        raise AdManagerError(code, status_code=409) from exc

    if bool(payload.get("shown", True)) and session.shown_at is None:
        session.shown_at = _now()
        await _append_event(db, session, "impression", provider=provider)
    if verification.completed:
        session.completed_at = session.completed_at or _now()
        session.status = "completed"
        await _append_event(
            db,
            session,
            "completed",
            provider=provider,
            provider_event_id=verification.provider_event_id,
            estimated_revenue_usd=verification.estimated_revenue_usd,
            metadata=verification.metadata,
        )
    client_can_authorize_reward = (
        cfg.verification_mode in CLIENT_REWARD_AUTHORITY_MODES
    )
    diagnostic_only = bool(session.test_mode) and provider == "builtin_timer"
    if client_can_authorize_reward:
        session.estimated_revenue_usd = (
            verification.estimated_revenue_usd
            or session.estimated_revenue_usd
        )

    if cfg.verification_level == "B":
        # Monetag/AdMaven client result — только UX/telemetry; reward ждёт
        # независимо аутентифицированный provider postback.
        await db.commit()
        return _view(session)
    if not verification.verified or not verification.completed:
        await db.commit()
        raise AdManagerError("VERIFICATION_FAILED", status_code=409)
    if not client_can_authorize_reward and not diagnostic_only:
        session.failure_code = "VERIFICATION_FAILED"
        await _append_event(
            db,
            session,
            "verification_rejected",
            provider=provider,
            metadata={
                "reason": "client_completion_has_no_reward_authority",
                "verification_mode": cfg.verification_mode,
            },
        )
        await db.commit()
        raise AdManagerError("VERIFICATION_FAILED", status_code=409)

    session.verified_at = session.verified_at or _now()
    session.status = "verified"
    await _append_event(db, session, "verified", provider=provider, provider_event_id=verification.provider_event_id)
    return await _finalize_verified_reward(db, session=session, verification=verification)



async def provider_postback(
    db: AsyncSession,
    *,
    provider: str,
    session_id: str,
    payload: dict[str, Any],
) -> AdSessionView:
    """Обработать server-to-server provider event с session correlation."""

    code = str(provider or "").strip().lower()
    session = await _lock_owned_session(db, session_id=session_id)
    if session.actual_provider != code:
        raise AdManagerError("VERIFICATION_FAILED", status_code=403)
    if session.rewarded_at is not None:
        return _view(session)
    _require_session_status(
        session, frozenset({"provider_selected", "loading", "shown", "completed", "verified"})
    )
    cfg = await load_provider_config(db, code)
    adapter = get_provider_adapter(code)
    verification = await adapter.verify_callback(cfg, dict(payload or {}), session_id=session.session_id)
    await _append_event(
        db,
        session,
        "postback_received",
        provider=code,
        provider_event_id=verification.provider_event_id,
        estimated_revenue_usd=verification.estimated_revenue_usd,
        metadata=verification.metadata,
    )
    provider_event_type = str(verification.metadata.get("event_type") or "").strip().lower()
    if provider_event_type == "click":
        await _append_event(
            db, session, "click", provider=code,
            provider_event_id=verification.provider_event_id,
            metadata={"source": "provider_postback"},
        )
    if verification.valued is True:
        await _append_event(
            db, session, "valued", provider=code,
            provider_event_id=verification.provider_event_id,
            estimated_revenue_usd=verification.estimated_revenue_usd,
            metadata={"source": "provider_postback"},
        )
    if not verification.verified or not verification.completed:
        session.failure_code = "VERIFICATION_FAILED"
        await db.commit()
        raise AdManagerError("VERIFICATION_FAILED", status_code=403)

    session.completed_at = session.completed_at or _now()
    session.verified_at = session.verified_at or _now()
    session.status = "verified"
    session.estimated_revenue_usd = verification.estimated_revenue_usd or session.estimated_revenue_usd
    session.actual_revenue_usd = verification.actual_revenue_usd or session.actual_revenue_usd
    await _append_event(db, session, "verified", provider=code, provider_event_id=verification.provider_event_id)
    await _set_provider_health(db, code, success=True)
    return await _finalize_verified_reward(db, session=session, verification=verification)


async def record_client_telemetry(
    db: AsyncSession,
    *,
    session_id: str,
    global_id: str,
    event_type: str,
    metadata: dict[str, Any] | None = None,
) -> AdSessionView:
    """Записать безопасную SDK telemetry без влияния на reward state."""

    session = await _lock_owned_session(db, session_id=session_id, global_id=global_id)
    normalized = str(event_type or "").strip().lower()
    if normalized not in CLIENT_TELEMETRY_EVENTS:
        raise AdManagerError("NOT_SUPPORTED", status_code=400)
    _require_session_status(session, frozenset({"provider_selected", "loading", "shown"}))
    await _append_event(
        db, session, normalized, provider=session.actual_provider, metadata=metadata,
    )
    if normalized in {"ad_requested", "preload_started"} and session.status == "provider_selected":
        session.status = "loading"
    elif normalized == "preload_success" and session.status == "loading":
        session.status = "provider_selected"
    if normalized == "preload_failed" and session.actual_provider:
        await _set_provider_health(
            db, session.actual_provider, success=False, error_code="SDK_LOAD_FAILED"
        )
    await db.commit()
    return _view(session)


async def get_session(
    db: AsyncSession,
    *,
    session_id: str,
    global_id: str,
) -> AdSessionView:
    session = await _lock_owned_session(db, session_id=session_id, global_id=global_id)
    await db.commit()
    return _view(session)


async def create_admin_test_session(
    db: AsyncSession,
    *,
    global_id: str,
    task_code: str,
    context: AdContext,
) -> AdSessionView:
    """Admin/diagnostic session. Даже successful completion не выдаёт EFHCb."""

    return await create_session(
        db,
        global_id=global_id,
        task_code=task_code,
        context=AdContext(
            app_language=context.app_language,
            country_code=context.country_code,
            platform=context.platform,
            user_agent=context.user_agent,
            ip_address=context.ip_address,
            provider_tg_id=context.provider_tg_id,
            telegram_premium=context.telegram_premium,
            test_mode=True,
        ),
        test_mode=True,
    )


__all__ = [
    "AdContext",
    "AdManagerError",
    "AdSessionView",
    "NORMALIZED_ERRORS",
    "client_complete",
    "create_admin_test_session",
    "create_session",
    "fallback_session",
    "get_session",
    "mark_shown",
    "provider_postback",
]
