# backend/app/services/exchange_service.py
# ----------------------------------------------------------------------
# EFHC Bot — Обмен доступной энергии (kWh) на EFHCm по фиксированному
# курсу 1:1
# ----------------------------------------------------------------------
# Назначение файла:
# • Предоставляет высокоуровневые функции обмена users.available_kwh →
# EFHC.
# • Гарантирует соблюдение канона: только однонаправленный обмен (kWh →
# EFHC),
# обратный путь ЗАПРЕЩЁН жёстко.
# • Делегирует все денежные операции ЕДИНОМУ банковскому сервису
# (backend/app/services/transactions_service.py) с идемпотентностью и
# запретом «минуса» у пользователей.
# • Содержит «ИИ»-защиту уровня сервиса: валидации, дружелюбные ошибки,
# вспомогательные проверки и «самоподсказки» для роутов/UI.
#
# Важные инварианты канона:
# 1) Курс внутренний фиксированный: 1 EFHC = 1 kWh (на уровне бота —
# неизменный).
# 2) Обмен только в одну сторону: kWh → EFHCm. Любая попытка обратной
# конверсии
# должна немедленно отклоняться ошибкой уровня сервиса.
# 3) Пользователь НИКОГДА не уходит в минус ни по EFHC, ни по kWh.
# Банк может уйти в минус (операции не блокируются).
# 4) Идемпотентность обязательна: после cutover ключ строится по
# global_id; до cutover сохраняется совместимый legacy key по global_id.
# 5) Все суммы — Decimal с 8 знаками после запятой (округление ВНИЗ)
# через
# deps.d8().
#
# SSOT Lock: total_generated_kwh is append-only.
# Обмен никогда не должен мутировать total_generated_kwh;
# разрешено менять только exchanged_kwh_total и зеркальный
# available_kwh.
# Для чайника:
# • Этот модуль — «диспетчер обмена». Он проверяет корректность запроса,
# а затем вызывает transactions_service.exchange_kwh_to_efhc(...) — это
# единственная функция, которая реально меняет EFHC-балансы в БД.
# • Если вы строите HTTP-эндпоинт, используйте request_exchange(...) и
# отдавайте его результат в JSON.
# • Для UI можно позвать preview_exchange(...) — там безопасно узнаете,
# сколько максимум можно обменять прямо сейчас (не делает списаний).
# ----------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.deps import d8
from app.models.user_models import User
from app.services.transactions_service import (
    append_transfer_meta,
    exchange__all__available_kwh_to_main,
    exchange_partial_available_kwh_to_main,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()

# ----------------------------------------------------------------------
# Точность и курс (канон)
# ----------------------------------------------------------------------

EFHC_DECIMALS: int = int(getattr(settings, "EFHC_DECIMALS", 8) or 8)

# Фиксированный курс 1:1 (канон). Храним для явной проверки/health.
KWH_TO_EFHC_RATE = Decimal(
    str(getattr(settings, "KWH_TO_EFHC_RATE", "1.0") or "1.0")
)
if Decimal("1") != KWH_TO_EFHC_RATE:
    # Каноническая защита от подмены курса в .env
    logger.warning(
        "KWH_TO_EFHC_RATE в .env не равен 1. Применяем 1:1 (канон)."
    )
    KWH_TO_EFHC_RATE = Decimal("1")

# ----------------------------------------------------------------------
# Специальные ошибки сервиса (для маршрутов/обработчиков)
# ----------------------------------------------------------------------


class ExchangeError(Exception):
    """Базовая ошибка обмена."""


class ExchangeValidationError(ExchangeError):
    """Ошибка валидации запроса (некорректные параметры)."""


class ExchangeDirectionForbidden(ExchangeError):
    """Попытка выполнить запрещённую операцию (EFHC → kWh)."""


class ExchangeInsufficientEnergy(ExchangeError):
    """Недостаточно доступной энергии для обмена."""


class ExchangeIdempotencyRequired(ExchangeError):
    """Нет idempotency_key при strict-режиме."""


# ----------------------------------------------------------------------
# Внутренние хелперы чтения пользователя
# ----------------------------------------------------------------------


async def _user_energy_snapshot(
    db: AsyncSession,
    *,
    global_id: int,
) -> dict[str, Decimal]:
    """Вернуть snapshot энергии canonical owner без блокировки."""

    owner = int(global_id)
    query = text(
        """
        SELECT COALESCE(total_generated_kwh, 0),
               COALESCE(exchanged_kwh_total, 0)
          FROM efhc_core.users
         WHERE global_id = :owner
        """
    )
    row = await db.execute(query, {"owner": owner})
    record = row.fetchone()
    if not record:
        raise ExchangeValidationError("Пользователь не найден")
    total = d8(record[0])
    exchanged_total = d8(record[1])
    available = d8(total - exchanged_total)
    if available < Decimal("0"):
        available = Decimal("0")
    return {
        "available_kwh": available,
        "total_generated_kwh": total,
        "exchanged_kwh_total": exchanged_total,
    }


# ----------------------------------------------------------------------
# Публичные функции сервиса
# ----------------------------------------------------------------------


@dataclass
class ExchangePreview:
    ok: bool
    available_kwh: Decimal
    max_exchangeable_kwh: Decimal
    rate_kwh_to_efhc: Decimal = Decimal("1")
    detail: str = ""


async def preview_exchange(
    db: AsyncSession,
    *,
    global_id: int,
) -> ExchangePreview:
    """
    Возвращает доступную энергию для обмена.
    Ничего не меняет в БД, пригодно для UI/подсказок.
    """
    snap = await _user_energy_snapshot(
        db,
        global_id=global_id,
    )
    avail = d8(snap["available_kwh"])
    return ExchangePreview(
        ok=True,
        available_kwh=avail,
        max_exchangeable_kwh=avail,  # курс 1:1, так что max = avail
        rate_kwh_to_efhc=KWH_TO_EFHC_RATE,
        detail="К обмену доступно только available_kwh (канон).",
    )


@dataclass
class ExchangeResult:
    ok: bool
    exchanged_kwh: Decimal
    credited_efhc: Decimal
    new__main__balance: Decimal
    new_available_kwh: Decimal
    log_id: int | None = None
    detail: str = ""
    idempotency_key: str | None = None


async def request_exchange(
    db: AsyncSession,
    *,
    global_id: int,
    amount_kwh: Any,
    idempotency_key: str | None,
) -> ExchangeResult:
    """
    Канонический публичный wrapper для
    частичного обмена available_kwh → EFHCm.

    Важно:
      • request_exchange не имеет права обходить
        exchange_kwh_to_efhc(...).
      • Возврат new_available_kwh должен
        читаться только из SSOT-состояния
        после транзакции, а не считаться
        «теоретически».
    """
    if not idempotency_key or not str(idempotency_key).strip():
        raise ExchangeIdempotencyRequired(
            "Отсутствует idempotency_key (обязателен)"
        )

    amt = d8(amount_kwh)
    if amt <= 0:
        raise ExchangeValidationError(
            "Сумма обмена должна быть больше 0"
        )

    try:
        return await exchange_kwh_to_efhc(
            db,
            global_id=global_id,
            amount_kwh=amt,
            idempotency_key=str(idempotency_key),
        )
    except Exception as e:
        msg = f"Не удалось выполнить обмен: {type(e).__name__}: {e}"
        logger.warning(
            "exchange_service.request_exchange failed "
            "(global_id=%s): %s",
            global_id,
            msg,
        )
        raise ExchangeError(msg) from e


async def _read_user_exchange_state(
    db: AsyncSession,
    *,
    global_id: int,
    for_update: bool = False,
) -> dict[str, Decimal]:
    condition = User.global_id == int(global_id)
    stmt = select(
        User.total_generated_kwh,
        User.exchanged_kwh_total,
        User.main_balance,
    ).where(condition)
    if for_update:
        stmt = stmt.with_for_update()

    result = await db.execute(stmt)
    record = result.first()
    if not record:
        raise ExchangeValidationError("Пользователь не найден")
    return {
        "total_generated_kwh": d8(record[0] or 0),
        "exchanged_kwh_total": d8(record[1] or 0),
        "main_balance": d8(record[2] or 0),
    }


async def _log_has_marker(
    db: AsyncSession,
    *,
    log_id: int,
    marker_key: str,
) -> bool:
    row = await db.execute(
        text(
            """
            SELECT COALESCE(meta, '{}'::jsonb)
            FROM efhc_core.efhc_transfers_log
            WHERE id = :lid
            """
        ),
        {"lid": int(log_id)},
    )
    rec = row.fetchone()
    if not rec:
        return False
    try:
        extra = rec[0] or {}
        return bool(extra.get(marker_key))
    except Exception:
        return False


async def _attach_exchange_audit(
    db: AsyncSession,
    *,
    log_id: int,
    audit: dict[str, Any],
) -> None:
    await append_transfer_meta(
        db,
        log_id=int(log_id),
        meta=dict(audit or {}),
    )


async def exchange_kwh_to_efhc(
    db: AsyncSession,
    *,
    global_id: int,
    amount_kwh: Decimal | None,
    idempotency_key: str,
) -> ExchangeResult:
    """Обмен available_kwh → EFHC MAIN по канону 1:1.

    Если amount_kwh не передан, выполняется EXCHANGE_ALL.
    Если amount_kwh передан, выполняется частичный
    обмен на точную сумму.
    """

    before_state = await _read_user_exchange_state(
        db,
        global_id=global_id,
    )
    total_before = d8(before_state["total_generated_kwh"])

    # HEAL-0018:
    # _read_user_exchange_state() is read-only, but SQLAlchemy
    # autobegin still opens a transaction. Close that read-only
    # boundary before transactions_service owns commit/rollback.
    if getattr(db, "in_transaction", None) and db.in_transaction():
        await db.rollback()

    if amount_kwh is None:
        tx = await exchange__all__available_kwh_to_main(
            db,
            global_id=global_id,
            idempotency_key=str(idempotency_key),
            reason="exchange_all",
        )
    else:
        tx = await exchange_partial_available_kwh_to_main(
            db,
            global_id=global_id,
            amount_kwh=d8(amount_kwh),
            idempotency_key=str(idempotency_key),
            reason="exchange_partial",
        )

    exchanged_amt = Decimal("0")
    log_id_val = int(getattr(tx, "created_log_id", 0) or 0)
    if log_id_val:
        row = await db.execute(
            text(
                """
                SELECT COALESCE(amount, 0)
                FROM efhc_core.efhc_transfers_log
                WHERE id = :lid
                """
            ),
            {"lid": int(log_id_val)},
        )
        exchanged_amt = d8(row.scalar() or 0)

    state = await _read_user_exchange_state(
        db,
        global_id=global_id,
    )
    total_after = d8(state["total_generated_kwh"])
    if total_after != total_before:
        raise ExchangeError(
            "Нарушение SSOT: total_generated_kwh изменился"
        )

    exchanged_total = d8(state["exchanged_kwh_total"])
    avail = d8(total_after - exchanged_total)
    if avail < Decimal("0"):
        avail = Decimal("0")

    return ExchangeResult(
        ok=bool(tx.ok),
        exchanged_kwh=d8(exchanged_amt if tx.ok else Decimal("0")),
        credited_efhc=d8(exchanged_amt if tx.ok else Decimal("0")),
        new__main__balance=d8(tx.user__main__balance),
        new_available_kwh=d8(avail),
        log_id=(int(log_id_val) or None),
        idempotency_key=str(idempotency_key),
        detail=(
            "Обмен выполнен (kWh→EFHCm 1:1)."
            if tx.ok
            else "Обмен отклонён."
        ),
    )


# ----------------------------------------------------------------------
# Жёсткий запрет обратной конверсии (EFHC → kWh)
# ----------------------------------------------------------------------


def forbid_reverse_exchange(*args, **kwargs) -> None:
    """
    Любая попытка добавить обратную конверсию должна
    заканчиваться ошибкой. Хук можно вызывать из system_locks.
    """
    raise ExchangeDirectionForbidden(
        "Обратная конверсия EFHC→kWh запрещена каноном"
    )


# ----------------------------------------------------------------------
# Дополнительные утилиты для UI/роутов
# ----------------------------------------------------------------------


async def max_exchangeable_kwh(
    db: AsyncSession,
    *,
    global_id: int,
) -> Decimal:
    """
    Возвращает максимум для обмена (available_kwh).
    """
    snap = await _user_energy_snapshot(
        db,
        global_id=global_id,
    )
    return cast(Decimal, d8(snap["available_kwh"]))


async def user_balances_brief(
    db: AsyncSession,
    *,
    global_id: int,
) -> dict[str, Decimal]:
    """Короткая сводка balances canonical owner."""

    owner = int(global_id)
    query = text(
        """
        SELECT COALESCE(main_balance, 0),
               COALESCE(bonus_balance, 0),
               COALESCE(available_kwh, 0),
               COALESCE(total_generated_kwh, 0)
          FROM efhc_core.users
         WHERE global_id = :owner
        """
    )
    row = await db.execute(query, {"owner": owner})
    record = row.fetchone()
    if not record:
        raise ExchangeValidationError("Пользователь не найден")
    return {
        "main_balance": d8(record[0]),
        "bonus_balance": d8(record[1]),
        "available_kwh": d8(record[2]),
        "total_generated_kwh": d8(record[3]),
    }


# ----------------------------------------------------------------------
# ИИ-поддержка/самодиагностика (лёгкая)
# ----------------------------------------------------------------------


async def health_snapshot(db: AsyncSession) -> dict[str, Any]:
    """
    Лёгкий «health» обменника:
      • пользователи с нулевым available_kwh (для статистики UI),
      • суммарная доступная энергия в системе,
      • метка канонического курса.
    Не тяжёлый запрос: считает агрегаты по users.
    """
    total_energy_row = await db.execute(
        text(
            "SELECT COALESCE(SUM(available_kwh),0) FROM efhc_core.users"
        )
    )
    total_energy = d8(total_energy_row.scalar() or 0)

    zero_users_row = await db.execute(
        text(
            "SELECT COUNT(*) FROM efhc_core.users "
            "WHERE COALESCE(available_kwh,0)=0"
        )
    )
    zero_users = int(zero_users_row.scalar() or 0)

    return {
        "total_available_kwh_system": total_energy,
        "users_with_zero_available": zero_users,
        "rate_kwh_to_efhc": KWH_TO_EFHC_RATE,
    }


# ----------------------------------------------------------------------
# Примеры использования (для разработчика)
# ----------------------------------------------------------------------
# from app.services import exchange_service as ex
#
# async def api_exchange(db, global_id: int, amount: str, idem: str):
# """
# Пример ручки/интеракции:
# • берём amount из запроса пользователя (строкой), idem — с клиента
# • пробуем выполнить обмен
# """
# try:
# res = await ex.request_exchange(
# db,
# global_id=global_id,
# amount_kwh=amount,
# idempotency_key=idem,
# )
# # success JSON:
# return {
# "ok": True,
# "exchanged_kwh": str(res.exchanged_kwh),
# "credited_efhc": str(res.credited_efhc),
# "new__main__balance": str(res.new__main__balance),
# "new_available_kwh": str(res.new_available_kwh),
# "idempotency_key": res.idempotency_key,
# }
# except ExchangeValidationError as ve:
# return {"ok": False, "error": "validation", "detail": str(ve)}
# except ExchangeInsufficientEnergy as ie:
# return {"ok": False, "error": "insufficient_energy", "detail":
# str(ie)}
# except ExchangeDirectionForbidden as df:
# return {"ok": False, "error": "forbidden", "detail": str(df)}
# except ExchangeError as ee:
# return {"ok": False, "error": "exchange_error", "detail": str(ee)}
# except Exception as e:
# # Непредвиденное — логируем и отдаём общий ответ
# logger.exception("api_exchange unexpected: %s", e)
# return {"ok": False, "error": "internal", "detail": "Временная ошибка,
# повторите попытку."}
# ----------------------------------------------------------------------

__all__ = [
    "ExchangeError",
    "ExchangeValidationError",
    "ExchangeDirectionForbidden",
    "ExchangeInsufficientEnergy",
    "ExchangeIdempotencyRequired",
    "ExchangePreview",
    "ExchangeResult",
    "preview_exchange",
    "request_exchange",
    "max_exchangeable_kwh",
    "user_balances_brief",
    "forbid_reverse_exchange",
    "health_snapshot",
]
