# backend/app/services/efhc_deposits_service.py
# ----------------------------------------------------------------------
# EFHC Bot — приём внешних депозитов EFHC с блокчейна во внутренний банк
# бота
# ----------------------------------------------------------------------
# Назначение:
# • После того как вотчер увидел входящую on-chain транзакцию EFHC
# на проектный внешний кошелёк, этот сервис:
# 1) Однозначно привязывает её к пользователю бота.
# 2) Начисляет пользователю EFHC из центрального "банка EFHC"
# по курсу 1:1 (внутренняя транзакция).
# 3) Гарантирует идемпотентность по tx_hash (никаких дублей).
#
# Канон/инварианты:
# • Источник внутренних EFHC — только банк EFHC.
#   credit_user_from_bank(
#       ..., idempotency_key="deposit:efhc:<tx_hash>"
#   )
# • Пользователь НИКОГДА не уходит в минус. Банк МОЖЕТ (операции не
# блокируем).
# • Курс фиксированный: 1 EFHC on-chain = 1 EFHC внутри бота.
# • Идемпотентность:
# idempotency_key = "deposit:efhc:<tx_hash>"
# Повторная обработка той же транзакции НЕ создаёт повторных начислений.
# • Привязка к пользователю:
# 1) Если есть корректный MEMO → global_id.
# 2) Если MEMO нет/невалиден → по адресу отправителя через таблицу
# привязанных кошельков (WalletBinding).
# • Если пользователя определить нельзя — депозит НЕ зачисляется,
# возвращаем
# error=user_not_resolved (для ручной обработки в админке).
#
# Контекст использования:
# • Внешний TON-кошелёк проекта принимает EFHC от пользователя.
# • Старт этой транзакции инициируется нажатием кнопки в боте
# ("Пополнить EFHC"), но сервис депозитов этого не требует — ему важен
# факт
# on-chain транзакции.
# • Начальный баланс банка EFHC (например, 5_000_000 EFHC) создаётся
# миграцией
# или отдельным скриптом — здесь мы только уменьшаем банк/увеличиваем
# баланс пользователя через banking-сервис.
# ----------------------------------------------------------------------

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.deps import d8  # Decimal с 8 знаками, округление вниз
from app.identity.auth_provider import AuthProvider
from app.identity.types import (
    global_id_from_database,
    global_id_to_database,
    parse_global_id,
)
from app.identity.user_identities_storage_contract import (
    USER_IDENTITY_DEFAULT_TENANT,
)
from app.integrations.ton_api import TonAPIClient
from app.integrations.ton_memo import (
    MemoDepositEFHC,
    MemoDepositEFHCGlobal,
    parse_memo,
)
from app.lib.ton_address import (
    TonAddressError,
    canonicalize_ton_address,
)
from app.models.admin_models import IdempotencyKey
from app.models.identity_models import UserIdentity
from app.models.ton_logs_models import TonInboxLog
from app.models.user_models import User
from app.models.wallets_models import WalletBinding
from app.services import transactions_service as tx
from app.services.financial_execution_window import (
    validate_external_financial_execution,
)
from app.services.jetton_parsing_service import (
    parse_payment_intent_transport_from_tx,
)
from app.services.shop_payment_tx_hash_lock_service import (
    claim_tx_hash_settlement,
)
from app.standards.finance_rules import quantize_external_efhc_d2
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
DEPOSIT_IDEMPOTENCY_SCOPE = "deposit:efhc"
# HEAL-0055: deposit idempotency is an audit record,
# not a short HTTP-click lock. It must not expire automatically
# because on-chain replay/reconciliation can happen long after
# a serverless process has disappeared. Keep this constant
# explicit so future changes cannot silently reintroduce TTL.
DEPOSIT_IDEMPOTENCY_RETENTION_POLICY = "NON_EXPIRING"
DEPOSIT_IDEMPOTENCY_EXPIRES_AT = None


