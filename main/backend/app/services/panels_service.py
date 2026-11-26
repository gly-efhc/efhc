# backend/app/services/panels_service.py
# =====================================================================
# EFHC Bot — Сервис панелей (активация, учёт, списки, архивирование)
# --------------------------------------------------------------------
# Назначение (коротко, 1–3 строки):
# • Операции с «солнечными панелями» пользователя:
#   активация за EFHC, учёт
# активных
# и архивных панелей, сводка для UI, архивирование просроченных.
#
# Канон/инварианты (строго):
# • Цена панели фиксирована: 100 EFHC.
# • Строгий порядок списания: СНАЧАЛА бонусный баланс, затем основной (1
# операция — 2 дебета).
# • Пользователь НИКОГДА не уходит в минус: при дефиците —
# отказ.
# • Банк EFHC может быть в минусе — операции НЕ блокируем (это не зона
# ответственности сервиса).
# • Генерация энергии везде посекундная (SSOT per-sec ставки).
# Ставка VIP определяется наличием NFT.
# Панели хранят базовую ставку на момент
# создания,
# но фактические начисления делает energy_service по текущему статусу
# VIP.
# • Лимит активных панелей на пользователя: MAX_PANELS.
# • Срок жизни панели: 180 дней; по окончании — перевод в архив
# (is_active=false).
# • Все денежные движения только через единый банковский сервис
# (transactions_service).
#
# ИИ-защиты/самовосстановление:
# • Блокировки на уровне SQL (FOR UPDATE) сериализуют денежные гонки за
# один и тот же global_id.
# • Read-through идемпотентность делается в банковском сервисе по
# idempotency_key.
# • Активация панели атомарна: списание EFHC, создание panel records,
# first-panel referral activation and rewards execute in one
# bank._tx_context; при ошибке всё откатывается вместе.
# • Для массовой активации qty>1 —
#   детерминированные ключи идемпотентности
# (suffix #1, #2, ...).
#
# Запреты:
# • Никаких P2P-переводов. Никаких EFHC→kWh. Никаких суточных расчётов.
# • Никаких прямых правок балансов — только через transactions_service.
# =====================================================================

# SSOT: p.expires_at > :server_now_utc
# SSOT: p.expires_at <= :server_now_utc
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.system_locks import (
    get_rate_base_d8,
    get_rate_vip_d8,
)
from app.deps import (
    d8,
    decode_cursor,
    encode_cursor,
)
from app.domain.panels_rules import allocate_panel_payment_splits
from app.identity.financial_write_owner import (
    resolve_and_lock_financial_write_owner,
)
from app.lib.time import utcnow
from app.models.panels_models import Panel, panel_is_operational_clause
from app.services import referral_service
from app.services import transactions_service as bank
from app.standards.finance_rules import (
    SpendBreakdown,
    split_bonus_then_main,
)
from sqlalchemy import desc, func, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


settings = get_settings()

# Константы канона (источник истины — Settings + SSOT helpers)
GEN_PER_SEC_BASE_KWH: Decimal = get_rate_base_d8()
GEN_PER_SEC_VIP_KWH: Decimal = get_rate_vip_d8()
# Канон EFHC: активация панели всегда 100 EFHC.
PANEL_PRICE: Decimal = d8("100")
MAX_PANELS: int = int(getattr(settings, "MAX_PANELS", 1000) or 1000)
PANEL_LIFETIME_DAYS: int = int(
    getattr(settings, "PANEL_LIFETIME_DAYS", 180) or 180
)

# --------------------------------------------------------------------
# Исключения домена (понятные коду роутов)
# --------------------------------------------------------------------


class PanelPurchaseError(Exception):
    """Общая ошибка активации панели (детали в сообщении)."""


class UserInDebtError(PanelPurchaseError):
    """Исторический минус: активации за EFHC заблокированы."""


class PanelLimitExceeded(PanelPurchaseError):
    """Превышен лимит активных панелей."""


class IdempotencyRequiredError(PanelPurchaseError):
    """Для денежных операций обязателен idempotency_key."""


class PanelReplayMissingDataError(PanelPurchaseError):
    """Replay-операция без данных о созданных панелях."""


