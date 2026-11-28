"""Ручная защитная деактивация и повторная активация мёртвых Панелей.

Прямой канон владельца от 2026-08-20:
- операция доступна только Admin, корневой транзакцией владеет вызывающий route;
- маркер мёртвой Панели хранится в ``panels.meta.protectively_voided``;
- агрегатное kWh-аннулирование: U=min(G,A), R=G-U, NET=100-R;
- отдельный журнал обменов по Панелям, долг и отрицательные пользовательские балансы не вводятся;
- возврат использует исторический split активации и уменьшает EFHCb до EFHCm;
- мёртвая строка физически сохраняется и может быть повторно активирована только Admin;
- повторная активация заново списывает 100 EFHC по обычному правилу EFHCb -> EFHCm.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.system_locks import get_rate_base_d8
from app.deps import d8
from app.domain.panels_rules import (
    PANEL_PRICE_D8,
    PROTECTIVELY_VOIDED_META_KEY,
    allocate_panel_payment_splits,
    calculate_protective_refund_split,
    calculate_protective_void_amounts,
)
from app.lib.time import utcnow
from app.models.panels_models import Panel, panel_is_operational_clause
from app.services import transactions_service as bank
from app.services.energy_service import checkpoint_user_energy_nocommit
from app.services.panels_service import MAX_PANELS, PANEL_LIFETIME_DAYS
from app.standards.finance_rules import (
    SpendBreakdown,
    split_bonus_then_main,
)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .admin_logging import AdminLogger
from .admin_notifications import AdminNotifier
from .admin_rbac import AdminUser


class PanelProtectiveError(Exception):
    """Стабильная ошибка защитного контура Панелей."""

    def __init__(self, code: str, *, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = int(status_code)


@dataclass(frozen=True)
class ProtectivePanelResult:
    panel_id: int
    global_id: int
    replay: bool
    operation: str
    notification_id: int | None = None
    notification_event: str | None = None
    notification_message: str | None = None
    generated_kwh: Decimal = Decimal("0")
    unused_kwh: Decimal = Decimal("0")
    realized_kwh: Decimal = Decimal("0")
    refund_bonus: Decimal = Decimal("0")
    refund_main: Decimal = Decimal("0")
    spent_bonus: Decimal = Decimal("0")
    spent_main: Decimal = Decimal("0")


def _meta_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _is_dead(meta: dict[str, Any]) -> bool:
    return meta.get(PROTECTIVELY_VOIDED_META_KEY) is True


def _event_replay(meta: dict[str, Any], *, op: str, idempotency_key: str) -> bool:
    events = meta.get("protective_events")
    if not isinstance(events, list):
        return False
    return any(
        isinstance(event, dict)
        and event.get("op") == op
        and event.get("idempotency_key") == idempotency_key
        for event in events
    )


def _append_event(meta: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    out = dict(meta)
    current = out.get("protective_events")
    events = [dict(item) for item in current if isinstance(item, dict)] if isinstance(current, list) else []
    events.append(dict(event))
    out["protective_events"] = events
    return out


def _activation_split_from_meta(meta: dict[str, Any]) -> SpendBreakdown | None:
    raw = meta.get("activation_payment_split")
    if not isinstance(raw, dict):
        return None
    try:
        bonus = d8(raw.get("bonus") or "0")
        main = d8(raw.get("main") or "0")
    except Exception:
        return None
    if bonus < 0 or main < 0 or d8(bonus + main) != PANEL_PRICE_D8:
        return None
    return SpendBreakdown(bonus_part=bonus, main_part=main)


async def _activation_split_from_ledger(
    db: AsyncSession,
    *,
    panel_id: int,
    global_id: int,
) -> SpendBreakdown | None:
    """Восстановить legacy split из канонических metadata перевода panel_activation."""

    result = await db.execute(
        text(
            """
            SELECT meta
              FROM efhc_core.efhc_transfers_log
             WHERE global_id = :global_id
               AND reason = 'panel_activation'
               AND meta IS NOT NULL
             ORDER BY id DESC
            """
        ),
        {"global_id": int(global_id)},
    )
    seen_payloads: set[str] = set()
    for row in result.fetchall():
        raw_meta = row[0]
        raw_key = str(raw_meta or "")
        if raw_key in seen_payloads:
            continue
        seen_payloads.add(raw_key)
        payload = _meta_dict(raw_meta)
        raw_ids = payload.get("panels_created_ids")
        if not isinstance(raw_ids, list):
            continue
        try:
            panel_ids = [int(value) for value in raw_ids]
        except (TypeError, ValueError):
            panel_ids = []
        if int(panel_id) not in panel_ids:
            continue
        try:
            spent_bonus = d8(payload.get("spent_bonus") or "0")
            spent_main = d8(payload.get("spent_main") or "0")
        except (InvalidOperation, TypeError, ValueError):
            spent_bonus = None
            spent_main = None
        if spent_bonus is None or spent_main is None:
            continue

        # Для legacy batch без сохранённого per-Panel split автоматическое
        # восстановление разрешено только при однозначном evidence.
        # Смешанный общий платёж нескольких Панелей не доказывает, какая
        # конкретно Панель была оплачена EFHCb/EFHCm, поэтому fail closed.
        if len(panel_ids) > 1 and spent_bonus > 0 and spent_main > 0:
            continue
        try:
            allocated = allocate_panel_payment_splits(
                panel_ids=panel_ids,
                spent_bonus=spent_bonus,
                spent_main=spent_main,
            )
        except ValueError:
            continue
        return allocated.get(int(panel_id))
    return None


async def _resolve_activation_split(
    db: AsyncSession,
    *,
    panel: Panel,
) -> SpendBreakdown:
    meta = _meta_dict(panel.meta)
    direct = _activation_split_from_meta(meta)
    if direct is not None:
        return direct
    legacy = await _activation_split_from_ledger(
        db,
        panel_id=int(panel.id),
        global_id=int(panel.global_id),
    )
    if legacy is None:
        raise PanelProtectiveError("ADMIN_PANEL_PAYMENT_EVIDENCE_MISSING", status_code=422)
    # Материализовать найденное каноническое evidence в той же корневой транзакции.
    meta["activation_payment_split"] = {
        "bonus": str(d8(legacy.bonus_part)),
        "main": str(d8(legacy.main_part)),
        "price": str(PANEL_PRICE_D8),
        "source": "legacy_panel_activation_transfer_evidence",
    }
    panel.meta = meta
    return legacy


async def _lock_panel(db: AsyncSession, panel_id: int) -> Panel:
    result = await db.execute(
        select(Panel).where(Panel.id == int(panel_id)).with_for_update()
    )
    panel = result.scalar_one_or_none()
    if panel is None:
        raise PanelProtectiveError("ADMIN_PANEL_NOT_FOUND", status_code=404)
    return panel


async def _lock_user_state(db: AsyncSession, global_id: int) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT global_id, is_vip, main_balance, bonus_balance,
                       total_generated_kwh, exchanged_kwh_total, available_kwh
                  FROM efhc_core.users
                 WHERE global_id = :global_id
                 FOR UPDATE
                """
            ),
            {"global_id": int(global_id)},
        )
    ).fetchone()
    if row is None:
        raise PanelProtectiveError("ADMIN_PANEL_OWNER_NOT_FOUND", status_code=404)
    return {
        "global_id": int(row[0]),
        "is_vip": bool(row[1]),
        "main_balance": d8(row[2] or 0),
        "bonus_balance": d8(row[3] or 0),
        "total_generated_kwh": d8(row[4] or 0),
        "exchanged_kwh_total": d8(row[5] or 0),
        "available_kwh": d8(row[6] or 0),
    }