def _canonical_deposit_idempotency_key(tx_hash: str) -> str:
    """Build the long-retention deposit idempotency key.

    The canonical value remains ``deposit:efhc:<tx_hash>`` while it fits
    the efhc_admin.idempotency_key.key limit. If a watcher
    supplies an unusually long transaction hash, store a stable
    digest key instead of truncating the source value.
    """
    raw_hash = str(tx_hash or "").strip()
    raw_key = f"deposit:efhc:{raw_hash}"
    if len(raw_key) <= 128:
        return raw_key
    digest = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()
    return f"deposit:efhc:{digest}"


def _deposit_request_fingerprint(
    *,
    tx_hash: str,
    amount: Any,
    memo: str | None,
    from_address: str | None,
    to_address: str | None,
) -> str:
    """Return a stable fingerprint for a deposit watcher payload."""
    payload = {
        "amount": str(amount),
        "from_address": from_address,
        "memo": memo,
        "to_address": to_address,
        "tx_hash": str(tx_hash or "").strip(),
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def _read_deposit_idempotency_cache(
    db: AsyncSession,
    *,
    key: str,
    fingerprint: str,
) -> dict[str, Any] | None:
    """Read a stored long-retention deposit response, if any."""
    stmt = (
        select(
            IdempotencyKey.used,
            IdempotencyKey.request_fingerprint,
            IdempotencyKey.response_code,
            IdempotencyKey.response_payload_json,
        )
        .where(IdempotencyKey.key == str(key))
        .where(IdempotencyKey.scope == DEPOSIT_IDEMPOTENCY_SCOPE)
        .limit(1)
    )
    row = (await db.execute(stmt)).mappings().first()
    if not row:
        return None
    existing_fingerprint = row.get("request_fingerprint")
    if (
        existing_fingerprint
        and str(existing_fingerprint) != str(fingerprint)
    ):
        raise DepositError(
            "idempotency_fingerprint_mismatch: "
            "same deposit tx_hash was replayed with different payload"
        )

    payload = row.get("response_payload_json")
    if bool(row.get("used")) and isinstance(payload, dict):
        cached = dict(payload)
        cached.setdefault("idempotency_key", str(key))
        cached["detail"] = "idempotent_deposit_cache"
        return cached
    return None


async def _reserve_deposit_idempotency_key(
    db: AsyncSession,
    *,
    key: str,
    fingerprint: str,
) -> None:
    """Persist a non-expiring EFHC deposit idempotency record."""
    stmt = (
        pg_insert(IdempotencyKey)
        .values(
            key=str(key),
            scope=DEPOSIT_IDEMPOTENCY_SCOPE,
            request_fingerprint=str(fingerprint),
            used=False,
            expires_at=DEPOSIT_IDEMPOTENCY_EXPIRES_AT,
        )
        .on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
    )
    await db.execute(stmt)


async def _store_deposit_idempotency_response(
    db: AsyncSession,
    *,
    key: str,
    fingerprint: str,
    response: dict[str, Any],
    response_code: int = 200,
) -> None:
    """Сохраняет первый ответ депозита без владения transaction boundary."""
    payload = json.loads(
        json.dumps(
            response,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    )
    stmt = (
        update(IdempotencyKey)
        .where(IdempotencyKey.key == str(key))
        .values(
            scope=DEPOSIT_IDEMPOTENCY_SCOPE,
            request_fingerprint=str(fingerprint),
            used=True,
            response_code=int(response_code),
            response_payload_json=payload,
            expires_at=DEPOSIT_IDEMPOTENCY_EXPIRES_AT,
        )
    )
    await db.execute(stmt)


# ----------------------------------------------------------------------
# Ошибки и утилиты
# ----------------------------------------------------------------------


class DepositError(Exception):
    """Ошибка сервиса депозитов EFHC (для UI/логов, не про деньги)."""


def _external_efhc_from_transport_meta(
    raw_meta: dict[str, Any] | None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Восстановить exact EFHC jetton amount из transport-v2 evidence."""
    meta = raw_meta or {}
    if int(meta.get("transport_version") or 0) < 2:
        raise DepositError("EFHC_DEPOSIT_TRANSPORT_V2_REQUIRED")
    if str(meta.get("financial_asset") or "").upper() != "EFHC":
        raise DepositError("EFHC_DEPOSIT_TRANSPORT_ASSET_INVALID")
    try:
        amount_atomic = int(str(meta["amount_atomic"]).strip())
        token_decimals = int(str(meta["token_decimals"]).strip())
    except (KeyError, TypeError, ValueError) as exc:
        raise DepositError("EFHC_DEPOSIT_TRANSPORT_AMOUNT_INVALID") from exc
    if amount_atomic < 0 or not 0 <= token_decimals <= 18:
        raise DepositError("EFHC_DEPOSIT_TRANSPORT_AMOUNT_INVALID")
    raw_external_efhc = Decimal(amount_atomic) / (Decimal(10) ** token_decimals)
    credited_external_efhc = quantize_external_efhc_d2(raw_external_efhc)
    dec_amount = d8(credited_external_efhc)
    rounding_dust = raw_external_efhc - credited_external_efhc
    return dec_amount, raw_external_efhc, rounding_dust


async def _refetch_legacy_efhc_transport_meta(
    *,
    tx_hash: str,
    created_at: Any,
) -> dict[str, Any] | None:
    """Best-effort authoritative refetch для legacy row без transport-v2 meta."""
    settings = get_settings()
    wallet = str(getattr(settings, "TON_MAIN_WALLET", "") or "").strip()
    if not wallet:
        return None
    since_utime: int | None = None
    if created_at is not None and hasattr(created_at, "timestamp"):
        try:
            since_utime = max(0, int(created_at.timestamp()) - 86400)
        except (OverflowError, OSError, TypeError, ValueError):
            since_utime = None
    try:
        events = await TonAPIClient().get_incoming_payments(
            wallet,
            limit=500,
            since_utime=since_utime,
        )
    except Exception as exc:
        logger.warning(
            "EFHC emergency deposit refetch failed for %s: %s",
            tx_hash,
            type(exc).__name__,
        )
        return None
    for event in events:
        if str(event.tx_hash) != tx_hash:
            continue
        parsed = parse_payment_intent_transport_from_tx(tx=event)
        decision = parsed.decision
        if decision.confirm_asset != "EFHCJ":
            raise DepositError("EFHC_DEPOSIT_TRANSPORT_ASSET_INVALID")
        return {
            "transport_version": 2,
            "asset": str(getattr(event, "asset", "JETTON") or "JETTON"),
            "financial_asset": "EFHC",
            "jetton_master": str(getattr(event, "jetton_master", "") or ""),
            "amount_atomic": str(int(decision.amount_atomic)),
            "token_decimals": int(decision.atomic_decimals),
            "provider": "tonapi_refetch",
        }
    return None


def _as_decimal(value: Any) -> Decimal:
    """Безопасно привести к Decimal."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DepositError(
            "Некорректное числовое значение amount"
        ) from exc


@dataclass
class ResolvedUser:
    global_id: str
    provider_tg_id: int | None = None


async def _telegram_subject_for_global_id(
    db: AsyncSession,
    global_id: int,
) -> int | None:
    subject = await db.scalar(
        select(UserIdentity.provider_subject)
        .where(
            UserIdentity.global_id == int(global_id),
            UserIdentity.provider == AuthProvider.TELEGRAM.value,
            UserIdentity.provider_tenant == USER_IDENTITY_DEFAULT_TENANT,
            UserIdentity.status == "active",
            UserIdentity.is_verified.is_(True),
        )
        .limit(1)
    )
    if subject is None:
        return None
    try:
        return int(subject)
    except (TypeError, ValueError):
        return None


async def _global_id_for_telegram_subject(
    db: AsyncSession,
    telegram_subject: int,
) -> int | None:
    value = await db.scalar(
        select(UserIdentity.global_id)
        .where(
            UserIdentity.provider == AuthProvider.TELEGRAM.value,
            UserIdentity.provider_tenant == USER_IDENTITY_DEFAULT_TENANT,
            UserIdentity.provider_subject == str(int(telegram_subject)),
            UserIdentity.status == "active",
            UserIdentity.is_verified.is_(True),
        )
        .limit(1)
    )
    return int(value) if value is not None else None


async def _resolved_user_from_global_id(
    db: AsyncSession,
    global_id: int,
) -> ResolvedUser | None:
    stored_global_id = await db.scalar(
        select(User.global_id)
        .where(User.global_id == int(global_id))
        .limit(1)
    )
    if stored_global_id is None:
        return None
    return ResolvedUser(
        global_id=str(global_id_from_database(stored_global_id)),
        provider_tg_id=await _telegram_subject_for_global_id(
            db, int(stored_global_id)
        ),
    )


async def _resolve_user_by_memo(
    db: AsyncSession,
    memo: str | None,
) -> ResolvedUser | None:
    """Разрешить canonical memo и historical Telegram memo."""
    if not memo:
        return None
    memo_text = str(memo).strip()
    parsed = parse_memo(memo_text)
    if isinstance(parsed, MemoDepositEFHCGlobal):
        global_id = global_id_to_database(
            parse_global_id(parsed.global_id)
        )
    elif isinstance(parsed, MemoDepositEFHC):
        resolved_global_id = await _global_id_for_telegram_subject(
            db, int(parsed.tg_id)
        )
        if resolved_global_id is None:
            return None
        global_id = resolved_global_id
    elif memo_text.isdigit():
        # Historical read-through: bare numeric memo was Telegram ID.
        resolved_global_id = await _global_id_for_telegram_subject(
            db, int(memo_text)
        )
        if resolved_global_id is None:
            return None
        global_id = resolved_global_id
    else:
        return None
    return await _resolved_user_from_global_id(db, int(global_id))


async def _resolve_user_by_wallet(
    db: AsyncSession,
    from_address: str | None,
) -> ResolvedUser | None:
    """Разрешить active verified wallet binding в canonical account."""
    if not from_address:
        return None
    addr_raw = str(from_address).strip()
    if not addr_raw:
        return None
    try:
        addr_norm = canonicalize_ton_address(addr_raw)
    except TonAddressError:
        addr_norm = addr_raw
    resolved_global_id = await db.scalar(
        select(WalletBinding.global_id)
        .where(
            WalletBinding.wallet_address == addr_norm,
            WalletBinding.is_active.is_(True),
            WalletBinding.proof_verified.is_(True),
        )
        .order_by(WalletBinding.id.asc())
        .limit(1)
    )
    if resolved_global_id is None:
        return None
    return await _resolved_user_from_global_id(
        db, int(resolved_global_id)
    )


async def _resolve_deposit_user(
    db: AsyncSession,
    *,
    memo: str | None,
    from_address: str | None,
) -> ResolvedUser | None:
    """Сначала разрешить владельца по memo, затем по кошельку."""
    user = await _resolve_user_by_memo(db, memo)
    if user:
        return user
    return await _resolve_user_by_wallet(db, from_address)


# ----------------------------------------------------------------------
# Основная функция приёма депозита EFHC
# ----------------------------------------------------------------------


async def process_efhc_deposit(
    db: AsyncSession,
    *,
    tx_hash: str,
) -> dict[str, Any]:
    """Аварийно обработать уже материализованную on-chain операцию.

    Admin-клиент не является источником суммы, MEMO, адресов или owner.
    Все факты читаются только из ``efhc_core.ton_inbox_logs`` под
    ``FOR UPDATE``. Если watcher не материализовал транзакцию, ручное
    начисление под видом депозита запрещено.

    Денежный write выполняется через ``*_nocommit``: корневая transaction
    принадлежит Admin route, который обязан записать audit и только затем
    выполнить единый commit.
    """
    tx_hash = str(tx_hash or "").strip()
    if not tx_hash:
        raise DepositError("tx_hash обязателен для идемпотентности")

    inbox_result = await db.execute(
        select(TonInboxLog)
        .where(TonInboxLog.tx_hash == tx_hash)
        .with_for_update()
    )
    inbox = inbox_result.scalar_one_or_none()
    if inbox is None:
        return {
            "ok": False,
            "error": "materialized_tx_not_found",
            "detail": (
                "On-chain транзакция не найдена во входящем журнале; "
                "ручное создание депозита запрещено."
            ),
            "tx_hash": tx_hash,
            "amount": "0",
            "source": "ton_inbox_required",
        }

    memo = inbox.memo
    from_address = inbox.from_address
    to_address = inbox.to_address
    raw_tx = inbox.meta if isinstance(inbox.meta, dict) else None

    time_decision = validate_external_financial_execution(
        trusted_operation_at=inbox.trusted_operation_at,
        server_first_seen_at=inbox.created_at,
    )
    if not time_decision.allowed:
        return {
            "ok": False,
            "error": (
                "financial_execution_expired"
                if time_decision.expired
                else "financial_time_untrusted"
            ),
            "detail": time_decision.code,
            "tx_hash": tx_hash,
            "amount": "0",
            "source": "ton_inbox_materialized",
        }

    if not raw_tx or int(raw_tx.get("transport_version") or 0) < 2:
        refetched_meta = await _refetch_legacy_efhc_transport_meta(
            tx_hash=tx_hash,
            created_at=inbox.created_at,
        )
        if refetched_meta is None:
            raise DepositError("EFHC_DEPOSIT_TRANSPORT_EVIDENCE_REQUIRED")
        raw_tx = refetched_meta

    dec_amount, raw_external_efhc, rounding_dust = (
        _external_efhc_from_transport_meta(raw_tx)
    )
    if dec_amount <= Decimal("0"):
        raise DepositError("Материализованная сумма EFHC должна быть > 0")

    idem_key = _canonical_deposit_idempotency_key(tx_hash)
    fingerprint = _deposit_request_fingerprint(
        tx_hash=tx_hash,
        amount=str(dec_amount),
        memo=memo,
        from_address=from_address,
        to_address=to_address,
    )
    cached = await _read_deposit_idempotency_cache(
        db,
        key=idem_key,
        fingerprint=fingerprint,
    )
    if cached is not None:
        return cached
    await _reserve_deposit_idempotency_key(
        db,
        key=idem_key,
        fingerprint=fingerprint,
    )

    resolved: ResolvedUser | None
    if inbox.resolved_global_id is not None:
        resolved = ResolvedUser(
            global_id=str(global_id_from_database(inbox.resolved_global_id)),
            provider_tg_id=(
                int(inbox.parsed_tg_id)
                if inbox.parsed_tg_id is not None
                else None
            ),
        )
    else:
        resolved = await _resolve_deposit_user(
            db,
            memo=memo,
            from_address=from_address,
        )

    if not resolved:
        response = {
            "ok": False,
            "error": "user_not_resolved",
            "detail": (
                "Пользователь не найден по материализованным данным "
                "входящей операции."
            ),
            "tx_hash": tx_hash,
            "amount": str(dec_amount),
            "memo": memo,
            "from_address": from_address,
            "to_address": to_address,
            "idempotency_key": idem_key,
            "source": "ton_inbox_materialized",
        }
        await _store_deposit_idempotency_response(
            db,
            key=idem_key,
            fingerprint=fingerprint,
            response=response,
            response_code=200,
        )
        return response

    global_id = resolved.global_id
    provider_tg_id = resolved.provider_tg_id
    claim = await claim_tx_hash_settlement(
        db,
        tx_hash=tx_hash,
        purpose="admin_efhc_deposit",
        global_id=global_id,
        trusted_operation_at=time_decision.trusted_operation_at,
        server_first_seen_at=time_decision.server_first_seen_at,
    )
    if not claim.can_continue:
        response = {
            "ok": False,
            "error": "settlement_already_claimed",
            "detail": (
                "Эта blockchain-транзакция уже заявлена другим "
                "settlement-контуром и не может быть начислена повторно."
            ),
            "tx_hash": tx_hash,
            "amount": str(dec_amount),
            "global_id": global_id,
            "provider_tg_id": provider_tg_id,
            "from_address": from_address,
            "to_address": to_address,
            "memo": memo,
            "idempotency_key": idem_key,
            "source": "ton_inbox_materialized",
        }
        await _store_deposit_idempotency_response(
            db,
            key=idem_key,
            fingerprint=fingerprint,
            response=response,
            response_code=409,
        )
        return response

    meta: dict[str, Any] = {
        "domain": "efhc_external_deposit",
        "tx_hash": tx_hash,
        "from_address": from_address,
        "to_address": to_address,
        "memo": memo,
        "global_id": global_id,
        "provider_tg_id": provider_tg_id,
        "external_settlement": "received",
        "settlement_status": "confirmed",
        "bank_counterparty": "BANK_EFHC",
        "raw_external_efhc": str(raw_external_efhc),
        "credited_external_efhc": str(quantize_external_efhc_d2(raw_external_efhc)),
        "rounding_dust_efhc": str(rounding_dust),
        "external_rounding": "D2_ROUND_DOWN",
        "source": "admin_emergency_deposit",
    }
    if raw_tx is not None:
        meta["ton_inbox_meta"] = raw_tx

    try:
        tx_result = await tx.credit_user_from_bank_nocommit(
            db=db,
            global_id=global_id_to_database(parse_global_id(global_id)),
            amount=dec_amount,
            reason="efhc_external_deposit",
            idempotency_key=idem_key,
            meta=meta,
        )
    except Exception as exc:
        raise DepositError(
            f"Не удалось зачислить EFHC: {type(exc).__name__}: {exc}"
        ) from exc

    response = {
        "ok": True,
        "tx_hash": tx_hash,
        "amount": str(dec_amount),
        "global_id": global_id,
        "provider_tg_id": provider_tg_id,
        "from_address": from_address,
        "to_address": to_address,
        "memo": memo,
        "idempotency_key": idem_key,
        "new__main__balance": str(d8(tx_result.user__main__balance)),
        "new_bonus_balance": str(d8(tx_result.user_bonus_balance)),
        "source": "ton_inbox_materialized",
    }
    await _store_deposit_idempotency_response(
        db,
        key=idem_key,
        fingerprint=fingerprint,
        response=response,
        response_code=200,
    )
    return response


# ----------------------------------------------------------------------
# Схематический пример интеграции с watcher:
# ----------------------------------------------------------------------
# async def обработать_новый_перевод(tx):
# async with db_session() as db:
# внутри db.begin():
# результат = await process_efhc_deposit(
# db,
# tx_hash=tx.hash,
# amount=tx.amount,        # Decimal или строка
# memo=tx.comment,         # может быть None
# from_address=tx.from_addr,
# to_address=tx.to_addr,
# raw_tx=tx.to_dict(),     # опционально
# )
# # result["ok"] / result["error"] можно использовать для
# уведомлений/логов.
#
# Стартовый баланс банка EFHC (например, 5_000_000 EFHC) должен быть
# задан
# миграцией/скриптом в таблице банка (см. transactions_service и
# описание
# Банка).
# ----------------------------------------------------------------------

__all__ = [
    "DepositError",
    "process_efhc_deposit",
]