# --------------------------------------------------------------------
# DTO для ответов сервиса
# --------------------------------------------------------------------
@dataclass
class PurchaseResult:
    ok: bool
    qty: int
    total_spent_bonus: Decimal
    total_spent_main: Decimal
    created_panel_ids: list[int]
    detail: str


@dataclass
class PanelsSummary:
    active_count: int
    total_generated_by_panels: Decimal
    nearest_expire_at: datetime | None


@dataclass
class PagedPanels:
    items: list[dict[str, Any]]
    next_cursor: str | None


# --------------------------------------------------------------------
# Внутренние утилиты
# --------------------------------------------------------------------
async def _lock_user_row(
    db: AsyncSession,
    *,
    global_id: int,
) -> dict[str, Any] | None:
    """Lock the canonical account row for panel mutation."""
    row = await db.execute(
        text(
            """
            SELECT global_id, is_vip,
                   main_balance, bonus_balance,
                   total_generated_kwh, available_kwh
              FROM efhc_core.users
             WHERE global_id = :global_id
             FOR UPDATE
            """
        ),
        {"global_id": int(global_id)},
    )
    rec = row.fetchone()
    if not rec:
        return None
    return {
        "global_id": int(rec[0]),
        "is_vip": bool(rec[1]),
        "main_balance": d8(rec[2]),
        "bonus_balance": d8(rec[3]),
        "total_generated_kwh": d8(rec[4]),
        "available_kwh": d8(rec[5]),
    }



async def _get_active_panels_count(
    db: AsyncSession, global_id: int
) -> int:
    """Return active panel count for canonical owner."""
    now_utc = utcnow()
    r = await db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM efhc_core.panels
            WHERE global_id = :global_id
              AND expires_at > :now_utc
              AND COALESCE((meta ->> 'protectively_voided')::boolean, FALSE) = FALSE
            """
        ),
        {"global_id": int(global_id), "now_utc": now_utc},
    )
    return int(r.scalar() or 0)



PNL_COUNTER_KEY = "panels.pnl.last_issued"
PNL_MAX_NUMBER = 99_999_999


def _format_panel_public_id(number: int) -> str:
    """Public PNL is an eight-digit global issuance number, not panels.id."""
    if not 1 <= int(number) <= PNL_MAX_NUMBER:
        raise PanelPurchaseError("Global PNL sequence exhausted or invalid.")
    return f"PNL-{int(number):08d}"


async def _reserve_panel_public_ids(db: AsyncSession, *, qty: int) -> list[str]:
    """Reserve one contiguous PNL range in the same root purchase transaction.

    app_settings is an existing persisted table with UNIQUE(key).
    Its row-level FOR UPDATE lock serializes purchases; rollback restores the
    counter together with payment, panels, and their idempotency records.
    """
    if qty <= 0:
        raise PanelPurchaseError("PNL quantity must be positive.")
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.app_settings (key, value)
            VALUES (:key, '0')
            ON CONFLICT (key) DO NOTHING
            """
        ),
        {"key": PNL_COUNTER_KEY},
    )
    result = await db.execute(
        text(
            """
            SELECT value FROM efhc_core.app_settings
            WHERE key = :key FOR UPDATE
            """
        ),
        {"key": PNL_COUNTER_KEY},
    )
    row = result.fetchone()
    if row is None:
        raise PanelPurchaseError("Global PNL counter is unavailable.")
    try:
        last_issued = int(str(row[0]))
    except (TypeError, ValueError) as exc:
        raise PanelPurchaseError("Global PNL counter is corrupted.") from exc
    if not 0 <= last_issued <= PNL_MAX_NUMBER:
        raise PanelPurchaseError("Global PNL counter is outside the allowed range.")

    # An authoritative stored PNL must agree with the locked durable counter.
    # Use the existing UNIQUE(public_id) btree, not panels.id or BIGSERIAL.
    last_panel = (
        await db.execute(
            text(
                """
                SELECT public_id FROM efhc_core.panels
                WHERE public_id >= 'PNL-00000001'
                  AND public_id <= 'PNL-99999999'
                ORDER BY public_id DESC LIMIT 1
                """
            )
        )
    ).scalar()
    stored_number = int(str(last_panel)[4:]) if last_panel else 0
    if stored_number != last_issued:
        raise PanelPurchaseError("Global PNL counter and panel registry disagree.")
    if last_issued == 0:
        existing = (
            await db.execute(
                text("SELECT EXISTS (SELECT 1 FROM efhc_core.panels)")
            )
        ).scalar()
        if existing:
            raise PanelPurchaseError(
                "Existing panels require verified PNL numbering migration."
            )
    if last_issued + qty > PNL_MAX_NUMBER:
        raise PanelPurchaseError("Eight-digit PNL number space exhausted.")

    next_number = last_issued + qty
    result = await db.execute(
        text(
            """
            UPDATE efhc_core.app_settings
               SET value = :next_value, updated_at = NOW()
             WHERE key = :key
            """
        ),
        {"key": PNL_COUNTER_KEY, "next_value": str(next_number)},
    )
    if result.rowcount != 1:
        raise PanelPurchaseError("Failed to reserve the global PNL range.")
    return [
        _format_panel_public_id(number)
        for number in range(last_issued + 1, next_number + 1)
    ]