def _active_until(panel: Panel, now: datetime) -> bool:
    return bool(
        panel.is_active
        and panel.expires_at is not None
        and panel.expires_at > now
    )


async def _count_active_operational_panels(
    db: AsyncSession,
    *,
    global_id: int,
    now: datetime,
) -> int:
    stmt = select(func.count(Panel.id)).where(
        Panel.global_id == int(global_id),
        Panel.is_active.is_(True),
        Panel.expires_at > now,
        panel_is_operational_clause(),
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def protectively_deactivate_panel_nocommit(
    db: AsyncSession,
    *,
    panel_id: int,
    admin: AdminUser,
    idempotency_key: str,
    reason: str = "Ручная защитная деактивация",
) -> ProtectivePanelResult:
    """Атомарно защитно деактивировать активную Панель; границей владеет вызывающий код."""

    idem = str(idempotency_key or "").strip()
    if not idem:
        raise PanelProtectiveError("IDEMPOTENCY_KEY_REQUIRED", status_code=400)

    owner_row = (
        await db.execute(
            select(Panel.global_id).where(Panel.id == int(panel_id))
        )
    ).scalar_one_or_none()
    if owner_row is None:
        raise PanelProtectiveError("ADMIN_PANEL_NOT_FOUND", status_code=404)

    now = utcnow()
    # Агрегат A должен быть актуальным по всем живым Панелям пользователя.
    # Корневая транзакция уже принадлежит Admin route.
    await checkpoint_user_energy_nocommit(
        db,
        global_id=int(owner_row),
        now_ts=now,
    )

    panel = await _lock_panel(db, int(panel_id))
    meta = _meta_dict(panel.meta)
    if _event_replay(meta, op="protective_deactivate", idempotency_key=idem):
        return ProtectivePanelResult(
            panel_id=int(panel.id),
            global_id=int(panel.global_id),
            replay=True,
            operation="protective_deactivate",
        )
    if _is_dead(meta):
        raise PanelProtectiveError("ADMIN_PANEL_ALREADY_DEAD")
    if not _active_until(panel, now):
        raise PanelProtectiveError("ADMIN_PANEL_NOT_ACTIVE")

    user_state = await _lock_user_state(db, int(panel.global_id))
    generated = d8(panel.generated_kwh or 0)
    payment_split = await _resolve_activation_split(db, panel=panel)

    try:
        amounts = calculate_protective_void_amounts(
            generated_kwh=generated,
            available_kwh=d8(user_state["available_kwh"]),
        )
        refund = calculate_protective_refund_split(
            original_bonus=d8(payment_split.bonus_part),
            original_main=d8(payment_split.main_part),
            realized_offset=d8(amounts.realized_kwh),
        )
    except ValueError as exc:
        raise PanelProtectiveError("ADMIN_PANEL_PROTECTIVE_AMOUNT_ANOMALY", status_code=422) from exc

    total_before = d8(user_state["total_generated_kwh"])
    exchanged_before = d8(user_state["exchanged_kwh_total"])
    if total_before < generated or exchanged_before < amounts.realized_kwh:
        raise PanelProtectiveError("ADMIN_PANEL_ENERGY_SOURCE_ANOMALY", status_code=422)

    total_after = d8(total_before - generated)
    exchanged_after = d8(exchanged_before - amounts.realized_kwh)
    if exchanged_after < 0 or exchanged_after > total_after:
        raise PanelProtectiveError("ADMIN_PANEL_ENERGY_POSTSTATE_ANOMALY", status_code=422)

    await db.execute(
        text(
            """
            UPDATE efhc_core.users
               SET total_generated_kwh = :total_generated_kwh,
                   exchanged_kwh_total = :exchanged_kwh_total,
                   updated_at = NOW()
             WHERE global_id = :global_id
            """
        ),
        {
            "global_id": int(panel.global_id),
            "total_generated_kwh": str(total_after),
            "exchanged_kwh_total": str(exchanged_after),
        },
    )

    common_meta = {
        "module": "admin_panel_protective_service",
        "panel_id": int(panel.id),
        "panel_public_id": str(panel.public_id or ""),
        "owner_global_id": str(int(panel.global_id)),
        "gross_refund": str(PANEL_PRICE_D8),
        "generated_kwh": str(amounts.generated_kwh),
        "available_kwh_before": str(amounts.available_kwh_before),
        "unused_kwh": str(amounts.unused_kwh),
        "realized_kwh": str(amounts.realized_kwh),
        "net_refund": str(amounts.net_refund_efhc),
        "original_bonus": str(d8(payment_split.bonus_part)),
        "original_main": str(d8(payment_split.main_part)),
        "refund_bonus": str(d8(refund.bonus_part)),
        "refund_main": str(d8(refund.main_part)),
        "protectively_voided": True,
        "admin_actor_global_id": int(admin.global_id),
        "admin_reason": str(reason),
    }
    if refund.bonus_part > 0:
        await bank.credit_user_bonus_from_bank_nocommit(
            db,
            global_id=int(panel.global_id),
            amount=d8(refund.bonus_part),
            reason="panel_protective_refund",
            idempotency_key=f"{idem}:refund:bonus",
            meta=common_meta,
        )
    if refund.main_part > 0:
        await bank.credit_user_from_bank_nocommit(
            db,
            global_id=int(panel.global_id),
            amount=d8(refund.main_part),
            reason="panel_protective_refund",
            idempotency_key=f"{idem}:refund:main",
            meta=common_meta,
        )

    before = {
        "is_active": bool(panel.is_active),
        "is_archived": bool(panel.is_archived),
        "generated_kwh": str(generated),
        "activated_at": panel.activated_at.isoformat() if panel.activated_at else None,
        "expires_at": panel.expires_at.isoformat() if panel.expires_at else None,
    }
    event = {
        "op": "protective_deactivate",
        "idempotency_key": idem,
        "at": now.isoformat(),
        "actor_global_id": int(admin.global_id),
        "reason": str(reason),
        "original_payment_bonus": str(d8(payment_split.bonus_part)),
        "original_payment_main": str(d8(payment_split.main_part)),
        "generated_kwh": str(amounts.generated_kwh),
        "available_kwh_before": str(amounts.available_kwh_before),
        "unused_kwh": str(amounts.unused_kwh),
        "realized_kwh": str(amounts.realized_kwh),
        "refund_bonus": str(d8(refund.bonus_part)),
        "refund_main": str(d8(refund.main_part)),
        "net_refund": str(amounts.net_refund_efhc),
        "previous_lifecycle": before,
    }
    meta = _append_event(_meta_dict(panel.meta), event)
    meta[PROTECTIVELY_VOIDED_META_KEY] = True
    meta["dead_state"] = "admin_protective_deactivation"
    meta["protectively_voided_at"] = now.isoformat()
    meta["protectively_voided_by"] = int(admin.global_id)
    panel.meta = meta
    panel.generated_kwh = str(d8("0"))
    panel.is_active = False
    panel.is_archived = False
    panel.archived_at = None
    panel.last_generated_at = now

    after = {
        "is_active": False,
        "is_archived": False,
        "generated_kwh": str(d8("0")),
        "protectively_voided": True,
        "refund_bonus": str(d8(refund.bonus_part)),
        "refund_main": str(d8(refund.main_part)),
    }
    await AdminLogger.write(
        db,
        actor_global_id=int(admin.global_id),
        admin_id=admin.id,
        action="PANEL_PROTECTIVE_DEACTIVATE",
        entity="panel",
        entity_id=int(panel.id),
        details=(
            f"global_id={int(panel.global_id)}; ik={idem}; "
            f"G={amounts.generated_kwh}; U={amounts.unused_kwh}; "
            f"R={amounts.realized_kwh}; NET={amounts.net_refund_efhc}"
        ),
        before=before,
        after=after,
        meta=common_meta,
        required=True,
    )
    notification_message = (
        f"Панель #{int(panel.id)} для global_id={int(panel.global_id)} "
        "защитно деактивирована"
    )
    notification_id = await AdminNotifier.notify_generic(
        db,
        event="PANEL_PROTECTIVELY_DEACTIVATED",
        message=notification_message,
        payload_json=json.dumps(common_meta, ensure_ascii=False),
        send_telegram=False,
    )
    return ProtectivePanelResult(
        panel_id=int(panel.id),
        global_id=int(panel.global_id),
        replay=False,
        operation="protective_deactivate",
        notification_id=int(notification_id),
        notification_event="PANEL_PROTECTIVELY_DEACTIVATED",
        notification_message=notification_message,
        generated_kwh=d8(amounts.generated_kwh),
        unused_kwh=d8(amounts.unused_kwh),
        realized_kwh=d8(amounts.realized_kwh),
        refund_bonus=d8(refund.bonus_part),
        refund_main=d8(refund.main_part),
    )


async def reactivate_dead_panel_nocommit(
    db: AsyncSession,
    *,
    panel_id: int,
    admin: AdminUser,
    idempotency_key: str,
    reason: str = "Повторная активация мёртвой Панели",
) -> ProtectivePanelResult:
    """Повторно активировать тот же мёртвый Panel ID после новой оплаты 100 EFHC."""

    idem = str(idempotency_key or "").strip()
    if not idem:
        raise PanelProtectiveError("IDEMPOTENCY_KEY_REQUIRED", status_code=400)

    owner_row = (
        await db.execute(
            select(Panel.global_id).where(Panel.id == int(panel_id))
        )
    ).scalar_one_or_none()
    if owner_row is None:
        raise PanelProtectiveError("ADMIN_PANEL_NOT_FOUND", status_code=404)

    # Единый порядок финансовых блокировок: сначала пользователь, затем Панель.
    # Это совпадает с protective deactivation и обычной активацией.
    user_state = await _lock_user_state(db, int(owner_row))
    panel = await _lock_panel(db, int(panel_id))
    if int(panel.global_id) != int(owner_row):
        raise PanelProtectiveError("ADMIN_PANEL_OWNER_CHANGED", status_code=422)
    meta = _meta_dict(panel.meta)
    if _event_replay(meta, op="reactivate_dead", idempotency_key=idem):
        return ProtectivePanelResult(
            panel_id=int(panel.id),
            global_id=int(panel.global_id),
            replay=True,
            operation="reactivate_dead",
        )
    if not _is_dead(meta):
        raise PanelProtectiveError("ADMIN_PANEL_NOT_DEAD")

    now = utcnow()
    active_count = await _count_active_operational_panels(
        db,
        global_id=int(panel.global_id),
        now=now,
    )
    if active_count >= MAX_PANELS:
        raise PanelProtectiveError("ADMIN_PANEL_LIMIT_EXCEEDED")

    try:
        spend_split = split_bonus_then_main(
            bonus_balance=d8(user_state["bonus_balance"]),
            main_balance=d8(user_state["main_balance"]),
            amount=PANEL_PRICE_D8,
        )
    except ValueError as exc:
        raise PanelProtectiveError("ADMIN_PANEL_REACTIVATION_INSUFFICIENT_FUNDS") from exc

    spend_meta = {
        "module": "admin_panel_protective_service",
        "op": "reactivate_dead_panel",
        "panel_id": int(panel.id),
        "panel_public_id": str(panel.public_id or ""),
        "owner_global_id": str(int(panel.global_id)),
        "admin_actor_global_id": int(admin.global_id),
        "admin_reason": str(reason),
        "same_panel_id": True,
    }
    result = await bank.spend_user_to_bank_bonus_then__main__nocommit(
        db,
        global_id=int(panel.global_id),
        amount=PANEL_PRICE_D8,
        reason="panel_reactivation",
        idempotency_key=f"{idem}:reactivation",
        meta=spend_meta,
    )
    if result.detail == "idempotent":
        # Событие уровня операции обычно распознаёт replay первым. Если существует только
        # денежный лог без lifecycle event, применяется fail closed вместо неоднозначного изменения.
        raise PanelProtectiveError("ADMIN_PANEL_REACTIVATION_REPLAY_STATE_MISSING", status_code=422)

    before = {
        "is_active": bool(panel.is_active),
        "is_archived": bool(panel.is_archived),
        "generated_kwh": str(d8(panel.generated_kwh or 0)),
        "protectively_voided": True,
    }
    expires_at = now + timedelta(days=int(PANEL_LIFETIME_DAYS))
    event = {
        "op": "reactivate_dead",
        "idempotency_key": idem,
        "at": now.isoformat(),
        "actor_global_id": int(admin.global_id),
        "reason": str(reason),
        "spent_bonus": str(d8(spend_split.bonus_part)),
        "spent_main": str(d8(spend_split.main_part)),
        "price": str(PANEL_PRICE_D8),
        "previous_lifecycle": before,
    }
    meta = _append_event(meta, event)
    meta.pop(PROTECTIVELY_VOIDED_META_KEY, None)
    meta.pop("dead_state", None)
    meta.pop("protectively_voided_at", None)
    meta.pop("protectively_voided_by", None)
    meta["activation_payment_split"] = {
        "bonus": str(d8(spend_split.bonus_part)),
        "main": str(d8(spend_split.main_part)),
        "price": str(PANEL_PRICE_D8),
        "source": "admin_dead_panel_reactivation",
        "source_idempotency_key": idem,
        "recorded_at": now.isoformat(),
    }
    panel.meta = meta
    panel.is_active = True
    panel.is_archived = False
    panel.activated_at = now
    panel.expires_at = expires_at
    panel.archived_at = None
    panel.last_generated_at = now
    panel.generated_kwh = str(d8("0"))
    panel.base_gen_per_sec = str(d8(get_rate_base_d8()))

    after = {
        "is_active": True,
        "is_archived": False,
        "generated_kwh": str(d8("0")),
        "protectively_voided": False,
        "activated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    await AdminLogger.write(
        db,
        actor_global_id=int(admin.global_id),
        admin_id=admin.id,
        action="PANEL_DEAD_REACTIVATED",
        entity="panel",
        entity_id=int(panel.id),
        details=(
            f"global_id={int(panel.global_id)}; ik={idem}; "
            f"spent_bonus={d8(spend_split.bonus_part)}; "
            f"spent_main={d8(spend_split.main_part)}"
        ),
        before=before,
        after=after,
        meta=spend_meta,
        required=True,
    )
    notification_message = (
        f"Мёртвая Панель #{int(panel.id)} для global_id={int(panel.global_id)} "
        "повторно активирована за 100 EFHC"
    )
    notification_id = await AdminNotifier.notify_generic(
        db,
        event="PANEL_DEAD_REACTIVATED",
        message=notification_message,
        payload_json=json.dumps(
            {
                **spend_meta,
                "spent_bonus": str(d8(spend_split.bonus_part)),
                "spent_main": str(d8(spend_split.main_part)),
            },
            ensure_ascii=False,
        ),
        send_telegram=False,
    )
    return ProtectivePanelResult(
        panel_id=int(panel.id),
        global_id=int(panel.global_id),
        replay=False,
        operation="reactivate_dead",
        notification_id=int(notification_id),
        notification_event="PANEL_DEAD_REACTIVATED",
        notification_message=notification_message,
        spent_bonus=d8(spend_split.bonus_part),
        spent_main=d8(spend_split.main_part),
    )


__all__ = [
    "PanelProtectiveError",
    "ProtectivePanelResult",
    "protectively_deactivate_panel_nocommit",
    "reactivate_dead_panel_nocommit",
]
