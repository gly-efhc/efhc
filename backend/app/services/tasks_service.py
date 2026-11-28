from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from app.core.config_core import get_settings
from app.core.errors_core import (
    NotFoundError,
    TasksError,
    ValidationError,
)
from app.core.logging_core import get_logger
from app.deps import d8
from app.identity.financial_write_owner import (
    FinancialWriteOwner,
    resolve_and_lock_financial_write_owner,
)
from app.identity.nonfinancial_owner import (
    NonFinancialReadOwner,
    resolve_nonfinancial_read_owner,
)
from app.integrations.telegram_bot_api import TelegramAPI
from app.lib.time import utcnow
from app.services.transactions_service import (
    credit_user_bonus_from_bank,
    credit_user_bonus_from_bank_nocommit,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SUPPORTED_TEMPLATE_LANGS = (
    "en",
    "ru",
    "uk",
    "de",
    "fr",
    "es",
    "it",
    "tr",
    "pl",
    "da",
    "hi",
    "id",
    "sw",
    "pt",
    "ko",
    "ja",
)

_TEMPLATE_DEFAULTS: dict[str, dict[str, str]] = {
    "task_approve_prefix": {
        "en": "✅ Task approved.",
        "ru": "✅ Задание подтверждено.",
        "uk": "✅ Завдання підтверджено.",
        "de": "✅ Aufgabe bestätigt.",
        "fr": "✅ Tâche confirmée.",
        "es": "✅ Tarea confirmada.",
        "it": "✅ Attività confermata.",
        "tr": "✅ Görev onaylandı.",
        "pl": "✅ Zadanie potwierdzone.",
        "da": "✅ Opgaven er bekræftet.",
        "hi": "✅ कार्य की पुष्टि हो गई।",
        "id": "✅ Tugas dikonfirmasi.",
        "sw": "✅ Kazi imethibitishwa.",
        "pt": "✅ Tarefa confirmada.",
        "ko": "✅ 작업이 확인되었습니다.",
        "ja": "✅ タスクが承認されました。",
    },
    "task_reject_prefix": {
        "en": "⚠️ Task rejected.",
        "ru": "⚠️ Задание отклонено.",
        "uk": "⚠️ Завдання відхилено.",
        "de": "⚠️ Aufgabe abgelehnt.",
        "fr": "⚠️ Tâche refusée.",
        "es": "⚠️ Tarea rechazada.",
        "it": "⚠️ Attività rifiutata.",
        "tr": "⚠️ Görev reddedildi.",
        "pl": "⚠️ Zadanie odrzucone.",
        "da": "⚠️ Opgaven blev afvist.",
        "hi": "⚠️ कार्य अस्वीकृत किया गया।",
        "id": "⚠️ Tugas ditolak.",
        "sw": "⚠️ Kazi imekataliwa.",
        "pt": "⚠️ Tarefa rejeitada.",
        "ko": "⚠️ 작업이 거절되었습니다.",
        "ja": "⚠️ タスクが却下されました。",
    },
    "task_approve_fallback": {
        "en": "Task result confirmed.",
        "ru": "Результат задания подтвержден.",
        "uk": "Результат завдання підтверджено.",
        "de": "Das Ergebnis der Aufgabe wurde bestätigt.",
        "fr": "Le résultat de la tâche a été confirmé.",
        "es": "El resultado de la tarea fue confirmado.",
        "it": "Il risultato dell'attività è stato confermato.",
        "tr": "Görev sonucu doğrulandı.",
        "pl": "Wynik zadania został potwierdzony.",
        "da": "Opgavens resultat er bekræftet.",
        "hi": "कार्य का परिणाम पुष्टि कर दिया गया है।",
        "id": "Hasil tugas telah dikonfirmasi.",
        "sw": "Matokeo ya kazi yamehakikishwa.",
        "pt": "Resultado da tarefa confirmado.",
        "ko": "작업 결과가 확인되었습니다.",
        "ja": "タスクの結果が確認されました。",
    },
    "task_reject_fallback": {
        "en": "Task result was not confirmed.",
        "ru": "Выполнение не подтверждено.",
        "uk": "Виконання не підтверджено.",
        "de": "Die Ausführung wurde nicht bestätigt.",
        "fr": "L'exécution n'a pas été confirmée.",
        "es": "La ejecución no fue confirmada.",
        "it": "L'esecuzione non è stata confermata.",
        "tr": "Tamamlama doğrulanmadı.",
        "pl": "Wykonanie nie zostało potwierdzone.",
        "da": "Udførelsen blev ikke bekræftet.",
        "hi": "कार्य पूरा होने की पुष्टि नहीं हुई।",
        "id": "Penyelesaian tidak dikonfirmasi.",
        "sw": "Utekelezaji haujathibitishwa.",
        "pt": "A conclusão não foi confirmada.",
        "ko": "작업 완료가 확인되지 않았습니다.",
        "ja": "タスクの完了は確認されませんでした。",
    },
}


async def _begin_tx(db: AsyncSession) -> None:
    if getattr(db, "in_transaction", None) and db.in_transaction():
        await db.begin_nested()
    else:
        await db.begin()


logger = get_logger(__name__)
settings = get_settings()

# ------------------------------------------------------------------
# Внутренние DTO для страниц
# ------------------------------------------------------------------


@dataclass
class TaskItem:
    task_code: str
    title: str
    description: str | None
    bonus_efhc: Decimal
    is_repeatable: bool
    # available | done | cooldown | pending_check | disabled
    user_status: str
    icon: str | None = None
    meta: dict[str, Any] | None = None


@dataclass
class TasksPage:
    items: list[TaskItem]
    next_after: dict[str, Any] | None


@dataclass
class TaskBonusLogItem:
    id: int
    ts: datetime
    task_code: str
    amount_bonus_efhc: Decimal
    idempotency_key: str


@dataclass
class TaskBonusLogPage:
    items: list[TaskBonusLogItem]
    next_after_id: int | None


# ------------------------------------------------------------------
# SQL — осознанно без ORM, ради прозрачности и контроля
# Таблицы (миграции должны это создать):
# • {schema}.tasks
# (task_code TEXT PK, title TEXT, description TEXT NULL,
# bonus_efhc NUMERIC(30,8), is_repeatable BOOL, is_active BOOL,
# cooldown_sec INT NULL, type TEXT, icon TEXT NULL, meta JSONB NULL)
# • {schema}.user_tasks_status
# (global_id BIGINT, task_code TEXT, status TEXT,
# last_completed_at TIMESTAMPTZ NULL,
# next_available_at TIMESTAMPTZ NULL, UNIQUE(global_id, task_code))
# • {schema}.task_bonus_log
# (id BIGSERIAL PK, global_id BIGINT, ts TIMESTAMPTZ, task_code TEXT,
# amount_bonus_efhc NUMERIC(30,8), idempotency_key TEXT UNIQUE)
# • {schema}.task_complete_lock
# Поля: id BIGSERIAL PK, idempotency_key TEXT UNIQUE,
# global_id BIGINT, task_code ...
# TEXT,
# created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ,
# credited BOOL DEFAULT FALSE)
# ------------------------------------------------------------------

_SQL_LIST_TASKS = text(
    """
            SELECT
        code AS task_code,
        title,
        description,
        bonus_efhc,
        CASE WHEN limit_per_user > 1 THEN TRUE ELSE FALSE END
            AS is_repeatable,
        active AS is_active,
        0 AS cooldown_sec,
        type,
        NULL::text AS icon,
        COALESCE(meta::jsonb, '{}'::jsonb) AS meta
      FROM efhc_core.tasks
     WHERE active = TRUE
       AND (
            CAST(:after_code AS TEXT) IS NULL
            OR code > CAST(:after_code AS TEXT)
       )
     ORDER BY code ASC
     LIMIT :lim
    """
)

_SQL_USER_TASK_STATUS = text(
    """
    SELECT status, last_completed_at, next_available_at
      FROM efhc_core.user_tasks_status
     WHERE task_code = :code
       AND global_id = :global_id
     LIMIT 1
    """
)

_SQL_USER_TASK_STATUSES = text(
    """
    SELECT task_code, status, last_completed_at, next_available_at
      FROM efhc_core.user_tasks_status
     WHERE global_id = :global_id
       AND task_code = ANY(CAST(:codes AS TEXT[]))
    """
)

_SQL_UPDATE_USER_TASK_STATUS = text(
    """
    UPDATE efhc_core.user_tasks_status
       SET status = :status,
           last_completed_at = :lca,
           next_available_at = :naa
     WHERE task_code = :code
       AND global_id = :global_id
    RETURNING id
    """
)

_SQL_INSERT_USER_TASK_STATUS = text(
    """
    INSERT INTO efhc_core.user_tasks_status
      (global_id, task_code, status, last_completed_at,
       next_available_at)
    VALUES (:global_id, :code, :status, :lca, :naa)
    ON CONFLICT (global_id, task_code) DO UPDATE
       SET status = EXCLUDED.status,
           last_completed_at = EXCLUDED.last_completed_at,
           next_available_at = EXCLUDED.next_available_at
    """
)

_SQL_INSERT_REWARD_LOG = text(
    """
    INSERT INTO efhc_core.task_bonus_log
      (global_id, ts, task_code, amount_bonus_efhc, idempotency_key)
    VALUES (:global_id, NOW(), :code, :amt, :idk)
    ON CONFLICT (idempotency_key) DO NOTHING
    """
)

_SQL_SELECT_REWARD_LOG_BY_IDK = text(
    """
    SELECT id, ts, task_code, amount_bonus_efhc, idempotency_key
      FROM efhc_core.task_bonus_log
     WHERE idempotency_key = :idk
     LIMIT 1
    """
)

_SQL_LIST_REWARD_LOG = text(
    """
    SELECT id, ts, task_code, amount_bonus_efhc, idempotency_key
      FROM efhc_core.task_bonus_log
     WHERE global_id = :global_id
       AND (
            CAST(:after_id AS BIGINT) IS NULL
            OR id < CAST(:after_id AS BIGINT)
       )
     ORDER BY id DESC
     LIMIT :lim
    """
)

_SQL_SUM_REWARD_LOG = text(
    """
    SELECT COALESCE(SUM(amount), 0)
      FROM efhc_core.efhc_transfers_log
     WHERE global_id = :global_id
       AND system_entity IS NULL
       AND direction = 'credit'
       AND balance_type = 'bonus'
       AND reason LIKE 'task_bonus:%'
    """
)

_SQL_LOCK_UPSERT = text(
    """
    INSERT INTO efhc_core.task_complete_lock
      (idempotency_key, global_id, task_code, created_at,
       updated_at, credited)
    VALUES (:idk, :global_id, :code, NOW(), NOW(), FALSE)
    ON CONFLICT (idempotency_key) DO UPDATE
       SET global_id = COALESCE(
               efhc_core.task_complete_lock.global_id,
               EXCLUDED.global_id
           ),
           updated_at = NOW()
    """
)

_SQL_LOCK_SELECT_FOR_UPDATE = text(
    """
    SELECT id, task_code, credited
      FROM efhc_core.task_complete_lock
     WHERE idempotency_key = :idk
     FOR UPDATE
    """
)

_SQL_LOCK_SET_CREDITED = text(
    """
            UPDATE efhc_core.task_complete_lock
       SET credited = TRUE, updated_at = NOW()
     WHERE idempotency_key = :idk
    """
)

_SQL_GET_TASK = text(
    """
            SELECT
        code AS task_code,
        title,
        description,
        bonus_efhc,
        CASE WHEN limit_per_user > 1 THEN TRUE ELSE FALSE END
            AS is_repeatable,
        active AS is_active,
        0 AS cooldown_sec,
        type,
        NULL::text AS icon,
        COALESCE(meta::jsonb, '{}'::jsonb) AS meta
      FROM efhc_core.tasks
     WHERE code = :code
     LIMIT 1
    """
)

# ------------------------------------------------------------------
# Вспомогательные функции
# ------------------------------------------------------------------


def _now_utc() -> datetime:
    """Возвращает текущее UTC-время."""
    return cast(datetime, utcnow())


def _as_task_item_row(row: Any, user_status: str) -> TaskItem:
    """Преобразует строку SQL-выборки в TaskItem."""
    return TaskItem(
        task_code=str(row[0]),
        title=str(row[1]),
        description=(row[2] if row[2] is not None else None),
        bonus_efhc=d8(row[3] or 0),
        is_repeatable=bool(row[4]),
        user_status=user_status,
        icon=(row[8] if row[8] is not None else None),
        meta=(row[9] if row[9] is not None else None),
    )


def _calc_user_status(
    base_status: str | None,
    next_available_at: datetime | None,
) -> str:
    """Нормализует статус пользователя."""
    if base_status == "pending_check":
        return "pending_check"
    if next_available_at and next_available_at > _now_utc():
        return "cooldown"
    return base_status or "available"


async def _resolve_task_read_owner(
    db: AsyncSession,
    *,
    global_id: int,
) -> NonFinancialReadOwner:
    return await resolve_nonfinancial_read_owner(
        db,
        global_id=int(global_id),
    )


async def _resolve_task_write_owner(
    db: AsyncSession,
    *,
    global_id: int,
) -> FinancialWriteOwner:
    return await resolve_and_lock_financial_write_owner(
        db,
        global_id=int(global_id),
    )


def _task_owner_params(*, global_id: int) -> dict[str, int]:
    return {"global_id": int(global_id)}


async def _upsert_user_task_status(
    db: AsyncSession,
    *,
    global_id: int,
    task_code: str,
    status: str,
    last_completed_at: datetime | None,
    next_available_at: datetime | None,
) -> None:
    params: dict[str, Any] = {
        **_task_owner_params(global_id=global_id),
        "code": task_code,
        "status": status,
        "lca": last_completed_at,
        "naa": next_available_at,
    }
    updated = await db.execute(
        _SQL_UPDATE_USER_TASK_STATUS,
        params,
    )
    if updated.first() is not None:
        return
    await db.execute(_SQL_INSERT_USER_TASK_STATUS, params)


# ------------------------------------------------------------------
# Публичное API сервиса — список заданий
# ------------------------------------------------------------------


async def list_available_tasks(
    db: AsyncSession,
    *,
    global_id: int,
    limit: int = 50,
    after: dict[str, Any] | None = None,
) -> TasksPage:
    """Вернуть задания по canonical owner без provider lock-in."""
    owner = await _resolve_task_read_owner(
        db,
        global_id=global_id,
    )
    owner_params = _task_owner_params(global_id=owner.global_id)
    lim = max(1, min(200, int(limit)))
    after_code = after.get("after_code") if after else None
    rows = (
        await db.execute(
            _SQL_LIST_TASKS,
            {"after_code": after_code, "lim": lim},
        )
    ).fetchall()
    codes = [str(row[0]) for row in rows]
    status_by_code: dict[str, tuple[Any, Any, Any]] = {}
    if codes:
        status_rows = (
            await db.execute(
                _SQL_USER_TASK_STATUSES,
                {**owner_params, "codes": codes},
            )
        ).fetchall()
        status_by_code = {
            str(row[0]): (row[1], row[2], row[3])
            for row in status_rows
        }

    items: list[TaskItem] = []
    last_code: str | None = None
    for row in rows:
        code = str(row[0])
        status_row = status_by_code.get(code)
        base_status = status_row[0] if status_row else None
        next_available = status_row[2] if status_row else None
        status = _calc_user_status(base_status, next_available)
        items.append(_as_task_item_row(row, status))
        last_code = code
    next_after = None
    if rows and len(rows) == lim:
        next_after = {"after_code": last_code}
    return TasksPage(items=items, next_after=next_after)


# ------------------------------------------------------------------
# Публичное API сервиса — завершение задания (join_channel/watch_ad)
# ------------------------------------------------------------------


async def complete_task(
    db: AsyncSession,
    *,
    global_id: int,
    task_code: str,
    proof: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    """Идемпотентно завершить задание canonical owner."""
    _ = proof
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    idk = idempotency_key.strip()
    owner = await _resolve_task_write_owner(
        db,
        global_id=global_id,
    )
    owner_params = _task_owner_params(global_id=owner.global_id)

    try:
        await _begin_tx(db)
        await db.execute(
            _SQL_LOCK_UPSERT,
            {
                **owner_params,
                "idk": idk,
                "code": task_code,
            },
        )
        lock = (
            await db.execute(
                _SQL_LOCK_SELECT_FOR_UPDATE,
                {"idk": idk},
            )
        ).fetchone()
        if not lock:
            await db.rollback()
            raise RuntimeError("failed to acquire tasks lock")
        if bool(lock[2]):
            await db.commit()
            previous = (
                await db.execute(
                    _SQL_SELECT_REWARD_LOG_BY_IDK,
                    {"idk": idk},
                )
            ).fetchone()
            if previous:
                return {
                    "ok": True,
                    "task_code": str(previous[2]),
                    "bonus_efhc": d8(previous[3] or 0),
                    "user_bonus_balance": None,
                    "replayed": True,
                }
            return {
                "ok": True,
                "task_code": task_code,
                "bonus_efhc": Decimal("0"),
                "user_bonus_balance": None,
                "replayed": True,
            }
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            logger.debug(
                "tasks_service: lock rollback failed",
                exc_info=True,
            )
        raise

    task_row = (
        await db.execute(_SQL_GET_TASK, {"code": task_code})
    ).fetchone()
    if not task_row:
        raise ValueError("task not found")
    if not bool(task_row[5]):
        raise ValueError("task is disabled")

    task_type = str(task_row[7] or "").strip()
    bonus_amount = d8(task_row[3] or 0)
    cooldown_sec = int(task_row[6] or 0)
    meta = task_row[9] or {}
    status_row = (
        await db.execute(
            _SQL_USER_TASK_STATUS,
            {**owner_params, "code": task_code},
        )
    ).fetchone()
    last_completed_at = status_row[1] if status_row else None
    next_available_at = status_row[2] if status_row else None
    if next_available_at and next_available_at > _now_utc():
        raise ValueError("task is in cooldown")
    if status_row and not bool(task_row[4]):
        raise ValueError("task is one-time and already completed")

    if task_type == "join_channel":
        if owner.provider_tg_id is None:
            raise ValueError("tg_provider_required")
        if (
            isinstance(meta, dict)
            and isinstance(meta.get("channels"), list)
        ):
            required = [
                str(item).strip()
                for item in meta["channels"]
                if str(item).strip()
            ]
        else:
            raw = getattr(settings, "REQUIRED_CHANNELS", "") or ""
            required = [
                item.strip()
                for item in raw.split(",")
                if item.strip()
            ]
        if not required:
            raise ValueError("task misconfigured: no channels")
        api = TelegramAPI()
        try:
            checks = await api.batch_is_user_subscribed(
                tg_id=owner.provider_tg_id,
                chats=required,
            )
        except Exception as err:
            logger.warning(
                "tasks_service: Telegram API failed",
                exc_info=True,
            )
            raise ValueError("telegram_api_unavailable") from err
        missing = [item.chat for item in checks if not item.subscribed]
        if missing:
            raise ValueError(
                "user is not subscribed to: " + ", ".join(missing)
            )
        return await _credit_bonus_and_finalize(
            db,
            global_id=owner.global_id,
            task_code=task_code,
            bonus_amount=bonus_amount,
            idempotency_key=idk,
            cooldown_sec=cooldown_sec,
        )

    if task_type == "watch_ad":
        await _upsert_user_task_status(
            db,
            global_id=owner.global_id,
            task_code=task_code,
            status="pending_check",
            last_completed_at=last_completed_at,
            next_available_at=None,
        )
        await db.commit()
        return {
            "ok": True,
            "task_code": task_code,
            "bonus_efhc": Decimal("0"),
            "user_bonus_balance": None,
            "replayed": False,
        }
    raise ValueError("unsupported task type")


# ------------------------------------------------------------------
# Публичное API — завершение рекламной сессии по колбэку провайдера
# ------------------------------------------------------------------


async def confirm_ad_view_and_credit(
    db: AsyncSession,
    *,
    global_id: int,
    task_code: str,
    provider: str,
    provider_ref: str,
    bonus_efhc: Decimal,
    idempotency_key: str,
) -> dict[str, Any]:
    """Начислить canonical owner бонус по callback провайдера."""
    _ = provider, provider_ref
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    idk = idempotency_key.strip()
    owner = await _resolve_task_write_owner(
        db,
        global_id=global_id,
    )
    owner_params = _task_owner_params(global_id=owner.global_id)
    try:
        await _begin_tx(db)
        await db.execute(
            _SQL_LOCK_UPSERT,
            {
                **owner_params,
                "idk": idk,
                "code": task_code,
            },
        )
        lock = (
            await db.execute(
                _SQL_LOCK_SELECT_FOR_UPDATE,
                {"idk": idk},
            )
        ).fetchone()
        if not lock:
            await db.rollback()
            raise RuntimeError("failed to acquire tasks lock")
        if bool(lock[2]):
            await db.commit()
            previous = (
                await db.execute(
                    _SQL_SELECT_REWARD_LOG_BY_IDK,
                    {"idk": idk},
                )
            ).fetchone()
            if previous:
                return {
                    "ok": True,
                    "task_code": str(previous[2]),
                    "bonus_efhc": d8(previous[3] or 0),
                    "user_bonus_balance": None,
                    "replayed": True,
                }
            return {
                "ok": True,
                "task_code": task_code,
                "bonus_efhc": Decimal("0"),
                "user_bonus_balance": None,
                "replayed": True,
            }
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            logger.debug(
                "tasks_service: ad rollback failed",
                exc_info=True,
            )
        raise

    task_row = (
        await db.execute(_SQL_GET_TASK, {"code": task_code})
    ).fetchone()
    if not task_row:
        raise ValueError("task not found")
    if not bool(task_row[5]):
        raise ValueError("task is disabled")
    if str(task_row[7] or "").strip() != "watch_ad":
        raise ValueError("task type mismatch for ad confirmation")
    return await _credit_bonus_and_finalize(
        db,
        global_id=owner.global_id,
        task_code=task_code,
        bonus_amount=d8(bonus_efhc or 0),
        idempotency_key=idk,
        cooldown_sec=int(task_row[6] or 0),
        completion_status="available",
    )


# ------------------------------------------------------------------
# Публичное API сервиса — история бонусов
# ------------------------------------------------------------------


async def list_task_bonus_log(
    db: AsyncSession,
    *,
    global_id: int,
    limit: int = 50,
    after_id: int | None = None,
) -> TaskBonusLogPage:
    """Вернуть историю task rewards canonical owner."""
    owner = await _resolve_task_read_owner(
        db,
        global_id=global_id,
    )
    params: dict[str, Any] = {
        **_task_owner_params(global_id=owner.global_id),
        "after_id": after_id,
        "lim": max(1, min(200, int(limit))),
    }
    rows = (
        await db.execute(_SQL_LIST_REWARD_LOG, params)
    ).fetchall()
    items: list[TaskBonusLogItem] = []
    last_id: int | None = None
    for row in rows:
        row_id, ts, code, amount, idk = row
        items.append(
            TaskBonusLogItem(
                id=int(row_id),
                ts=ts,
                task_code=str(code),
                amount_bonus_efhc=d8(amount or 0),
                idempotency_key=str(idk),
            )
        )
        last_id = int(row_id)
    next_id = None if len(rows) < int(params["lim"]) else last_id
    return TaskBonusLogPage(
        items=items,
        next_after_id=next_id,
    )

async def get_task_bonus_earned_total(
    db: AsyncSession,
    *,
    global_id: int,
) -> Decimal:
    """Вернуть lifetime EFHCb по Tasks/ADS из canonical reward ledger."""
    owner = await _resolve_task_read_owner(db, global_id=global_id)
    value = (
        await db.execute(
            _SQL_SUM_REWARD_LOG,
            _task_owner_params(global_id=owner.global_id),
        )
    ).scalar()
    return cast(Decimal, d8(value or 0))



async def _credit_bonus_and_finalize(
    db: AsyncSession,
    *,
    global_id: int,
    task_code: str,
    bonus_amount: Decimal,
    idempotency_key: str,
    cooldown_sec: int,
    completion_status: str | None = None,
) -> dict[str, Any]:
    """Кредитовать и финализировать task по canonical owner."""
    bonus = d8(bonus_amount or 0)
    await credit_user_bonus_from_bank(
        db=db,
        global_id=int(global_id),
        amount=bonus,
        reason=f"task_bonus:{task_code}",
        idempotency_key=idempotency_key,
        meta={"task_code": task_code},
    )
    await db.execute(
        _SQL_INSERT_REWARD_LOG,
        {
            **_task_owner_params(global_id=global_id),
            "code": task_code,
            "amt": str(bonus),
            "idk": idempotency_key,
        },
    )
    next_available = None
    if completion_status:
        status = str(completion_status)
    elif cooldown_sec > 0:
        next_available = _now_utc() + timedelta(
            seconds=int(cooldown_sec)
        )
        status = "cooldown"
    else:
        status = "done"
    await _upsert_user_task_status(
        db,
        global_id=global_id,
        task_code=task_code,
        status=status,
        last_completed_at=_now_utc(),
        next_available_at=next_available,
    )
    await db.execute(
        _SQL_LOCK_SET_CREDITED,
        {"idk": idempotency_key},
    )
    await db.commit()
    return {
        "ok": True,
        "task_code": task_code,
        "bonus_efhc": bonus,
        "user_bonus_balance": None,
        "replayed": False,
    }


# ----------------------------------------------------------------------
# Admin API (используется backend/app/routes/admin_tasks_routes.py)
# Канон:
# - LEGACY runtime: global_id используется до перехода задач.
#   Целевой owner key — канонический global_id.
# - Денежные начисления только через transactions_service (банк).
# - Для операций записи: обязательный commit().
# ----------------------------------------------------------------------

from app.models.tasks_models import (  # noqa: E402
    Task,
    TaskBonusLog,
    TaskCompleteLock,
    TaskSubmission,
    UserTaskStatus,
)
from sqlalchemy import select  # noqa: E402


class TaskDeleteBlockedError(RuntimeError):
    """Удаление задания заблокировано из-за сохранённой истории."""

    def __init__(self, blockers: dict[str, int]) -> None:
        self.blockers = blockers
        super().__init__("У задания есть связанная история")


class TaskCodeChangeBlockedError(RuntimeError):
    """Изменение task code заблокировано из-за сохранённой истории."""

    def __init__(self, blockers: dict[str, int]) -> None:
        self.blockers = blockers
        super().__init__("Код задания уже связан с историей")


async def _task_history_blockers(
    db: AsyncSession,
    *,
    task_id: int,
    task_code: str,
) -> dict[str, int]:
    """Вернуть счётчики истории, запрещающей destructive-операции."""
    checks = {
        "submissions": select(func.count(TaskSubmission.id)).where(
            TaskSubmission.task_id == int(task_id)
        ),
        "user_status": select(func.count(UserTaskStatus.global_id)).where(
            UserTaskStatus.task_code == str(task_code)
        ),
        "bonus_log": select(func.count(TaskBonusLog.id)).where(
            TaskBonusLog.task_code == str(task_code)
        ),
        "complete_locks": select(func.count(TaskCompleteLock.id)).where(
            TaskCompleteLock.task_code == str(task_code)
        ),
    }
    result: dict[str, int] = {}
    for key, stmt in checks.items():
        result[key] = int((await db.execute(stmt)).scalar_one() or 0)
    return result


def _task_admin_dict(obj: Task) -> dict[str, Any]:
    """Сериализовать полную canonical-модель задания для Admin UI."""
    return {
        "id": int(obj.id),
        "code": str(obj.code),
        "title": obj.title,
        "description": obj.description,
        "is_active": bool(obj.active),
        "bonus_efhc": str(d8(obj.bonus_efhc)),
        "kind": str(obj.type),
        "price_usd_hint": (
            str(d8(obj.price_usd_hint))
            if obj.price_usd_hint is not None
            else None
        ),
        "limit_per_user": int(obj.limit_per_user),
        "total_limit": (
            int(obj.total_limit) if obj.total_limit is not None else None
        ),
        "performed_count": int(obj.performed_count),
        "proof_type": obj.proof_type,
        "proof_hint": obj.proof_hint,
        "meta": obj.meta,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }


async def admin_create_task(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Создать задание из полной canonical Admin-модели."""
    code = str(payload.get("code") or "").strip()
    if not code:
        raise ValueError("code обязателен для нового задания")

    obj = Task(
        code=code,
        title=str(payload.get("title") or "").strip(),
        description=payload.get("description"),
        type=str(
            payload.get("kind") or payload.get("type") or "custom"
        ).strip(),
        active=bool(payload.get("is_active", True)),
        bonus_efhc=d8(
            payload.get("bonus_efhc")
            or settings.TASK_REWARD_BONUS_EFHC_DEFAULT
        ),
        price_usd_hint=(
            d8(payload["price_usd_hint"])
            if payload.get("price_usd_hint") not in (None, "")
            else None
        ),
        limit_per_user=int(payload.get("limit_per_user", 1)),
        total_limit=(
            int(payload["total_limit"])
            if payload.get("total_limit") not in (None, "")
            else None
        ),
        proof_type=payload.get("proof_type"),
        proof_hint=payload.get("proof_hint"),
        meta=payload.get("meta"),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _task_admin_dict(obj)


async def admin_get_task(
    db: AsyncSession,
    task_id: int,
) -> dict[str, Any] | None:
    """Получить полную Admin-модель задания."""
    stmt = select(Task).where(Task.id == int(task_id)).limit(1)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        return None
    return _task_admin_dict(row)


async def admin_list_tasks(
    db: AsyncSession,
    *,
    limit: int = 50,
    after: dict[str, Any] | None = None,
    q: str | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    """Получить каталог заданий с курсорной пагинацией."""
    lim = max(1, min(200, int(limit)))
    after_id = None
    if after and after.get("after_id") is not None:
        try:
            raw_after = after.get("after_id")
            after_id = None if raw_after is None else int(raw_after)
        except Exception:
            after_id = None

    stmt = select(Task).order_by(Task.id.desc()).limit(lim)
    if after_id is not None:
        stmt = stmt.where(Task.id < after_id)
    if q:
        qq = f"%{q.strip()}%"
        stmt = stmt.where(
            Task.title.ilike(qq) | Task.code.ilike(qq)
        )
    if active is not None:
        stmt = stmt.where(Task.active.is_(bool(active)))

    rows = (await db.execute(stmt)).scalars().all()
    items = [_task_admin_dict(t) for t in rows]
    last_id = int(rows[-1].id) if rows else None
    next_after = last_id if rows and len(rows) == lim else None
    return {"items": items, "next_after": next_after}


async def admin_update_task(
    db: AsyncSession,
    task_id: int,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Частично обновить задание без изменения runtime-статистики."""
    stmt = select(Task).where(Task.id == int(task_id)).with_for_update()
    t = (await db.execute(stmt)).scalar_one_or_none()
    if not t:
        return None

    if "code" in payload and payload["code"] is not None:
        new_code = str(payload["code"]).strip()
        if new_code and new_code != t.code:
            blockers = await _task_history_blockers(
                db,
                task_id=int(t.id),
                task_code=str(t.code),
            )
            if any(blockers.values()):
                raise TaskCodeChangeBlockedError(blockers)
            t.code = new_code
    if "title" in payload and payload["title"] is not None:
        t.title = str(payload["title"]).strip()
    if "description" in payload:
        t.description = payload.get("description")
    if "is_active" in payload and payload["is_active"] is not None:
        t.active = bool(payload["is_active"])
    if "bonus_efhc" in payload and payload["bonus_efhc"] is not None:
        t.bonus_efhc = d8(payload["bonus_efhc"])
    if "kind" in payload and payload["kind"] is not None:
        t.type = str(payload["kind"]).strip()
    if "price_usd_hint" in payload:
        raw_price = payload.get("price_usd_hint")
        t.price_usd_hint = (
            d8(raw_price) if raw_price not in (None, "") else None
        )
    if "limit_per_user" in payload and payload["limit_per_user"] is not None:
        t.limit_per_user = int(payload["limit_per_user"])
    if "total_limit" in payload:
        raw_total = payload.get("total_limit")
        t.total_limit = (
            int(raw_total) if raw_total not in (None, "") else None
        )
    if "proof_type" in payload:
        t.proof_type = payload.get("proof_type")
    if "proof_hint" in payload:
        t.proof_hint = payload.get("proof_hint")
    if "meta" in payload:
        t.meta = payload.get("meta")
    await db.commit()
    await db.refresh(t)
    return _task_admin_dict(t)


async def admin_delete_task(db: AsyncSession, task_id: int) -> bool:
    """Удалить только задание без какой-либо связанной истории."""
    stmt = select(Task).where(Task.id == int(task_id)).with_for_update()
    t = (await db.execute(stmt)).scalar_one_or_none()
    if not t:
        return False
    blockers = await _task_history_blockers(
        db,
        task_id=int(t.id),
        task_code=str(t.code),
    )
    if any(blockers.values()):
        raise TaskDeleteBlockedError(blockers)
    await db.delete(t)
    await db.commit()
    return True


async def admin_list_submissions(
    db: AsyncSession,
    *,
    task_id: int | None = None,
    limit: int = 50,
    after: dict[str, Any] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    lim = max(1, min(200, int(limit)))
    after_id = None
    if after and after.get("after_id") is not None:
        try:
            raw_after = after.get("after_id")
            after_id = None if raw_after is None else int(raw_after)
        except Exception:
            after_id = None
    stmt = (
        select(TaskSubmission)
        .order_by(TaskSubmission.id.desc())
        .limit(lim)
    )
    if after_id is not None:
        stmt = stmt.where(TaskSubmission.id < after_id)
    if task_id is not None:
        stmt = stmt.where(TaskSubmission.task_id == int(task_id))
    if status:
        stmt = stmt.where(TaskSubmission.status == str(status))
    rows = (await db.execute(stmt)).scalars().all()
    items = []
    last_id = None
    for s in rows:
        last_id = int(s.id)
        items.append(
            {
                "id": int(s.id),
                "task_id": int(s.task_id),
                "global_id": f"{int(s.global_id):010d}",
                "status": str(s.status),
                "proof_text": s.proof_text,
                "proof_url": s.proof_url,
                "submitted_at": s.created_at,
                "reviewed_at": (
                    None
                    if s.moderator_global_id is None
                    else s.updated_at
                ),
                "bonus_efhc": (
                    str(d8(s.bonus_amount_efhc))
                    if s.bonus_amount_efhc is not None
                    else None
                ),
                "moderator_global_id": (
                    f"{int(s.moderator_global_id):010d}"
                    if s.moderator_global_id is not None
                    else None
                ),
                "moderator_note": s.moderator_note,
            }
        )
    next_after = last_id if rows and len(rows) == lim else None
    return {"items": items, "next_after": next_after}


def _normalize_template_lang(lang: str | None) -> str:
    lc = str(lang or "").strip().lower()
    if lc.startswith("uk"):
        return "uk"
    if lc.startswith("ru"):
        return "ru"
    if lc.startswith("en"):
        return "en"
    if lc.startswith("de"):
        return "de"
    if lc.startswith("fr"):
        return "fr"
    if lc.startswith("es"):
        return "es"
    if lc.startswith("it"):
        return "it"
    if lc.startswith("tr"):
        return "tr"
    if lc.startswith("pl"):
        return "pl"
    if lc.startswith("da"):
        return "da"
    if lc.startswith("hi"):
        return "hi"
    if lc.startswith("id"):
        return "id"
    if lc.startswith("sw"):
        return "sw"
    if lc.startswith("pt"):
        return "pt"
    if lc.startswith("ko"):
        return "ko"
    if lc.startswith("ja"):
        return "ja"
    return "ru"


def _default_template_value(
    key: str,
    *,
    lang: str,
) -> str | None:
    variants = _TEMPLATE_DEFAULTS.get(str(key), {})
    return variants.get(lang) or variants.get("ru")


async def _get_user_template_lang(
    db: AsyncSession,
    *,
    global_id: int,
) -> str:
    row = (
        await db.execute(
            text(
                "SELECT meta FROM efhc_core.users "
                "WHERE global_id = :global_id LIMIT 1"
            ),
            {"global_id": int(global_id)},
        )
    ).first()
    if not row or not isinstance(row[0], dict):
        return "ru"
    meta = row[0]
    for key in (
        "lang",
        "language",
        "language_code",
        "ui_lang",
        "preferred_language",
    ):
        value = meta.get(key)
        if value:
            return _normalize_template_lang(str(value))
    return "ru"


async def _get_system_template(
    db: AsyncSession,
    *,
    key: str,
    lang: str | None = None,
) -> str | None:
    norm_lang = _normalize_template_lang(lang)
    search_keys = [f"{key}.{norm_lang}"]
    if norm_lang != "ru":
        search_keys.append(f"{key}.ru")
    search_keys.append(str(key))
    for lookup in search_keys:
        row = (
            await db.execute(
                text(
                    "SELECT content FROM efhc_core.system_templates "
                    "WHERE key = :key"
                ),
                {"key": lookup},
            )
        ).first()
        if not row:
            continue
        value = row[0]
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned:
            return cleaned
    return _default_template_value(str(key), lang=norm_lang)


async def _notify_task_submission(
    db: AsyncSession,
    *,
    global_id: int,
    recipient_tg_id: int | None,
    approved: bool,
    note: str | None,
) -> None:
    """Best-effort Telegram delivery; вызывается только после DB commit."""

    if not note:
        return
    try:
        from app.bot.bot import get_bot

        lang = await _get_user_template_lang(
            db,
            global_id=int(global_id),
        )
        if recipient_tg_id is None:
            row = (
                await db.execute(
                    text(
                        "SELECT provider_subject "
                        "FROM efhc_core.user_identities "
                        "WHERE global_id = :global_id "
                        "AND provider = 'telegram' "
                        "AND provider_tenant = 'default' "
                        "AND status = 'active' "
                        "AND is_verified = TRUE LIMIT 1"
                    ),
                    {"global_id": int(global_id)},
                )
            ).first()
            recipient_tg_id = (
                int(row[0]) if row and row[0] is not None else None
            )
        if recipient_tg_id is None:
            return
        prefix_key = (
            "task_approve_prefix" if approved else "task_reject_prefix"
        )
        prefix = await _get_system_template(
            db,
            key=prefix_key,
            lang=lang,
        )
        text_out = str(note) if not prefix else f"{prefix} {note}"
        bot = get_bot()
        await bot.send_message(
            chat_id=int(recipient_tg_id),
            text=text_out,
        )
    except Exception:
        logger.warning(
            "task moderation post-commit Telegram delivery failed",
            exc_info=True,
        )


async def moderate_submission_and_pay(
    db: AsyncSession,
    *,
    submission_id: int,
    approve: bool,
    moderator_global_id: int,
    moderator_note: str | None = None,
    bonus_override_efhc: Decimal | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Атомарно модерировать заявку и, при approve, выплатить EFHCb."""

    from app.services.admin.admin_logging import AdminLogger
    from app.services.admin.admin_notifications import AdminNotifier

    stmt = (
        select(TaskSubmission)
        .where(TaskSubmission.id == int(submission_id))
        .with_for_update()
    )
    sub = (await db.execute(stmt)).scalar_one_or_none()
    if not sub:
        raise ValueError("submission not found")
    if str(sub.status) in ("approved", "rejected") or bool(sub.paid):
        raise ValueError("submission already finalized")

    template_key = (
        "task_approve_fallback" if approve else "task_reject_fallback"
    )
    lang = await _get_user_template_lang(
        db,
        global_id=int(sub.global_id),
    )
    note = (moderator_note or "").strip() or await _get_system_template(
        db,
        key=template_key,
        lang=lang,
    )
    action = "TASK_SUBMISSION_APPROVE" if approve else "TASK_SUBMISSION_REJECT"
    event = "TASK_SUBMISSION_APPROVED" if approve else "TASK_SUBMISSION_REJECTED"
    notification_message = (
        f"Заявка задания #{int(sub.id)}: "
        f"{'подтверждена' if approve else 'отклонена'}"
    )
    notification_id: int | None = None

    if not approve:
        sub.status = "rejected"
        sub.moderator_global_id = int(moderator_global_id)
        sub.moderator_note = note
        await AdminLogger.write(
            db,
            actor_global_id=int(moderator_global_id),
            action=action,
            entity="task_submission",
            entity_id=int(sub.id),
            details=(
                f"task_id={int(sub.task_id)}; "
                f"idempotency_key={str(idempotency_key or '').strip()}"
            ),
            required=True,
        )
        notification_id = await AdminNotifier.notify_generic(
            db,
            event=event,
            message=notification_message,
            payload_json=(
                f'{{"submission_id":{int(sub.id)},'
                f'"task_id":{int(sub.task_id)},'
                f'"global_id":{int(sub.global_id)}}}'
            ),
            send_telegram=False,
        )
        await db.commit()
        await _notify_task_submission(
            db,
            global_id=int(sub.global_id),
            recipient_tg_id=(
                int(sub.tg_id) if sub.tg_id is not None else None
            ),
            approved=False,
            note=note,
        )
        try:
            await AdminNotifier.send_telegram_after_commit(
                notification_id=int(notification_id),
                event=event,
                message=notification_message,
            )
        except Exception:
            logger.warning(
                "task moderation Admin Telegram delivery failed",
                exc_info=True,
            )
        return {
            "ok": True,
            "status": "rejected",
            "proof_text": sub.proof_text,
            "proof_url": sub.proof_url,
            "submitted_at": sub.created_at,
            "reviewed_at": sub.updated_at,
            "bonus_efhc": (
                str(d8(sub.bonus_amount_efhc))
                if sub.bonus_amount_efhc is not None
                else None
            ),
            "moderator_global_id": f"{int(sub.moderator_global_id):010d}",
            "moderator_note": note,
            "task_id": int(sub.task_id),
            "global_id": f"{int(sub.global_id):010d}",
            "id": int(sub.id),
        }

    task = (
        await db.execute(
            select(Task)
            .where(Task.id == int(sub.task_id))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not task:
        raise ValueError("task not found for submission")
    if task.total_limit is not None and int(task.performed_count) >= int(task.total_limit):
        raise ValueError("task total limit reached")

    reward = d8(
        bonus_override_efhc
        if bonus_override_efhc is not None
        else task.bonus_efhc
    )
    idk = f"task_submission:{int(sub.id)}"
    if sub.global_id is None:
        raise RuntimeError("task submission global owner missing")

    task.performed_count = int(task.performed_count or 0) + 1
    res = await credit_user_bonus_from_bank_nocommit(
        db,
        global_id=int(sub.global_id),
        amount=reward,
        reason="task_bonus",
        idempotency_key=idk,
        meta={"task_id": int(task.id), "submission_id": int(sub.id)},
    )
    sub.status = "approved"
    sub.moderator_global_id = int(moderator_global_id)
    sub.bonus_amount_efhc = reward
    sub.paid = True
    sub.moderator_note = note
    sub.paid_tx_id = (
        int(res.created_log_id) if res.created_log_id is not None else None
    )

    await AdminLogger.write(
        db,
        actor_global_id=int(moderator_global_id),
        action=action,
        entity="task_submission",
        entity_id=int(sub.id),
        details=(
            f"task_id={int(task.id)}; amount={str(reward)}; "
            f"ledger_id={sub.paid_tx_id}; idempotency_key={idk}"
        ),
        required=True,
    )
    notification_id = await AdminNotifier.notify_generic(
        db,
        event=event,
        message=notification_message,
        payload_json=(
            f'{{"submission_id":{int(sub.id)},'
            f'"task_id":{int(task.id)},'
            f'"global_id":{int(sub.global_id)},'
            f'"paid_tx_id":{int(sub.paid_tx_id or 0)}}}'
        ),
        send_telegram=False,
    )
    await db.commit()

    await _notify_task_submission(
        db,
        global_id=int(sub.global_id),
        recipient_tg_id=(
            int(sub.tg_id) if sub.tg_id is not None else None
        ),
        approved=True,
        note=note,
    )
    try:
        await AdminNotifier.send_telegram_after_commit(
            notification_id=int(notification_id),
            event=event,
            message=notification_message,
        )
    except Exception:
        logger.warning(
            "task moderation Admin Telegram delivery failed",
            exc_info=True,
        )
    return {
        "ok": True,
        "status": "approved",
        "amount": str(reward),
        "proof_text": sub.proof_text,
        "proof_url": sub.proof_url,
        "submitted_at": sub.created_at,
        "reviewed_at": sub.updated_at,
        "bonus_efhc": str(reward),
        "moderator_global_id": f"{int(sub.moderator_global_id):010d}",
        "moderator_note": note,
        "task_id": int(sub.task_id),
        "global_id": int(sub.global_id),
        "id": int(sub.id),
    }


# ======================================================================
# Public (user) tasks API used by routes/tasks_routes.py
# Канон:
# - Денежные операции (начисление бонуса)
#   только через transactions_service.
# - Cursor pagination for lists.
# ======================================================================


import sqlalchemy as sa  # noqa: E402
from app.services import transactions_service  # noqa: E402
from sqlalchemy import (  # noqa: E402
    func,
    text,
)
from sqlalchemy.orm import aliased  # noqa: E402


async def list_tasks_catalog(
    db: AsyncSession,
    *,
    after_id: int | None,
    limit: int,
) -> tuple[list[dict[str, Any]], int | None]:
    q = (
        select(
            Task.id,
            Task.code,
            Task.title,
            Task.description,
            Task.bonus_efhc,
            Task.type,
            Task.meta,
        )
        .where(Task.active.is_(True))
        .order_by(Task.id.asc())
        .limit(int(limit))
    )
    if after_id is not None:
        q = q.where(Task.id > int(after_id))

    r = await db.execute(q)
    rows = r.all()
    items = [
        {
            "id": int(row[0]),
            "code": str(row[1]),
            "title": str(row[2]),
            "description": (
                str(row[3]) if row[3] is not None else None
            ),
            "bonus_efhc": row[4],
            "kind": str(row[5]) if row[5] is not None else None,
            "meta": row[6] if row[6] is not None else None,
            "is_active": True,
        }
        for row in rows
    ]
    next_after_id = int(rows[-1][0]) if rows else None
    return items, next_after_id


async def list_user_tasks(
    db: AsyncSession,
    *,
    global_id: int,
    after_id: int | None,
    limit: int,
) -> tuple[list[dict[str, Any]], int | None]:
    """Вернуть единый статус каждого задания для текущего пользователя.

    Модерируемые задания используют ``task_submissions``. Автоматические
    задания и рекламные награды используют ``user_tasks_status``. Публичная
    страница должна видеть оба контура после React Query refetch, иначе уже
    оплаченное рекламное задание может снова выглядеть доступным.
    """
    sub = aliased(TaskSubmission)
    runtime_status = aliased(UserTaskStatus)
    submission_owner = sub.global_id == int(global_id)
    status_owner = runtime_status.global_id == int(global_id)

    q = (
        select(
            Task.id.label("task_id"),
            Task.bonus_efhc.label("bonus_efhc"),
            sub.id.label("id"),
            sub.status.label("submission_status"),
            func.coalesce(sub.paid, sa.false()).label("paid"),
            runtime_status.status.label("runtime_status"),
            runtime_status.next_available_at.label("next_available_at"),
        )
        .select_from(Task)
        .outerjoin(
            sub,
            sa.and_(
                sub.task_id == Task.id,
                submission_owner,
            ),
        )
        .outerjoin(
            runtime_status,
            sa.and_(
                runtime_status.task_code == Task.code,
                status_owner,
            ),
        )
        .where(Task.active.is_(True))
        .order_by(Task.id.asc())
        .limit(int(limit))
    )
    if after_id is not None:
        q = q.where(Task.id > int(after_id))

    rows = (await db.execute(q)).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        submission_status = (
            str(row.submission_status)
            if row.submission_status is not None
            else None
        )
        runtime_value = (
            str(row.runtime_status)
            if row.runtime_status is not None
            else None
        )
        paid = bool(row.paid)
        if paid:
            status = "claimed"
        elif submission_status is not None:
            status = submission_status
        elif runtime_value is not None:
            status = runtime_value
        else:
            status = "not_started"
        can_claim = (
            submission_status in ("approved", "auto_paid") and not paid
        )
        items.append(
            {
                "id": int(row.id) if row.id is not None else None,
                "task_id": int(row.task_id),
                "status": status,
                "progress": None,
                "bonus_efhc": row.bonus_efhc,
                "can_claim": can_claim,
                "next_available_at": row.next_available_at,
            }
        )
    next_after_id = int(rows[-1].task_id) if rows else None
    return items, next_after_id


class _ClaimResult:
    def __init__(
        self,
        *,
        ok: bool,
        global_id: int,
        bonus_efhc: Decimal,
        user_bonus_balance: Decimal,
        user__main__balance: Decimal,
        detail: str | None = None,
    ):
        self.ok = ok
        self.global_id = global_id
        self.bonus_efhc = bonus_efhc
        self.user_bonus_balance = user_bonus_balance
        self.user__main__balance = user__main__balance
        self.detail = detail


async def claim_task_bonus(
    db: AsyncSession,
    *,
    global_id: int,
    task_id: int,
    idempotency_key: str,
) -> _ClaimResult:
    """Идемпотентно выдать approved task bonus canonical owner."""

    owner = await _resolve_task_write_owner(
        db,
        global_id=global_id,
    )
    task = await db.get(Task, int(task_id))
    if not task or not bool(task.active):
        raise NotFoundError(
            "Task not found", details={"task_id": int(task_id)}
        )

    q = (
        select(TaskSubmission)
        .where(
            TaskSubmission.task_id == int(task_id),
            TaskSubmission.global_id == int(owner.global_id),
        )
        .with_for_update()
    )
    sub = (await db.execute(q)).scalar_one_or_none()
    if not sub:
        raise TasksError(
            "Task not submitted",
            details={
                "task_id": int(task_id),
                "global_id": int(owner.global_id),
            },
        )

    if bool(sub.paid):
        main_balance, bonus_balance = (
            await transactions_service.get_user_balances_snapshot(
                db, global_id=owner.global_id
            )
        )
        return _ClaimResult(
            ok=True,
            global_id=owner.global_id,
            bonus_efhc=Decimal(str(sub.bonus_amount_efhc)),
            user_bonus_balance=bonus_balance,
            user__main__balance=main_balance,
            detail="already_paid",
        )

    if str(sub.status) not in ("approved", "auto_paid"):
        raise TasksError(
            "Submission is not approved",
            details={
                "task_id": int(task_id),
                "global_id": int(owner.global_id),
            },
        )

    reward = d8(
        sub.bonus_amount_efhc
        if sub.bonus_amount_efhc is not None
        else task.bonus_efhc
    )
    if reward <= Decimal("0"):
        raise ValidationError(
            "No bonus for this task", details={"task_id": int(task_id)}
        )

    tx = await transactions_service.credit_user_bonus_from_bank_nocommit(
        db,
        global_id=owner.global_id,
        amount=reward,
        idempotency_key=str(idempotency_key),
        reason="task_bonus",
        meta={"task_id": int(task_id), "submission_id": int(sub.id)},
    )
    sub.paid = True
    sub.paid_tx_id = (
        int(tx.created_log_id) if tx.created_log_id is not None else None
    )
    sub.bonus_amount_efhc = reward
    await db.commit()

    main_balance, bonus_balance = (
        await transactions_service.get_user_balances_snapshot(
            db, global_id=owner.global_id
        )
    )
    return _ClaimResult(
        ok=True,
        global_id=owner.global_id,
        bonus_efhc=reward,
        user_bonus_balance=bonus_balance,
        user__main__balance=main_balance,
        detail="ok",
    )