async def _panel_public_ids(
    db: AsyncSession, *, panel_ids: list[int], global_id: int
) -> list[str]:
    """Read confirmed public IDs in input order; never synthesize a fallback."""
    if not panel_ids:
        return []
    rows = (
        await db.execute(
            select(Panel.id, Panel.public_id, Panel.global_id)
            .where(Panel.id.in_(panel_ids))
        )
    ).all()
    found = {
        int(panel_id): (public_id, int(owner_global_id))
        for panel_id, public_id, owner_global_id in rows
    }
    public_ids: list[str] = []
    for panel_id in panel_ids:
        public_id, owner_global_id = found.get(int(panel_id), (None, None))
        if (
            owner_global_id != int(global_id)
            or not isinstance(public_id, str)
            or len(public_id) != 12
            or not public_id.startswith("PNL-")
            or not public_id[4:].isascii()
            or not public_id[4:].isdigit()
            or public_id[4:] == "00000000"
        ):
            raise PanelPurchaseError("Panel has no valid eight-digit PNL.")
        public_ids.append(public_id)
    return public_ids


async def _create_panel_records_bulk(
    db: AsyncSession,
    *,
    global_id: int,
    qty: int,
) -> list[int]:
    """Insert a whole paid batch with immutable public PNLs from the locked counter.

    The VALUES list contains bound parameters, not interpolated user input.
    Match returned rows by their persisted public_id; SQL RETURNING order
    is not a contractual order and may differ from reservation order.
    """
    if qty <= 0:
        return []
    public_ids = await _reserve_panel_public_ids(db, qty=qty)
    now = utcnow()
    expires_at = now + timedelta(days=PANEL_LIFETIME_DAYS)
    values = ", ".join(
        f"(:public_id_{index})" for index in range(len(public_ids))
    )
    q = text(
        f"""
        INSERT INTO efhc_core.panels
          (
            global_id, public_id, activated_at, created_at,
            expires_at, last_generated_at, base_gen_per_sec,
            generated_kwh, is_active, is_archived, archived_at
          )
        SELECT
          :global_id, source.public_id, :activated_at, :created,
          :expires, :last_gen, :base_rate, 0, TRUE, FALSE, NULL
        FROM (VALUES {values}) AS source(public_id)
        RETURNING id, public_id
        """
    )
    params = {
        "global_id": int(global_id),
        "activated_at": now,
        "created": now,
        "expires": expires_at,
        "last_gen": now,
        "base_rate": str(GEN_PER_SEC_BASE_KWH),
    }
    params.update({
        f"public_id_{index}": public_id
        for index, public_id in enumerate(public_ids)
    })
    rows = (await db.execute(q, params)).fetchall()
    by_public_id = {
        str(public_id): int(panel_id)
        for panel_id, public_id in rows
    }
    if (
        len(rows) != qty
        or len(by_public_id) != qty
        or set(by_public_id) != set(public_ids)
        or len(set(by_public_id.values())) != qty
    ):
        raise PanelPurchaseError("Panel creation did not return the full PNL batch.")
    return [by_public_id[public_id] for public_id in public_ids]


def _json_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return dict(parsed)
        return {}
    return {}


async def _get_activation_payload_by_idk(
    db: AsyncSession,
    *,
    idempotency_key: str,
) -> dict[str, Any]:
    """Возвращает merged meta по :main и :bonus ключам списания.

    Guard: all-bonus panel activation creates only the
    ``:bonus`` spend log. Replay must therefore read both derived keys,
    otherwise it may miss existing panel ids and create duplicate panels
    without a new debit.
    """
    main_key = f"{idempotency_key}:main"
    bonus_key = f"{idempotency_key}:bonus"
    merged: dict[str, Any] = {}
    for key in (main_key, bonus_key):
        r = await db.execute(
            text(
                """
                SELECT meta
                FROM efhc_core.efhc_transfers_log
                WHERE idempotency_key = :idk
                LIMIT 1
                """
            ),
            {"idk": key},
        )
        row = r.fetchone()
        if row:
            merged.update(_json_to_dict(row[0]))
    return merged


async def _merge_activation_payload(
    db: AsyncSession,
    *,
    idempotency_key: str,
    patch: dict[str, Any],
) -> None:
    """Мержит extra_info в журнале активации панели.

    Делается диалект-safe: читаем → мержим → пишем.
    """
    main_key = f"{idempotency_key}:main"
    bonus_key = f"{idempotency_key}:bonus"
    prev = await _get_activation_payload_by_idk(
        db,
        idempotency_key=idempotency_key,
    )
    merged = dict(prev)
    merged.update(dict(patch))
    payload = json.dumps(merged, ensure_ascii=False)
    # Канон: любые правки efhc_transfers_log — только через
    # transactions_service.
    patch_dict = json.loads(payload) if payload else {}
    for idk in (bonus_key, main_key):
        await bank.append_transfer_meta_by_idempotency_key(
            db,
            idempotency_key=str(idk),
            meta=dict(patch_dict),
        )


async def _persist_activation_payment_splits(
    db: AsyncSession,
    *,
    panel_ids: list[int],
    spent_bonus: Decimal,
    spent_main: Decimal,
    idempotency_key: str,
) -> None:
    """Материализовать payment split каждой Панели для точного будущего refund."""

    splits = allocate_panel_payment_splits(
        panel_ids=[int(value) for value in panel_ids],
        spent_bonus=d8(spent_bonus),
        spent_main=d8(spent_main),
    )
    if not splits:
        return
    rows = (
        await db.execute(
            select(Panel)
            .where(Panel.id.in_(list(splits)))
            .with_for_update()
        )
    ).scalars().all()
    by_id = {int(panel.id): panel for panel in rows}
    if set(by_id) != set(splits):
        raise PanelPurchaseError("Строки payment split Панелей неполны.")
    recorded_at = utcnow().isoformat()
    for panel_id in panel_ids:
        panel = by_id[int(panel_id)]
        split = splits[int(panel_id)]
        meta = dict(panel.meta or {})
        meta["activation_payment_split"] = {
            "bonus": str(d8(split.bonus_part)),
            "main": str(d8(split.main_part)),
            "price": str(d8(PANEL_PRICE)),
            "source": "canonical_panel_activation",
            "source_idempotency_key": str(idempotency_key),
            "recorded_at": recorded_at,
        }
        panel.meta = meta


# --------------------------------------------------------------------
# Публичные функции сервиса
# --------------------------------------------------------------------
async def activate_panel(
    db: AsyncSession,
    *,
    global_id: int,
    qty: int = 1,
    idempotency_key: str | None = None,
    admin_actor_global_id: int | None = None,
    admin_reason: str | None = None,
) -> PurchaseResult:
    """Activate panels atomically for canonical ``global_id`` owner."""
    if not idempotency_key or not idempotency_key.strip():
        raise IdempotencyRequiredError(
            "Idempotency-Key is required by canon for "
            "monetary operations."
        )
    if qty <= 0:
        raise PanelPurchaseError("Количество панелей должно быть >= 1.")

    total_amount = d8(PANEL_PRICE) * d8(qty)
    created_ids: list[int] = []
    created_public_ids: list[str] = []
    status = "success"
    breakdown = SpendBreakdown(
        bonus_part=d8("0"), main_part=d8("0")
    )

    try:
        async with bank._tx_context(db):
            owner = await resolve_and_lock_financial_write_owner(
                db, global_id=int(global_id)
            )
            user = await _lock_user_row(
                db, global_id=owner.global_id
            )
            if not user:
                raise PanelPurchaseError("Пользователь не найден.")
            bonus_before = d8(user["bonus_balance"])
            main_before = d8(user["main_balance"])

            debit_result = await (
                bank.spend_user_to_bank_bonus_then__main__nocommit
            )(
                db,
                global_id=owner.global_id,
                amount=d8(total_amount),
                reason="panel_activation",
                idempotency_key=str(idempotency_key),
                meta={
                    "module": "panels_service",
                    "owner_global_id": str(owner.global_id),
                    "qty": int(qty),
                    "price_per_panel": str(d8(PANEL_PRICE)),
                    "panel_activation_atomicity": "true",
                    "activation_source": (
                        "admin_user_ops"
                        if admin_actor_global_id is not None
                        else "user"
                    ),
                    "admin_actor_global_id": admin_actor_global_id,
                    "admin_reason": admin_reason,
                },
            )

            current_active = await _get_active_panels_count(
                db, owner.global_id
            )
            if debit_result.detail == "idempotent":
                status = "replay"
                payload = await _get_activation_payload_by_idk(
                    db, idempotency_key=str(idempotency_key)
                )
                ids = payload.get("panels_created_ids")
                if not (
                    isinstance(ids, list)
                    and len(ids) == int(qty)
                    and len(set(ids)) == len(ids)
                    and all(isinstance(value, int) and value > 0 for value in ids)
                ):
                    raise PanelReplayMissingDataError(
                        "Panel replay requires the complete, unique created panel IDs."
                    )
                if payload.get("global_id") is None or payload.get("qty") is None:
                    raise PanelReplayMissingDataError(
                        "Panel replay requires original Global ID and quantity."
                    )
                payload_global_id = int(payload["global_id"])
                payload_qty = int(payload["qty"])
                if (
                    payload_global_id != owner.global_id
                    or payload_qty != int(qty)
                ):
                    raise PanelPurchaseError(
                        "Idempotency-Key belongs to another panel "
                        "activation request."
                    )
                created_ids = [int(value) for value in ids]
                # Replay must be complete, owned by this Global ID and
                # consistent with immutable PNLs previously written to ledger.
                ledger_public_ids = payload.get("panels_public_ids")
                if not (
                    isinstance(ledger_public_ids, list)
                    and len(ledger_public_ids) == int(qty)
                    and all(isinstance(value, str) for value in ledger_public_ids)
                ):
                    raise PanelReplayMissingDataError(
                        "Panel replay requires the complete public PNL metadata."
                    )
                created_public_ids = await _panel_public_ids(
                    db, panel_ids=created_ids, global_id=owner.global_id
                )
                if created_public_ids != ledger_public_ids:
                    raise PanelReplayMissingDataError(
                        "Panel replay PNL metadata disagrees with stored panels."
                    )
                breakdown = SpendBreakdown(
                    bonus_part=d8(payload.get("spent_bonus") or "0"),
                    main_part=d8(payload.get("spent_main") or "0"),
                )
            else:
                total_user = d8(main_before + bonus_before)
                if total_user < d8("0"):
                    raise UserInDebtError(
                        "У пользователя отрицательный баланс: "
                        "активации за EFHC запрещены до выхода в 0."
                    )
                if current_active + qty > MAX_PANELS:
                    raise PanelLimitExceeded(
                        f"Лимит активных панелей {MAX_PANELS} "
                        "будет превышен."
                    )
                breakdown = split_bonus_then_main(
                    bonus_balance=bonus_before,
                    main_balance=main_before,
                    amount=d8(total_amount),
                )

            if not created_ids:
                created_ids = await _create_panel_records_bulk(
                    db,
                    global_id=owner.global_id,
                    qty=int(qty),
                )
                created_public_ids = await _panel_public_ids(
                    db, panel_ids=created_ids, global_id=owner.global_id
                )
                if current_active == 0:
                    on_first = (
                        referral_service.on_user_first_panel_activation
                    )
                    await on_first(
                        db,
                        buyer_global_id=owner.global_id,
                    )

            if status != "replay":
                # A replay is read-only: never rewrite original ledger provenance
                # or per-panel payment split timestamps.
                await _merge_activation_payload(
                    db,
                    idempotency_key=str(idempotency_key),
                    patch={
                        "audit__schema__version": "v2-global-owner",
                        "op_type": "PANEL_CREATE",
                        "global_id": owner.global_id,
                        "idempotency_key": str(idempotency_key),
                        "status": status,
                        "qty": int(qty),
                        "price_per_panel": str(d8(PANEL_PRICE)),
                        "total_amount": str(d8(total_amount)),
                        "spent_bonus": str(d8(breakdown.bonus_part)),
                        "spent_main": str(d8(breakdown.main_part)),
                        "bonus_first": True,
                        "panels_created_ids": created_ids,
                        "panels_public_ids": created_public_ids,
                        "panel_activation_atomicity": "true",
                    },
                )
                await _persist_activation_payment_splits(
                    db,
                    panel_ids=created_ids,
                    spent_bonus=d8(breakdown.bonus_part),
                    spent_main=d8(breakdown.main_part),
                    idempotency_key=str(idempotency_key),
                )

            if admin_actor_global_id is not None and status != "replay":
                from app.services.admin.admin_logging import AdminLogger

                await AdminLogger.write(
                    db,
                    actor_global_id=int(admin_actor_global_id),
                    action="ADMIN_PAID_PANEL_ACTIVATION",
                    entity="panel",
                    entity_id=int(created_ids[0]) if created_ids else None,
                    details=(
                        f"global_id={owner.global_id}; qty={qty}; "
                        f"price={d8(PANEL_PRICE)}; ik={idempotency_key}; "
                        f"comment={admin_reason or 'Admin активация панели'}"
                    ),
                    meta={
                        "spent_bonus": str(d8(breakdown.bonus_part)),
                        "spent_main": str(d8(breakdown.main_part)),
                        "bonus_first": True,
                        "source": "admin_user_ops",
                    },
                    required=True,
                )
    except ValueError as exc:
        logger.warning(
            "panel activation denied global_id=%s: %s",
            global_id,
            exc,
        )
        raise PanelPurchaseError(
            "Недостаточно EFHC для активации панелей без ухода в минус."
        ) from exc
    except PanelPurchaseError:
        raise
    except Exception as exc:
        logger.exception(
            "panel activation failed global_id=%s: %s",
            global_id,
            exc,
        )
        raise PanelPurchaseError(
            f"Ошибка создания панелей: {exc}"
        ) from exc

    return PurchaseResult(
        ok=True,
        qty=qty,
        total_spent_bonus=d8(breakdown.bonus_part),
        total_spent_main=d8(breakdown.main_part),
        created_panel_ids=created_ids,
        detail="Панели успешно активированы.",
    )



async def create_panel_for_user(
    db: AsyncSession,
    *,
    global_id: int,
    idempotency_key: str,
) -> dict[str, Any]:
    """Create one idempotent panel for canonical owner."""
    result = await activate_panel(
        db,
        global_id=int(global_id),
        qty=1,
        idempotency_key=str(idempotency_key),
    )
    if not result.created_panel_ids:
        raise PanelReplayMissingDataError("Missing created panel id")
    pid = int(result.created_panel_ids[0])
    public_ids = await _panel_public_ids(db, panel_ids=[pid], global_id=int(global_id))
    return {"id": pid, "public_id": public_ids[0]}



async def archive_panel_for_user(
    db: AsyncSession,
    *,
    global_id: int,
    panel_id: int,
) -> None:
    """Archive one panel owned by canonical account."""
    owner = await resolve_and_lock_financial_write_owner(
        db, global_id=int(global_id)
    )
    await db.execute(
        text(
            """
            UPDATE efhc_core.panels
            SET is_archived = TRUE,
                is_active = FALSE,
                archived_at = :now
            WHERE id = :panel_id
              AND global_id = :global_id
              AND COALESCE((meta ->> 'protectively_voided')::boolean, FALSE) = FALSE
            """
        ),
        {
            "panel_id": int(panel_id),
            "global_id": owner.global_id,
            "now": utcnow(),
        },
    )



# --------------------------------------------------------------------
# Витрины/списки для UI (курсорная пагинация)
# --------------------------------------------------------------------
async def list_active_panels(
    db: AsyncSession,
    *,
    global_id: int,
    limit: int = 25,
    cursor: str | None = None,
) -> PagedPanels:
    """Return active panels for the canonical owner."""
    return await list_user_panels(
        db,
        global_id=int(global_id),
        kind="active",
        limit=int(limit),
        cursor=cursor,
    )


async def list_user_panels(
    db: AsyncSession,
    *,
    global_id: int,
    kind: str,
    limit: int = 25,
    cursor: str | None = None,
) -> PagedPanels:
    """Return a canonical owner's active or archived panels."""
    limit = max(1, min(100, int(limit)))
    server_now_utc = utcnow()

    if hasattr(kind, "value"):
        kind = kind.value  # type: ignore
    kind = (kind or "").strip().lower()
    if kind not in ("active", "archive"):
        raise ValueError("Invalid kind")

    act_at = func.coalesce(Panel.activated_at, Panel.created_at)
    stmt = select(
        Panel.id,
        Panel.public_id,
        act_at.label("act_at"),
        Panel.expires_at,
        Panel.base_gen_per_sec,
        Panel.generated_kwh,
        Panel.archived_at,
    ).where(
        Panel.global_id == int(global_id),
        panel_is_operational_clause(),
    )

    if kind == "active":
        stmt = stmt.where(Panel.expires_at > server_now_utc)
    else:
        stmt = stmt.where(Panel.expires_at <= server_now_utc)

    if cursor:
        payload = decode_cursor(cursor)
        created_at_iso = payload.get("ts")
        last_id = int(payload.get("id") or 0)
        c_at = None
        if isinstance(created_at_iso, str) and created_at_iso:
            try:
                c_at = datetime.fromisoformat(created_at_iso)
            except Exception:
                c_at = None
        if c_at is not None and last_id > 0:
            stmt = stmt.where(
                tuple_(act_at, Panel.id) < (c_at, int(last_id))
            )

    stmt = stmt.order_by(desc(act_at), desc(Panel.id)).limit(
        int(limit) + 1
    )
    rows = (await db.execute(stmt)).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows[: int(limit)]:
        items.append(
            {
                "id": int(row.id),
                "public_id": str(row.public_id),
                "activated_at": _as_iso(row.act_at),
                "created_at": _as_iso(row.act_at),
                "expires_at": _as_iso(row.expires_at),
                "archived_at": _as_iso(row.archived_at),
                "remaining_seconds": _remaining_seconds(
                    row.expires_at, server_now_utc
                ),
                "base_gen_per_sec": d8(row.base_gen_per_sec),
                "generated_kwh": d8(row.generated_kwh),
                "is_active": bool(row.expires_at > server_now_utc),
            }
        )

    next_cursor = None
    if len(rows) > int(limit):
        last = rows[int(limit) - 1]
        next_cursor = encode_cursor(
            {"ts": _as_iso(last.act_at) or "", "id": int(last.id)}
        )
    return PagedPanels(items=items, next_cursor=next_cursor)


async def list_archived_panels(
    db: AsyncSession,
    *,
    global_id: int,
    limit: int = 25,
    cursor: str | None = None,
) -> PagedPanels:
    """Return archived panels for the canonical owner."""
    return await list_user_panels(
        db,
        global_id=int(global_id),
        kind="archive",
        limit=int(limit),
        cursor=cursor,
    )


async def panels_summary(
    db: AsyncSession,
    *,
    global_id: int,
) -> PanelsSummary:
    """Return the panel summary for one canonical account."""
    now_utc = utcnow()
    row = (
        await db.execute(
            text(
                """
                SELECT
                  COUNT(*) FILTER (WHERE expires_at > :now_utc),
                  COALESCE(SUM(generated_kwh), 0),
                  MIN(expires_at) FILTER (
                      WHERE expires_at > :now_utc
                  )
                FROM efhc_core.panels
                WHERE global_id = :global_id
                  AND COALESCE((meta ->> 'protectively_voided')::boolean, FALSE) = FALSE
                """
            ),
            {"global_id": int(global_id), "now_utc": now_utc},
        )
    ).fetchone()
    if row is None:
        return PanelsSummary(0, d8(0), None)
    return PanelsSummary(
        active_count=int(row[0] or 0),
        total_generated_by_panels=d8(row[1] or 0),
        nearest_expire_at=row[2],
    )


# --------------------------------------------------------------------
# Архивирование просроченных панелей (для планировщика)
# --------------------------------------------------------------------
async def archive_expired_panels(
    db: AsyncSession,
    *,
    limit: int = 1000,
) -> int:
    """
    Переводит просроченные панели в архив (is_active=false).
    Проставляет archived_at.
    Возвращает количество переведённых записей.

    Реализация через CTE + RETURNING.
      • выбираем порцию id под блокировку (SKIP LOCKED),
      • обновляем только эти записи,
      • считаем количество по числу возвращённых строк.
    """
    now = utcnow()
    r = await db.execute(
        text(
            """
            WITH cte AS (
                SELECT id
                FROM efhc_core.panels
                WHERE is_active = TRUE
                  AND expires_at <= :now
                  AND COALESCE((meta ->> 'protectively_voided')::boolean, FALSE) = FALSE
                ORDER BY id
                LIMIT :lim
                FOR UPDATE SKIP LOCKED
            )
            UPDATE efhc_core.panels AS p
               SET is_active = FALSE,
                   archived_at = :now
            FROM cte
            WHERE p.id = cte.id
            RETURNING p.id
            """
        ),
        {"now": now, "lim": int(limit)},
    )
    rows = r.fetchall()
    return len(rows)


# --------------------------------------------------------------------
# Вспомогательные
# --------------------------------------------------------------------


def _as_iso(dt: datetime | None) -> str | None:
    """ISO-строка в UTC (или None)."""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _remaining_seconds(
    expires_at: datetime | None,
    server_now_utc: datetime,
) -> int | None:
    """Остаток секунд панели по серверному времени."""
    if not expires_at:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if server_now_utc.tzinfo is None:
        server_now_utc = server_now_utc.replace(tzinfo=UTC)
    delta = expires_at.astimezone(UTC) - server_now_utc.astimezone(UTC)
    return max(0, int(delta.total_seconds()))


# =====================================================================
# Экспорт для import *
# =====================================================================
__all__ = [
    # исключения
    "PanelPurchaseError",
    "UserInDebtError",
    "PanelLimitExceeded",
    "IdempotencyRequiredError",
    # DTO
    "PurchaseResult",
    "PanelsSummary",
    "PagedPanels",
    # public API
    "activate_panel",
    "list_active_panels",
    "list_archived_panels",
    "panels_summary",
    "archive_expired_panels",
]

# =====================================================================
# Пояснения:
# • Почему списание «бонус→основной»? Канон: бонусы тратятся первыми.
#   Их номинал возвращается в Банк, чтобы не создавать скрытую эмиссию.
# • Почему панели хранят base_gen_per_sec?
#   Чтобы не зашивать VIP в запись.
#   За VIP отвечает energy_service.
# • Почему блокируем активации при историческом минусе?
#   Канон безопасности:
#   пользователь должен выйти из минуса сам (пополнение/обмен kWh→EFHC).
# • Почему суффиксы в idempotency_key "#i"? Чтобы qty>1 можно было
#   безопасно переисполнять без дублей при сетевых сбоях.
# • Почему курсоры? Курсорная пагинация стабильнее и дешевле OFFSET.
# =====================================================================
