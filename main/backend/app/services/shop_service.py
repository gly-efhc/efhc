# backend/app/services/shop_service.py
# ====================================================================
# Назначение кода:
# Сервис магазина EFHC: каталожные позиции (сидер), витрины,
# создание заказов, генерация MEMO для внешних платежей
# (TON/USDT), внутренняя оплата EFHC (списание: сначала bonus,
# затем main), интеграция с Банком и Вотчером.
#
# Канон/инварианты:
# • Обмен только kWh→EFHC (1:1), обратной конверсии нет.
# • P2P запрещено. Любые движения EFHC — только «банк ↔ пользователь».
# • NFT — только заявка и ручная обработка.
# • EFHC-пакеты оплачиваются только внешне (TON/USDT).
#   Мы создаём заказ PENDING и генерируем MEMO.
#   оплата за EFHC запрещена.
# • Денежные POST — обязателен Idempotency-Key / client_nonce.
# • Пользователь не уходит в минус. Банк может (дефицит не блокирует).
#
# ИИ-защита/самовосстановление:
# • Идемпотентность: конфликт idempotency_key → вернуть
#   зафиксированный результат из логов; повторный вызов безопасен.
# • Лог-ориентированность: заказы и MEMO фиксируются в БД; вотчер
#   подхватывает оплату по tx_hash и обновляет статусы.
# • Витрина отдаёт флаги доступности и disabled_reason для UI;
#   кнопки деактивируются при минусе/недостатке средств/неподдержке.
#
# Запреты:
# • Никакой автодоставки NFT. Только заявка PAID_PENDING_MANUAL.
# • EFHC-пакеты оплачиваются только внешне (TON/USDT).
#   Мы создаём заказ PENDING и генерируем MEMO.
# • Никаких скрытых начислений, минуя Банк.
# ====================================================================

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any, cast

from app.contracts.shop_contract import ShopContract
from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.deps import d8, decode_cursor, encode_cursor, get_db
from app.domain.finance.external_amounts import (
    external_amount_from_atomic,
    external_amount_from_display,
)
from app.domain.finance.shop_prices import (
    normalize_shop_external_price_d2,
    shop_external_price_diagnostic,
)
from app.identity.financial_owner import resolve_financial_read_owner
from app.lib.time import utcnow
from app.schemas.shop_schemas import (
    ShopCatalogItemOut,
    ShopCatalogOut,
    ShopOrderExternalIn,
    ShopOrderExternalOut,
    ShopPurchaseByEFHCIn,
    ShopPurchaseByEFHCOut,
)
from app.services import transactions_service as bank
from app.services.shop_prepayment_store import (
    require_no_active_legacy_shop_intent,
    require_no_active_shop_preparation,
)
from app.services.financial_execution_window import (
    validate_external_financial_execution,
)
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()


def _build_nft_collection_json(settings) -> str:
    """JSON для extra.nft_collection (коротко и канонично)."""
    col = getattr(settings, "TON_NFT_COLLECTION", "")
    return f'{{"nft_collection": "{col}"}}'


# ---- Канонические типы/статусы
# ------------------------------------------------

ITEM_TYPE_EFHC_PACKAGE = "EFHC_PACKAGE"
# OWNER cycle 1818: 15 fixed packages + one custom EFHCm product.
CANONICAL_EFHC_PACKAGE_AMOUNTS = (
    10,
    50,
    100,
    150,
    200,
    250,
    300,
    350,
    500,
    750,
    1000,
    1500,
    2000,
    2500,
    3000,
)
CUSTOM_EFHC_PACKAGE_SKU = "EFHC_PACKAGE_CUSTOM"
CANONICAL_VIP_SKU = "EFHC_VIP_NFT_ANY"
ITEM_TYPE_NFT_VIP = "NFT_VIP"  # VIP NFT (TON/USDT/EFHC)
ITEM_TYPE_NFT_VIP_SELECTED_PRICE = "NFT_VIP_SELECTED_PRICE"
ITEM_TYPE_NFT_VIP_NUMBER = "NFT_VIP_NUMBER"
VIP_ITEM_TYPES = frozenset(
    {
        ITEM_TYPE_NFT_VIP,
        ITEM_TYPE_NFT_VIP_SELECTED_PRICE,
        ITEM_TYPE_NFT_VIP_NUMBER,
    }
)
VIP_NUMBER_RESERVATION_KEY = "vip_number_reservation"
VIP_NUMBER_CLAIM_KEY = "vip_number_claim"
ITEM_TYPE_VIRTUAL = "VIRTUAL"
# прочие виртуальные товары (за EFHC внутри)

PAY_TON = "TON"
PAY_USDT = "USDT"
PAY_EFHC = "EFHC"
USDT_DISABLED_REASON = "usdt_price_or_method_not_ready"

ORDER_STATUS_PENDING = "PENDING"  # заказ создан, ждём внешнюю оплату
ORDER_STATUS_PAID_AUTO = "PAID_AUTO"
# оплачен автоматически: внешний платёж подтверждён
# вотчером / авто-логика
ORDER_STATUS_PAID_PENDING_MANUAL = "PAID_PENDING_MANUAL"
# оплачен, ожидание ручной выдачи (NFT)
ORDER_STATUS_CANCELLED = "CANCELLED"
ORDER_STATUS_REJECTED = "REJECTED"

# ---- Вспомогательные DTO
# ------------------------------------------------------


@dataclass
class ShopItemDTO:
    id: int
    code: str
    title: str
    item_type: str
    is_active: bool
    price_efhc: Decimal | None
    price_ton: Decimal | None
    price_usdt: Decimal | None
    pay_currencies: list[str]
    extra_json: dict[str, Any]


@dataclass
class OrderDTO:
    id: int
    global_id: int
    status: str
    memo: str | None
    tx_hash: str | None
    created_at: datetime
    updated_at: datetime | None = None
    paid_at: datetime | None = None
    idempotency_key: str | None = None
    item_id: int | None = None
    payment_method: str | None = None
    order_type: str | None = None
    quantity_efhc: str | None = None
    expected_amount: str | None = None
    sku: str | None = None


# ---- Утилиты
# ------------------------------------------------------------------


def _now_utc() -> datetime:
    """Функция `_now_utc` выполняет операцию
    в контуре бота EFHC.
        Назначение: бизнес‑логика соответствующего модуля
    (см. имя функции и вызывающий код).

        Возвращает:
        - Значение типа/структуры: datetime.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли
      (идемпотентность достигается ключами/
      уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8
      и округлением вниз (ROUND_DOWN), если применимо
      по модулю.
        - Для операций, затрагивающих баланс/банк, изменения
      проходят через банковский сервис транзакций
      (transactions_service)."""
    return cast(datetime, utcnow())


def _pay_methods_from_row(row) -> list[str]:
    # pay_currencies хранится как массив TEXT[] или JSON — нормализуем к
    # List[str]
    """Функция `_pay_methods_from_row` выполняет операцию
    в контуре бота EFHC.
        Назначение: бизнес‑логика соответствующего модуля
    (см. имя функции и вызывающий код).

        Параметры:
        - `row`: входной параметр.

        Возвращает:
        - Значение типа/структуры: List[str].

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли
      (идемпотентность достигается ключами/
      уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8
      и округлением вниз (ROUND_DOWN), если применимо
      по модулю.
        - Для операций, затрагивающих баланс/банк, изменения
      проходят через банковский сервис транзакций
      (transactions_service)."""
    val = row["pay_currencies"]
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        # на случай JSON-строки
        try:
            import json

            arr = json.loads(val)
            if isinstance(arr, list):
                return [str(x) for x in arr]
            return []
        except Exception:
            return []
    return []


def _extra_obj(row: Any) -> dict[str, Any]:
    raw = row.get("extra") if hasattr(row, "get") else None
    if raw is None and hasattr(row, "get"):
        raw = row.get("extra_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}
    return {}


def _infer_item_type(row: Any) -> str:
    if hasattr(row, "get"):
        direct = row.get("item_type")
        if direct:
            return str(direct)
    extra = _extra_obj(row)
    if isinstance(extra.get("item_type"), str):
        return str(extra["item_type"])
    qty = None
    if hasattr(row, "get"):
        qty = row.get("quantity_efhc")
    if qty is not None:
        return ITEM_TYPE_EFHC_PACKAGE
    sku = None
    if hasattr(row, "get"):
        sku = row.get("sku") or row.get("code")
    sku_s = str(sku or "")
    if "NFT" in sku_s or "VIP" in sku_s:
        return ITEM_TYPE_NFT_VIP
    return ITEM_TYPE_VIRTUAL


def _price_from_extra(
    extra: dict[str, Any],
    key: str,
) -> Decimal | None:
    """Прочитать manual catalog price без смешения external money с EFHC D8."""
    raw = extra.get(key)
    if raw is None:
        prices = extra.get("prices")
        if isinstance(prices, dict):
            raw = prices.get(key)
    if raw is None:
        return None
    try:
        if key in {"price_ton", "price_usdt"}:
            normalized_price: Decimal = normalize_shop_external_price_d2(str(raw))
            return normalized_price
        return cast(Decimal, d8(raw))
    except (ArithmeticError, TypeError, ValueError):
        # Историческая внешняя цена >D2 не округляется автоматически.
        # Способ оплаты недоступен до явной коррекции цены администратором.
        return None


def _legacy_external_amount_d8(value: Decimal) -> Decimal:
    """Frozen-schema compatibility only; never settlement authority."""
    return Decimal(str(value)).quantize(
        Decimal("0.00000001"),
        rounding=ROUND_DOWN,
    )


def _pay_methods_from_item(row: Any) -> list[str]:
    if hasattr(row, "get"):
        direct = row.get("pay_currencies")
        if direct is not None:
            if isinstance(direct, list):
                return [str(x).upper() for x in direct]
            if isinstance(direct, str):
                arr: list[Any] | None = None
                try:
                    loaded = json.loads(direct)
                    if isinstance(loaded, list):
                        arr = loaded
                except (TypeError, ValueError, json.JSONDecodeError):
                    arr = None
                if arr is not None:
                    return [str(x).upper() for x in arr]
    extra = _extra_obj(row)
    pays = extra.get("pay_currencies")
    if isinstance(pays, list):
        return [str(x).upper() for x in pays]
    item_type = _infer_item_type(row)
    if item_type == ITEM_TYPE_EFHC_PACKAGE:
        return [PAY_TON, PAY_USDT]
    if item_type == ITEM_TYPE_NFT_VIP:
        return [PAY_EFHC, PAY_TON, PAY_USDT]
    return [PAY_EFHC]


def _item_to_dto(row: Any) -> ShopItemDTO:
    extra = _extra_obj(row)
    code = None
    if hasattr(row, "get"):
        code = row.get("code") or row.get("sku")
    return ShopItemDTO(
        id=int(row["id"]),
        code=str(code),
        title=str(row["title"]),
        item_type=_infer_item_type(row),
        is_active=bool(row.get("is_active", True)),
        price_efhc=_price_from_extra(extra, "price_efhc"),
        price_ton=_price_from_extra(extra, "price_ton"),
        price_usdt=_price_from_extra(extra, "price_usdt"),
        pay_currencies=_pay_methods_from_item(row),
        extra_json=extra,
    )


def _order_type_for_item(item: ShopItemDTO) -> str:
    """Выбрать безопасный order type по delivery-mode карточки."""
    delivery_mode = str(
        (item.extra_json or {}).get("delivery_mode") or ""
    ).lower()
    if item.item_type == ITEM_TYPE_EFHC_PACKAGE or delivery_mode == "bank_credit":
        return "EFHC"
    return "NFT"


def _item_quantity_text(item: ShopItemDTO) -> str | None:
    if item.extra_json:
        for key in (
            "quantity_efhc",
            "quantity",
            "efhc_quantity",
            "qty",
            "package_qty",
            "pack_quantity",
            "nominal",
            "efhc_amount",
        ):
            val = item.extra_json.get(key)
            if val is not None:
                return str(val)
    if item.item_type == ITEM_TYPE_EFHC_PACKAGE and "_" in item.code:
        tail = item.code.split("_")[-1]
        if tail.isdigit():
            return tail
    return None


def _normalize_custom_efhc_amount_d8(value: str | Decimal | None) -> Decimal | None:
    """Validate OWNER custom EFHCm quantity: whole units only, minimum 1."""
    if value is None or str(value).strip() == "":
        return None
    try:
        amount = Decimal(str(value).strip())
    except Exception as exc:
        raise ValueError("CUSTOM_EFHC_AMOUNT_INVALID") from exc
    if not amount.is_finite() or amount < 1 or amount != amount.to_integral_value():
        raise ValueError("CUSTOM_EFHC_AMOUNT_WHOLE_MIN_1_REQUIRED")
    return cast(Decimal, d8(amount))


def _is_custom_efhc_package(item: ShopItemDTO) -> bool:
    return (
        item.item_type == ITEM_TYPE_EFHC_PACKAGE
        and str(item.code).upper() == CUSTOM_EFHC_PACKAGE_SKU
    )


def _custom_external_total_d2(
    unit_rate: Decimal,
    custom_amount_d8: Decimal,
) -> Decimal:
    """Server-authoritative custom total = catalog D2 rate × whole EFHCm quantity."""
    rate = normalize_shop_external_price_d2(unit_rate)
    whole = _normalize_custom_efhc_amount_d8(custom_amount_d8)
    if whole is None:
        raise ValueError("CUSTOM_EFHC_AMOUNT_REQUIRED")
    return cast(Decimal, normalize_shop_external_price_d2(rate * whole))


def _is_vip_item(item: ShopItemDTO) -> bool:
    return str(item.item_type).upper() in VIP_ITEM_TYPES


def _is_selected_vip_number_item(item: ShopItemDTO) -> bool:
    return str(item.item_type).upper() == ITEM_TYPE_NFT_VIP_NUMBER


def _vip_number_from_item(item: ShopItemDTO) -> str | None:
    if not _is_selected_vip_number_item(item):
        return None
    for value in (item.code, item.title):
        text_value = str(value or "")
        tail = text_value.rsplit("_", 1)[-1].lstrip("#")
        if len(tail) == 4 and tail.isdigit() and tail != "0000":
            return tail
    return None


def _parse_business_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _active_vip_reservation(
    extra: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    reservation = extra.get(VIP_NUMBER_RESERVATION_KEY)
    if not isinstance(reservation, dict):
        return None
    expires_at = _parse_business_datetime(reservation.get("expires_at"))
    if expires_at is None:
        return None
    checked_at = now or _now_utc()
    if expires_at <= checked_at:
        return None
    return dict(reservation)


async def _lock_selected_vip_number_for_checkout(
    db: AsyncSession,
    *,
    item: ShopItemDTO,
    global_id: int,
    idempotency_key: str,
) -> dict[str, Any] | None:
    """Заблокировать выбранный VIP number и проверить reservation/claim state."""
    if not _is_selected_vip_number_item(item):
        return None
    row = (
        (
            await db.execute(
                text(
                    """
                    SELECT id, sku, title, description, quantity_efhc,
                           COALESCE(is_active, TRUE) AS is_active, extra
                      FROM efhc_core.shop_items
                     WHERE sku = :sku
                     FOR UPDATE
                    """
                ),
                {"sku": str(item.code)},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ValueError("VIP_NUMBER_NOT_FOUND")
    extra = _extra_obj(row)
    number = _vip_number_from_item(_item_to_dto(row))
    if number is None:
        raise ValueError("VIP_NUMBER_INVALID")

    claim = extra.get(VIP_NUMBER_CLAIM_KEY)
    if isinstance(claim, dict):
        same_claim = (
            str(claim.get("global_id") or "") == f"{int(global_id):010d}"
            and str(claim.get("idempotency_key") or "") == str(idempotency_key)
        )
        if not same_claim:
            raise ValueError("VIP_NUMBER_ALREADY_SOLD")

    status = str(extra.get("status") or "live").strip().lower()
    if status in {"sold", "archived", "hidden", "inactive"} and not isinstance(
        claim, dict
    ):
        raise ValueError("VIP_NUMBER_NOT_AVAILABLE")

    reservation = _active_vip_reservation(extra)
    if reservation is not None:
        same_reservation = (
            str(reservation.get("global_id") or "") == f"{int(global_id):010d}"
            and str(reservation.get("idempotency_key") or "")
            == str(idempotency_key)
        )
        if not same_reservation:
            raise ValueError("VIP_NUMBER_RESERVED")

    return {
        "id": int(row["id"]),
        "sku": str(row["sku"]),
        "number": number,
        "extra": extra,
    }


async def bind_vip_number_reservation_in_transaction(
    db: AsyncSession,
    *,
    item_code: str,
    global_id: int,
    idempotency_key: str,
    order_id: int,
    intent_id: int,
    expires_at: datetime,
) -> dict[str, Any] | None:
    """Привязать selected-number reservation к PaymentIntent в той же transaction."""
    item = await _get_item_by_code(db, item_code)
    locked = await _lock_selected_vip_number_for_checkout(
        db,
        item=item,
        global_id=int(global_id),
        idempotency_key=str(idempotency_key),
    )
    if locked is None:
        return None
    expiry = _parse_business_datetime(expires_at)
    if expiry is None or expiry <= _now_utc():
        raise ValueError("VIP_NUMBER_RESERVATION_EXPIRY_INVALID")
    extra = dict(locked["extra"])
    existing_reservation = _active_vip_reservation(extra)
    if existing_reservation is not None:
        same_binding = (
            str(existing_reservation.get("global_id") or "")
            == f"{int(global_id):010d}"
            and str(existing_reservation.get("idempotency_key") or "")
            == str(idempotency_key)
            and int(existing_reservation.get("order_id") or 0) == int(order_id)
            and int(existing_reservation.get("intent_id") or 0) == int(intent_id)
        )
        if not same_binding:
            raise ValueError("VIP_NUMBER_RESERVATION_BINDING_CONFLICT")
        return {
            "number": str(locked["number"]),
            "expires_at": _parse_business_datetime(
                existing_reservation.get("expires_at")
            ),
        }
    extra[VIP_NUMBER_RESERVATION_KEY] = {
        "global_id": f"{int(global_id):010d}",
        "idempotency_key": str(idempotency_key),
        "order_id": int(order_id),
        "intent_id": int(intent_id),
        "expires_at": expiry.isoformat(),
        "reserved_at": _now_utc().isoformat(),
    }
    extra["status"] = "live"
    await db.execute(
        text(
            """
            UPDATE efhc_core.shop_items
               SET extra = CAST(:extra AS jsonb), updated_at = :updated_at
             WHERE id = :item_id
            """
        ),
        {
            "item_id": int(locked["id"]),
            "extra": json.dumps(extra),
            "updated_at": _now_utc(),
        },
    )
    return {
        "number": str(locked["number"]),
        "expires_at": expiry,
    }


async def _claim_selected_vip_number_in_transaction(
    db: AsyncSession,
    *,
    item: ShopItemDTO,
    global_id: int,
    idempotency_key: str,
    order_id: int,
    intent_id: int | None = None,
) -> str | None:
    """Зафиксировать окончательную продажу selected VIP number без нового DDL."""
    locked = await _lock_selected_vip_number_for_checkout(
        db,
        item=item,
        global_id=int(global_id),
        idempotency_key=str(idempotency_key),
    )
    if locked is None:
        return None
    extra = dict(locked["extra"])
    existing_claim = extra.get(VIP_NUMBER_CLAIM_KEY)
    if isinstance(existing_claim, dict):
        return str(locked["number"])
    extra[VIP_NUMBER_CLAIM_KEY] = {
        "global_id": f"{int(global_id):010d}",
        "idempotency_key": str(idempotency_key),
        "order_id": int(order_id),
        "intent_id": int(intent_id) if intent_id is not None else None,
        "claimed_at": _now_utc().isoformat(),
    }
    extra["status"] = "sold"
    await db.execute(
        text(
            """
            UPDATE efhc_core.shop_items
               SET extra = CAST(:extra AS jsonb), updated_at = :updated_at
             WHERE id = :item_id
            """
        ),
        {
            "item_id": int(locked["id"]),
            "extra": json.dumps(extra),
            "updated_at": _now_utc(),
        },
    )
    return str(locked["number"])


def _order_extra(
    item: ShopItemDTO,
    payment_method: str | None = None,
    canonical_memo: str | None = None,
    *,
    request_quantity: int = 1,
    unit_amount: Decimal | None = None,
    expected_amount: Decimal | None = None,
    to_address: str | None = None,
    external_amount_atomic: int | None = None,
    external_decimals: int | None = None,
    custom_efhc_amount_d8: Decimal | None = None,
) -> dict[str, Any]:
    """Сохранить immutable fingerprint исходного Shop-запроса."""
    method = str(payment_method or "").upper()
    external = method in {PAY_TON, PAY_USDT}
    return {
        "sku": str(item.code),
        "item_type": str(item.item_type),
        "payment_method": method if method else None,
        "request_quantity": int(request_quantity),
        "unit_amount": (
            str(unit_amount)
            if external and unit_amount is not None
            else (str(d8(unit_amount)) if unit_amount is not None else None)
        ),
        "expected_amount": (
            str(expected_amount)
            if external and expected_amount is not None
            else (str(d8(expected_amount)) if expected_amount is not None else None)
        ),
        "external_amount_atomic": (
            str(int(external_amount_atomic))
            if external_amount_atomic is not None
            else None
        ),
        "external_decimals": (
            int(external_decimals) if external_decimals is not None else None
        ),
        "to_address": str(to_address) if to_address else None,
        "canonical_memo": str(canonical_memo) if canonical_memo else None,
        "custom_efhc_amount_d8": (
            str(d8(custom_efhc_amount_d8))
            if custom_efhc_amount_d8 is not None
            else None
        ),
        "vip_number": _vip_number_from_item(item),
    }


def _scaled_item_quantity_text(
    item: ShopItemDTO,
    request_quantity: int,
    *,
    custom_efhc_amount_d8: Decimal | None = None,
) -> str | None:
    if _is_custom_efhc_package(item):
        custom = _normalize_custom_efhc_amount_d8(custom_efhc_amount_d8)
        return str(custom) if custom is not None else None
    raw = _item_quantity_text(item)
    if raw is None:
        return None
    try:
        return str(d8(Decimal(str(raw)) * Decimal(int(request_quantity))))
    except Exception:
        return raw if int(request_quantity) == 1 else None


def _shop_order_extra_from_row(row: Any) -> dict[str, Any]:
    raw = row.get("extra") if hasattr(row, "get") else None
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    return {}


def _raise_shop_idempotency_payload_conflict() -> None:
    raise bank.IdempotencyPayloadConflictError(
        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"
    )


def _assert_shop_order_fingerprint(
    row: Any,
    *,
    global_id: int,
    item: ShopItemDTO,
    payment_method: str,
    request_quantity: int,
    expected_amount: Decimal,
    to_address: str | None = None,
    external_amount_atomic: int | None = None,
    custom_efhc_amount_d8: Decimal | None = None,
) -> None:
    """Проверить owner-scoped immutable fingerprint ShopOrder."""
    extra = _shop_order_extra_from_row(row)
    saved_quantity_raw = extra.get("request_quantity")
    if saved_quantity_raw is None:
        _raise_shop_idempotency_payload_conflict()
        return
    try:
        saved_quantity = int(saved_quantity_raw)
    except (TypeError, ValueError):
        _raise_shop_idempotency_payload_conflict()
        return
    method = str(payment_method).upper()
    current_unit = {
        PAY_EFHC: item.price_efhc,
        PAY_TON: item.price_ton,
        PAY_USDT: item.price_usdt,
    }.get(method)
    fingerprint_ok = (
        int(row.get("global_id")) == int(global_id)
        and str(extra.get("sku") or "") == str(item.code)
        and str(extra.get("item_type") or "") == str(item.item_type)
        and str(extra.get("payment_method") or "").upper() == method
        and saved_quantity == int(request_quantity)
        and current_unit is not None
    )
    if method in {PAY_TON, PAY_USDT}:
        if external_amount_atomic is None:
            _raise_shop_idempotency_payload_conflict()
            return
        saved_atomic = extra.get("external_amount_atomic")
        try:
            current_atomic = external_amount_from_display(
                method, expected_amount, require_positive=True
            ).atomic
            fingerprint_ok = fingerprint_ok and (
                int(str(saved_atomic)) == int(external_amount_atomic) == current_atomic
            )
        except (TypeError, ValueError):
            fingerprint_ok = False
    else:
        saved_unit = extra.get("unit_amount")
        saved_expected = row.get("expected_amount")
        fingerprint_ok = fingerprint_ok and (
            saved_unit is not None
            and d8(saved_unit) == d8(current_unit)
            and saved_expected is not None
            and d8(saved_expected) == d8(expected_amount)
        )
    if custom_efhc_amount_d8 is not None:
        saved_custom = extra.get("custom_efhc_amount_d8")
        try:
            fingerprint_ok = fingerprint_ok and (
                d8(saved_custom) == d8(custom_efhc_amount_d8)
            )
        except Exception:
            fingerprint_ok = False
    elif _is_custom_efhc_package(item):
        fingerprint_ok = False
    if to_address is not None:
        fingerprint_ok = fingerprint_ok and (
            str(extra.get("to_address") or "").strip() == str(to_address).strip()
        )
    if not fingerprint_ok:
        _raise_shop_idempotency_payload_conflict()


async def _find_shop_order_by_idempotency(
    db: AsyncSession,
    *,
    global_id: int,
    idempotency_key: str,
) -> dict[str, Any] | None:
    row = (
        (
            await db.execute(
                text(
                    """
                    SELECT id, global_id, type, status, quantity_efhc,
                           expected_amount, memo, tx_hash, idempotency_key,
                           created_at, extra
                      FROM efhc_core.shop_orders
                     WHERE global_id = :global_id
                       AND idempotency_key = :idk
                     LIMIT 1
                    """
                ),
                {
                    "global_id": int(global_id),
                    "idk": str(idempotency_key),
                },
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


async def _shop_spend_breakdown_from_ledger(
    db: AsyncSession,
    *,
    global_id: int,
    item_code: str,
    request_quantity: int,
    expected_amount: Decimal,
    idempotency_key: str,
) -> tuple[Decimal, Decimal, int]:
    """Прочитать фактическое BONUS/MAIN списание и проверить fingerprint."""
    bonus_key = f"{idempotency_key}:bonus"
    main_key = f"{idempotency_key}:main"
    rows = (
        await db.execute(
            text(
                """
                SELECT id, amount, direction, balance_type, reason,
                       idempotency_key, meta
                  FROM efhc_core.efhc_transfers_log
                 WHERE global_id = :global_id
                   AND idempotency_key IN (:bonus_key, :main_key)
                 ORDER BY id ASC
                """
            ),
            {
                "global_id": int(global_id),
                "bonus_key": bonus_key,
                "main_key": main_key,
            },
        )
    ).mappings().all()
    if not rows:
        raise RuntimeError("shop spend ledger proof is missing")

    bonus_part = d8("0")
    main_part = d8("0")
    log_id = 0
    expected_reason = f"shop:{item_code}"
    for row in rows:
        if str(row.get("reason") or "") != expected_reason:
            _raise_shop_idempotency_payload_conflict()
        raw_meta = row.get("meta")
        meta: dict[str, Any] = {}
        if isinstance(raw_meta, dict):
            meta = dict(raw_meta)
        elif isinstance(raw_meta, str) and raw_meta.strip():
            try:
                loaded = json.loads(raw_meta)
                meta = loaded if isinstance(loaded, dict) else {}
            except Exception:
                meta = {}
        try:
            raw_meta_qty = meta.get("qty")
            if raw_meta_qty is None:
                _raise_shop_idempotency_payload_conflict()
                return d8("0"), d8("0"), 0
            meta_qty = int(raw_meta_qty)
        except Exception:
            _raise_shop_idempotency_payload_conflict()
            return d8("0"), d8("0"), 0
        if (
            str(meta.get("item_code") or "") != str(item_code)
            or meta_qty != int(request_quantity)
        ):
            _raise_shop_idempotency_payload_conflict()
        amount = d8(row.get("amount") or "0")
        direction = str(row.get("direction") or "").lower()
        balance_type = str(row.get("balance_type") or "").lower()
        derived_key = str(row.get("idempotency_key") or "")
        if direction != "debit":
            _raise_shop_idempotency_payload_conflict()
        if derived_key == bonus_key and balance_type == "bonus":
            bonus_part = d8(bonus_part + amount)
        elif derived_key == main_key and balance_type == "main":
            main_part = d8(main_part + amount)
        else:
            _raise_shop_idempotency_payload_conflict()
        log_id = int(row.get("id") or log_id)

    if d8(bonus_part + main_part) != d8(expected_amount):
        _raise_shop_idempotency_payload_conflict()
    return bonus_part, main_part, log_id


# ---- Сидер каталога под список EFHC-пакетов и VIP
# ----------------------------


async def _hide_legacy_shop_item(db: AsyncSession, sku: str) -> None:
    row = await _admin_get_item_row(db, code=sku)
    if row is None:
        return
    extra = _extra_obj(row)
    extra["status"] = "hidden"
    await db.execute(
        text(
            """
            UPDATE efhc_core.shop_items
               SET is_active = FALSE, extra = CAST(:extra AS jsonb), updated_at = NOW()
             WHERE sku = :sku
            """
        ),
        {"sku": str(sku), "extra": json.dumps(extra)},
    )


async def seed_default_items(db: AsyncSession) -> dict[str, Any]:
    """Idempotently reconcile Shop base rows with OWNER/CANON v234.

    Existing owner prices/content are preserved whenever a legacy fixed package
    can be renamed to its stable SKU. Obsolete legacy rows are hidden rather
    than deleted so historical orders remain attributable.
    """
    inserted = 0
    updated = 0

    for qty in CANONICAL_EFHC_PACKAGE_AMOUNTS:
        stable_sku = f"EFHC_PACKAGE_{qty}"
        legacy_sku = f"EFHC_{qty}"
        stable = await _admin_get_item_row(db, code=stable_sku)
        legacy = await _admin_get_item_row(db, code=legacy_sku)
        if stable is None and legacy is not None:
            extra = _extra_obj(legacy)
            extra.update(
                {
                    "item_type": ITEM_TYPE_EFHC_PACKAGE,
                    "category": str(extra.get("category") or "efhc"),
                    "action_mode": "checkout",
                    "delivery_mode": "bank_credit",
                    "pay_currencies": [PAY_TON, PAY_USDT],
                    "quantity_efhc": str(d8(qty)),
                    "sort_order": int(qty),
                }
            )
            await db.execute(
                text(
                    """
                    UPDATE efhc_core.shop_items
                       SET sku = :stable_sku, title = :title,
                           quantity_efhc = :quantity_efhc,
                           extra = CAST(:extra AS jsonb), updated_at = NOW()
                     WHERE sku = :legacy_sku
                    """
                ),
                {
                    "stable_sku": stable_sku,
                    "legacy_sku": legacy_sku,
                    "title": f"{qty} EFHCm",
                    "quantity_efhc": str(d8(qty)),
                    "extra": json.dumps(extra),
                },
            )
            updated += 1
            stable = await _admin_get_item_row(db, code=stable_sku)
        if stable is None:
            extra = {
                "item_type": ITEM_TYPE_EFHC_PACKAGE,
                "status": "hidden",
                "category": "efhc",
                "badge": "",
                "action_mode": "checkout",
                "delivery_mode": "bank_credit",
                "pay_currencies": [PAY_TON, PAY_USDT],
                "quantity_efhc": str(d8(qty)),
                "sort_order": int(qty),
            }
            result = await db.execute(
                text(
                    """
                    INSERT INTO efhc_core.shop_items (
                        sku, title, description, quantity_efhc,
                        is_active, extra, created_at, updated_at
                    ) VALUES (
                        :sku, :title, NULL, :quantity_efhc, FALSE,
                        CAST(:extra AS jsonb), NOW(), NOW()
                    )
                    ON CONFLICT (sku) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "sku": stable_sku,
                    "title": f"{qty} EFHCm",
                    "quantity_efhc": str(d8(qty)),
                    "extra": json.dumps(extra),
                },
            )
            if result.first() is not None:
                inserted += 1
        if legacy is not None and stable is not None:
            await _hide_legacy_shop_item(db, legacy_sku)
            updated += 1

    custom = await _admin_get_item_row(db, code=CUSTOM_EFHC_PACKAGE_SKU)
    if custom is None:
        custom_extra = {
            "item_type": ITEM_TYPE_EFHC_PACKAGE,
            "status": "hidden",
            "category": "efhc",
            "badge": "",
            "action_mode": "checkout",
            "delivery_mode": "bank_credit",
            "pay_currencies": [PAY_TON, PAY_USDT],
            "sort_order": 1500,
        }
        result = await db.execute(
            text(
                """
                INSERT INTO efhc_core.shop_items (
                    sku, title, description, quantity_efhc,
                    is_active, extra, created_at, updated_at
                ) VALUES (
                    :sku, :title, :description, NULL, FALSE,
                    CAST(:extra AS jsonb), NOW(), NOW()
                )
                ON CONFLICT (sku) DO NOTHING
                RETURNING id
                """
            ),
            {
                "sku": CUSTOM_EFHC_PACKAGE_SKU,
                "title": "Свободный выбор EFHCm",
                "description": "Ручной выбор количества EFHCm по курсу за 1 EFHCm.",
                "extra": json.dumps(custom_extra),
            },
        )
        if result.first() is not None:
            inserted += 1

    vip = await _admin_get_item_row(db, code=CANONICAL_VIP_SKU)
    if vip is None:
        legacy_generic_vip = await _admin_get_item_row(db, code="EFHC_VIP_NFT")
        if legacy_generic_vip is not None:
            # OWNER cycle 1818: consolidate the former generic VIP row into the
            # single operational SKU without inventing or replacing Admin prices.
            legacy_extra = dict(legacy_generic_vip.extra_json or {})
            legacy_extra.update(
                {
                    "item_type": ITEM_TYPE_NFT_VIP,
                    "category": "vip",
                    "action_mode": "checkout",
                    "delivery_mode": "manual",
                    "pay_currencies": [PAY_TON, PAY_USDT, PAY_EFHC],
                }
            )
            await db.execute(
                text(
                    """
                    UPDATE efhc_core.shop_items
                       SET sku = :canonical_sku,
                           title = 'EFHC VIP NFT',
                           extra = CAST(:extra AS jsonb),
                           updated_at = :updated_at
                     WHERE id = :item_id
                    """
                ),
                {
                    "canonical_sku": CANONICAL_VIP_SKU,
                    "extra": json.dumps(legacy_extra),
                    "updated_at": _now_utc(),
                    "item_id": int(legacy_generic_vip.id),
                },
            )
            updated += 1
            vip = await _admin_get_item_row(db, code=CANONICAL_VIP_SKU)
        else:
            vip_extra = {
                "item_type": ITEM_TYPE_NFT_VIP,
                "status": "hidden",
                "category": "vip",
                "badge": "",
                "action_mode": "checkout",
                "delivery_mode": "manual",
                "pay_currencies": [PAY_TON, PAY_USDT, PAY_EFHC],
                "sort_order": 2000,
            }
            # Latest OWNER authority: a newly created canonical VIP starts
            # without generated prices. Admin must explicitly set each method.
            result = await db.execute(
                text(
                    """
                    INSERT INTO efhc_core.shop_items (
                        sku, title, description, quantity_efhc,
                        is_active, extra, created_at, updated_at
                    ) VALUES (
                        :sku, :title, NULL, NULL, FALSE,
                        CAST(:extra AS jsonb), :created_at, :updated_at
                    )
                    ON CONFLICT (sku) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "sku": CANONICAL_VIP_SKU,
                    "title": "EFHC VIP NFT",
                    "extra": json.dumps(vip_extra),
                    "created_at": _now_utc(),
                    "updated_at": _now_utc(),
                },
            )
            if result.first() is not None:
                inserted += 1

    canonical_fixed = {f"EFHC_PACKAGE_{qty}" for qty in CANONICAL_EFHC_PACKAGE_AMOUNTS}
    obsolete_rows = (
        await db.execute(
            text(
                """
                SELECT sku FROM efhc_core.shop_items
                 WHERE (sku ~ '^EFHC_[0-9]+$'
                        OR sku IN ('EFHC_VIP_NFT', 'VIP_NFT_TON', 'VIP_NFT_USDT', 'VIP_NFT_EFHC'))
                   AND COALESCE(is_active, TRUE) = TRUE
                """
            )
        )
    ).mappings().all()
    protected = canonical_fixed | {CUSTOM_EFHC_PACKAGE_SKU, CANONICAL_VIP_SKU}
    for row in obsolete_rows:
        sku = str(row.get("sku") or "")
        if sku in protected:
            continue
        await _hide_legacy_shop_item(db, sku)
        updated += 1

    await db.commit()
    return {"inserted": inserted, "updated": updated}


async def _get_user_balances(
    db: AsyncSession,
    global_id: int,
) -> tuple[Decimal, Decimal]:
    """Асинхронная функция `_get_user_balances` выполняет операцию
    в контуре бота EFHC.
        Назначение: бизнес‑логика соответствующего модуля
    (см. имя функции и вызывающий код).

        Параметры:
        - `db` (AsyncSession): входной параметр.
        - `global_id` (int): входной параметр.

        Возвращает:
        - Значение типа/структуры: Tuple[Decimal, Decimal].

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли
      (идемпотентность достигается ключами/
      уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8
      и округлением вниз (ROUND_DOWN), если применимо
      по модулю.
        - Для операций, затрагивающих баланс/банк, изменения
      проходят через банковский сервис транзакций
      (transactions_service)."""
    q = text(
        """
            SELECT COALESCE(main_balance,0) AS main_balance,
               COALESCE(bonus_balance,0) AS bonus_balance
        FROM efhc_core.users WHERE global_id = :global_id
        LIMIT 1
    """
    )
    row = (
        await db.execute(q, {"global_id": int(global_id)})
    ).mappings().first()
    if not row:
        raise ValueError(f"global_id={global_id:010d} not found")
    return d8(row["main_balance"]), d8(row["bonus_balance"])


# ---- Загрузка каталога
# --------------------------------------------------------


async def _fetch_items(db: AsyncSession) -> list[ShopItemDTO]:
    """Чтение карточек магазина по каноничной схеме shop_items."""
    q = text(
        """
        SELECT id, sku, title, description, quantity_efhc,
               COALESCE(is_active, TRUE) AS is_active,
               extra
          FROM efhc_core.shop_items
         ORDER BY id ASC
        """
    )
    rows = (await db.execute(q)).mappings().all()
    return [_item_to_dto(r) for r in rows]


# ---- Витрина магазина для пользователя
# ---------------------------------------


async def list_shop_for_user(
    db: AsyncSession,
    global_id: int,
) -> dict[str, Any]:
    """
    Витрина магазина для пользователя:
      • отдаёт весь активный каталог товаров;
      • по каждой карточке товара рассчитывает
        доступность кнопок по методам оплаты;
      • для EFHC-покупок — проверяет, хватает ли
        (bonus+main) и не в «минусе» ли пользователь.
    """
    main, bonus = await _get_user_balances(db, global_id)
    total_efhc = d8(main + bonus)

    items = await _fetch_items(db)

    def check_efhc_afford(item: ShopItemDTO) -> tuple[bool, str]:
        """Функция `check_efhc_afford` выполняет операцию
        в контуре бота EFHC.
                Назначение: бизнес‑логика соответствующего модуля
        (см. имя функции и вызывающий код).

                Параметры:
                - `item` (ShopItemDTO): входной параметр.

                Возвращает:
                - Значение типа/структуры: Tuple[bool, str].

                Инварианты и безопасность:
                - Повторный вызов не должен создавать дубли
          (идемпотентность достигается ключами/
          уникальными ограничениями).
                - Денежные значения в EFHC учитываются с точностью d8
          и округлением вниз (ROUND_DOWN), если применимо
          по модулю.
                - Для операций, затрагивающих баланс/банк, изменения
          проходят через банковский сервис транзакций
          (transactions_service)."""
        if item.item_type == ITEM_TYPE_EFHC_PACKAGE:
            # EFHC-пакеты нельзя покупать за EFHC
            return (False, "efhc_not_supported_for_packages")
        if item.price_efhc is None:
            return (False, "price_not_set")
        if total_efhc < item.price_efhc:
            return (False, "insufficient_efhc_balance")
        return (True, "")

    def method_supported(item: ShopItemDTO, method: str) -> bool:
        """Функция `method_supported` выполняет операцию
        в контуре бота EFHC.
                Назначение: бизнес‑логика соответствующего модуля
        (см. имя функции и вызывающий код).

                Параметры:
                - `item` (ShopItemDTO): входной параметр.
                - `method` (str): входной параметр.

                Возвращает:
                - Значение типа/структуры: bool.

                Инварианты и безопасность:
                - Повторный вызов не должен создавать дубли
          (идемпотентность достигается ключами/
          уникальными ограничениями).
                - Денежные значения в EFHC учитываются с точностью d8
          и округлением вниз (ROUND_DOWN), если применимо
          по модулю.
                - Для операций, затрагивающих баланс/банк, изменения
          проходят через банковский сервис транзакций
          (transactions_service)."""
        return method in item.pay_currencies

    out_items: list[dict[str, Any]] = []
    for it in items:
        can_efhc, reason_efhc = check_efhc_afford(it)
        efhc_enabled = (
            can_efhc
            and method_supported(it, PAY_EFHC)
            and it.price_efhc is not None
            and it.price_efhc > 0
        )
        ton_enabled = (
            method_supported(it, PAY_TON)
            and it.price_ton is not None
            and it.price_ton > 0
        )
        usdt_enabled = (
            method_supported(it, PAY_USDT)
            and it.price_usdt is not None
            and it.price_usdt > 0
        )

        out_items.append(
            {
                "id": it.id,
                "code": it.code,
                "title": it.title,
                "type": it.item_type,
                "prices": {
                    "EFHC": (
                        str(it.price_efhc)
                        if it.price_efhc is not None
                        else None
                    ),
                    "TON": (
                        str(it.price_ton)
                        if it.price_ton is not None
                        else None
                    ),
                    "USDT": (
                        str(it.price_usdt)
                        if it.price_usdt is not None
                        else None
                    ),
                },
                "supported_methods": it.pay_currencies,
                "available": {
                    "EFHC": {
                        "enabled": efhc_enabled,
                        "disabled_reason": (
                            None
                            if efhc_enabled
                            else (
                                reason_efhc
                                if not can_efhc
                                else "method_not_supported"
                            )
                        ),
                    },
                    "TON": {
                        "enabled": ton_enabled,
                        "disabled_reason": (
                            None
                            if ton_enabled
                            else (
                                "price_not_set"
                                if it.price_ton is None or it.price_ton <= 0
                                else "method_not_supported"
                            )
                        ),
                    },
                    "USDT": {
                        "enabled": usdt_enabled,
                        "disabled_reason": (
                            None
                            if usdt_enabled
                            else (
                                "price_not_set"
                                if it.price_usdt is None or it.price_usdt <= 0
                                else USDT_DISABLED_REASON
                            )
                        ),
                    },
                },
                "extra": it.extra_json,
            }
        )

    return {
        "balances": {
            "main_balance": str(main),
            "bonus_balance": str(bonus),
            "total_efhc": str(total_efhc),
        },
        "items": out_items,
    }


# ---- MEMO-формат по канону
# ----------------------------------------------------


def _build_memo_for_external(
    item: ShopItemDTO,
    global_id: int,
    *,
    custom_efhc_amount_d8: Decimal | None = None,
) -> str:
    """
    EFHC-пакеты: SKU:EFHC|Q:<INT>|G:<global_id>
    VIP NFT:    SKU:NFT_VIP|Q:1|G:<global_id>
    Прочие SKU можно расширять по мере добавления типов товаров.
    """
    if item.item_type == ITEM_TYPE_EFHC_PACKAGE:
        qty = 0
        if _is_custom_efhc_package(item):
            custom = _normalize_custom_efhc_amount_d8(custom_efhc_amount_d8)
            if custom is None:
                raise ValueError("CUSTOM_EFHC_AMOUNT_REQUIRED")
            qty = int(custom)
        elif item.extra_json and "quantity_efhc" in item.extra_json:
            try:
                qty = int(Decimal(str(item.extra_json["quantity_efhc"])))
            except Exception:
                qty = 0
        return f"SKU:EFHC|Q:{qty}|G:{global_id:010d}"
    elif _is_vip_item(item):
        return f"SKU:NFT_VIP|Q:1|G:{global_id:010d}"
    return f"SKU:{item.code}|Q:1|G:{global_id:010d}"


# ---- Загрузка карточки товара по code
# -----------------------------------------


async def _get_item_by_code(db: AsyncSession, code: str) -> ShopItemDTO:
    """Загрузка карточки товара по каноничному SKU."""
    q = text(
        """
        SELECT id, sku, title, description, quantity_efhc,
               COALESCE(is_active, TRUE) AS is_active,
               extra
          FROM efhc_core.shop_items
         WHERE sku = :code AND COALESCE(is_active, TRUE) = TRUE
         LIMIT 1
        """
    )
    r = (await db.execute(q, {"code": code})).mappings().first()
    if not r:
        msg = f"shop_item code={code} not found or inactive"
        raise ValueError(msg)
    return _item_to_dto(r)


# ---- Создание заказа: внешняя оплата (TON/USDT)
# -------------------------------


def _quote_external_checkout_amount(
    item: ShopItemDTO, payment_method: str,
    custom_efhc_amount_d8: str | Decimal | None,
):
    unit_amount = (
        item.price_ton if payment_method == PAY_TON else item.price_usdt
    )
    if unit_amount is None:
        raise ValueError(f"price_{payment_method.lower()} not set for item")
    custom_amount = _normalize_custom_efhc_amount_d8(custom_efhc_amount_d8)
    if _is_custom_efhc_package(item):
        if custom_amount is None:
            raise ValueError("CUSTOM_EFHC_AMOUNT_REQUIRED")
        total_display = _custom_external_total_d2(unit_amount, custom_amount)
    else:
        if custom_amount is not None:
            raise ValueError("CUSTOM_EFHC_AMOUNT_NOT_ALLOWED_FOR_SKU")
        total_display = normalize_shop_external_price_d2(unit_amount)
    external_amount = external_amount_from_display(
        payment_method, total_display, require_positive=True
    )
    return external_amount, custom_amount


async def create_order_external_in_transaction(
    db: AsyncSession,
    *,
    global_id: int,
    item_code: str,
    payment_method: str,
    client_order_id: str,
    quantity: int = 1,
    custom_efhc_amount_d8: str | Decimal | None = None,
) -> dict[str, Any]:
    """Создать owner-scoped PENDING-заказ для внешней оплаты."""
    if not client_order_id or not client_order_id.strip():
        raise ValueError(
            "client_order_id is required for external orders (idempotency)"
        )
    if int(quantity) != 1:
        raise ValueError("external shop order quantity must be exactly 1")
    if payment_method not in {PAY_TON, PAY_USDT}:
        raise ValueError("PAYMENT_METHOD_NOT_SUPPORTED")

    item = await _get_item_by_code(db, item_code)
    await _lock_selected_vip_number_for_checkout(
        db,
        item=item,
        global_id=int(global_id),
        idempotency_key=str(client_order_id),
    )
    external_amount, custom_amount = _quote_external_checkout_amount(
        item, payment_method, custom_efhc_amount_d8
    )
    if payment_method not in item.pay_currencies:
        raise ValueError("payment method not supported for this item")

    request_quantity = int(quantity)
    if request_quantity != 1:
        raise ValueError("external shop order quantity must be exactly 1")
    expected_amount = external_amount.display
    expected_amount_compat = _legacy_external_amount_d8(expected_amount)
    to_address = str(getattr(settings, "TON_MAIN_WALLET", None) or "").strip()
    memo = _build_memo_for_external(
        item,
        global_id=int(global_id),
        custom_efhc_amount_d8=custom_amount,
    )
    order_extra = _order_extra(
        item,
        payment_method,
        canonical_memo=memo,
        request_quantity=request_quantity,
        unit_amount=external_amount.display,
        expected_amount=external_amount.display,
        to_address=to_address,
        external_amount_atomic=external_amount.atomic,
        external_decimals=external_amount.decimals,
        custom_efhc_amount_d8=custom_amount,
    )

    existing = await _find_shop_order_by_idempotency(
        db,
        global_id=int(global_id),
        idempotency_key=str(client_order_id),
    )
    if existing is not None:
        _assert_shop_order_fingerprint(
            existing,
            global_id=int(global_id),
            item=item,
            payment_method=payment_method,
            request_quantity=request_quantity,
            expected_amount=expected_amount,
            to_address=to_address,
            external_amount_atomic=external_amount.atomic,
            custom_efhc_amount_d8=custom_amount,
        )
        row = existing
    else:
        order_type = _order_type_for_item(item)
        inserted = (
            (
                await db.execute(
                    text(
                        """
                        INSERT INTO efhc_core.shop_orders (
                            global_id, type, status, quantity_efhc,
                            expected_amount, memo, idempotency_key, extra,
                            created_at, updated_at
                        )
                        VALUES (
                            :global_id, :otype, :status, :qty,
                            :expected_amount, :memo, :idk, CAST(:extra AS jsonb),
                            :created_at, :updated_at
                        )
                        ON CONFLICT (global_id, idempotency_key) DO NOTHING
                        RETURNING id, global_id, type, status, quantity_efhc,
                                  expected_amount, memo, tx_hash,
                                  idempotency_key, created_at, extra
                        """
                    ),
                    {
                        "global_id": int(global_id),
                        "otype": order_type,
                        "status": ORDER_STATUS_PENDING,
                        "qty": _scaled_item_quantity_text(
                            item,
                            request_quantity,
                            custom_efhc_amount_d8=custom_amount,
                        ),
                        "expected_amount": str(expected_amount_compat),
                        "memo": memo,
                        "idk": str(client_order_id),
                        "extra": json.dumps(order_extra),
                        "created_at": _now_utc(),
                        "updated_at": _now_utc(),
                    },
                )
            )
            .mappings()
            .first()
        )
        if inserted is None:
            existing = await _find_shop_order_by_idempotency(
                db,
                global_id=int(global_id),
                idempotency_key=str(client_order_id),
            )
            if existing is None:
                raise RuntimeError("shop order insert/select returned no row")
            _assert_shop_order_fingerprint(
                existing,
                global_id=int(global_id),
                item=item,
                payment_method=payment_method,
                request_quantity=request_quantity,
                expected_amount=expected_amount,
                to_address=to_address,
                external_amount_atomic=external_amount.atomic,
                custom_efhc_amount_d8=custom_amount,
            )
            row = existing
        else:
            row = dict(inserted)

    extra = _shop_order_extra_from_row(row)
    order = OrderDTO(
        id=int(row["id"]),
        global_id=int(row["global_id"]),
        status=str(row["status"]),
        memo=row.get("memo"),
        tx_hash=row.get("tx_hash"),
        created_at=row["created_at"],
        order_type=row.get("type"),
        quantity_efhc=(
            str(row["quantity_efhc"])
            if row.get("quantity_efhc") is not None
            else None
        ),
        expected_amount=(
            str(row["expected_amount"])
            if row.get("expected_amount") is not None
            else None
        ),
        payment_method=str(extra.get("payment_method") or payment_method),
        sku=str(extra.get("sku") or item.code),
    )
    persisted_external = external_amount_from_atomic(
        str(extra.get("payment_method") or payment_method),
        str(extra.get("external_amount_atomic") or external_amount.atomic),
        require_positive=True,
    )
    persisted_wallet = str(extra.get("to_address") or "").strip()
    return {
        "order": asdict(order),
        "pay": {
            "method": str(extra.get("payment_method") or payment_method),
            "amount": persisted_external.display_text,
            "external_amount_atomic": str(persisted_external.atomic),
            "external_decimals": persisted_external.decimals,
            "memo": str(row.get("memo") or memo),
            "to_wallet": persisted_wallet,
        },
    }


async def create_order_external(
    db: AsyncSession,
    *,
    global_id: int,
    item_code: str,
    payment_method: str,
    client_order_id: str,
    quantity: int = 1,
    custom_efhc_amount_d8: str | Decimal | None = None,
) -> dict[str, Any]:
    """Compatibility root wrapper для standalone external-order callers.

    Selected VIP number requires one atomic order+PaymentIntent transaction and
    therefore is intentionally unavailable through this compatibility wrapper.
    """
    item = await _get_item_by_code(db, item_code)
    if _is_selected_vip_number_item(item):
        raise ValueError("VIP_NUMBER_REQUIRES_ATOMIC_PAYMENT_INTENT")
    try:
        result = await create_order_external_in_transaction(
            db,
            global_id=global_id,
            item_code=item_code,
            payment_method=payment_method,
            client_order_id=client_order_id,
            quantity=quantity,
            custom_efhc_amount_d8=custom_efhc_amount_d8,
        )
        await db.commit()
        return result
    except BaseException:
        await db.rollback()
        raise


# ---- Создание заказа: внутренняя оплата EFHC
# ----------------------------------


async def purchase_with_efhc(
    db: AsyncSession,
    *,
    global_id: int,
    item_code: str,
    qty: int = 1,
    idempotency_key: str,
) -> dict[str, Any]:
    """Купить Shop item за EFHC одной root DB transaction."""
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("Idempotency-Key is required")
    if qty < 1 or qty > 10:
        raise ValueError("qty must be 1..10")

    item = await _get_item_by_code(db, item_code)
    if PAY_EFHC not in item.pay_currencies:
        raise ValueError("EFHC payment not supported for this item")
    if item.price_efhc is None or item.price_efhc <= 0:
        raise ValueError("price_efhc not set")

    need = d8(d8(item.price_efhc) * Decimal(int(qty)))

    # Не проверяем текущий баланс до idempotent money primitive: точный
    # replay уже committed spend (включая legacy-окно «деньги без заказа»)
    # должен дочитаться/долечить order, даже если текущий баланс уже ниже need.
    # Для новой операции достаточность средств проверяет locked canonical
    # transactions_service внутри той же root transaction.
    owner = await resolve_financial_read_owner(db, global_id=int(global_id))
    await _lock_selected_vip_number_for_checkout(
        db,
        item=item,
        global_id=owner.global_id,
        idempotency_key=str(idempotency_key),
    )
    status = ORDER_STATUS_PAID_AUTO
    if _is_vip_item(item):
        status = ORDER_STATUS_PAID_PENDING_MANUAL
    order_type = _order_type_for_item(item)
    order_extra = _order_extra(
        item,
        PAY_EFHC,
        request_quantity=int(qty),
        unit_amount=d8(item.price_efhc),
        expected_amount=need,
    )

    try:
        existing = await _find_shop_order_by_idempotency(
            db,
            global_id=owner.global_id,
            idempotency_key=str(idempotency_key),
        )
        if existing is not None:
            _assert_shop_order_fingerprint(
                existing,
                global_id=owner.global_id,
                item=item,
                payment_method=PAY_EFHC,
                request_quantity=int(qty),
                expected_amount=need,
            )

        async def guard_new_shop_balance_spend() -> None:
            await require_no_active_shop_preparation(db, global_id=owner.global_id)
            await require_no_active_legacy_shop_intent(db, global_id=owner.global_id)

        tx_result = await bank.spend_user_to_bank_bonus_then__main__nocommit(
            db,
            global_id=owner.global_id,
            amount=d8(need),
            reason=f"shop:{item.code}",
            idempotency_key=str(idempotency_key),
            before_new_spend=guard_new_shop_balance_spend,
            meta={
                "module": "shop_service",
                "item_code": str(item.code),
                "qty": int(qty),
                "shop_expected_amount": str(need),
            },
        )
        debited_bonus, debited_main, transfer_log_id = (
            await _shop_spend_breakdown_from_ledger(
                db,
                global_id=owner.global_id,
                item_code=str(item.code),
                request_quantity=int(qty),
                expected_amount=need,
                idempotency_key=str(idempotency_key),
            )
        )

        if existing is not None:
            row = existing
        else:
            inserted = (
                (
                    await db.execute(
                        text(
                            """
                            INSERT INTO efhc_core.shop_orders (
                                global_id, type, status, quantity_efhc,
                                expected_amount, memo, idempotency_key, extra,
                                created_at, updated_at
                            )
                            VALUES (
                                :global_id, :otype, :status, :qty,
                                :expected_amount, NULL, :idk, CAST(:extra AS jsonb),
                                NOW(), NOW()
                            )
                            ON CONFLICT (global_id, idempotency_key) DO NOTHING
                            RETURNING id, global_id, type, status,
                                      quantity_efhc, expected_amount, memo,
                                      tx_hash, idempotency_key, created_at, extra
                            """
                        ),
                        {
                            "global_id": owner.global_id,
                            "otype": order_type,
                            "status": status,
                            "qty": _scaled_item_quantity_text(item, int(qty)),
                            "expected_amount": str(need),
                            "idk": str(idempotency_key),
                            "extra": json.dumps(order_extra),
                        },
                    )
                )
                .mappings()
                .first()
            )
            if inserted is None:
                concurrent = await _find_shop_order_by_idempotency(
                    db,
                    global_id=owner.global_id,
                    idempotency_key=str(idempotency_key),
                )
                if concurrent is None:
                    raise RuntimeError(
                        "idempotent order insert failed unexpectedly"
                    )
                _assert_shop_order_fingerprint(
                    concurrent,
                    global_id=owner.global_id,
                    item=item,
                    payment_method=PAY_EFHC,
                    request_quantity=int(qty),
                    expected_amount=need,
                )
                row = concurrent
            else:
                row = dict(inserted)

        await _claim_selected_vip_number_in_transaction(
            db,
            item=item,
            global_id=owner.global_id,
            idempotency_key=str(idempotency_key),
            order_id=int(row["id"]),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {
        "ok": True,
        "sku": str(item.code),
        "quantity": int(qty),
        "debited_bonus_efhc": debited_bonus,
        "debited__main__efhc": debited_main,
        "total_debited_efhc": d8(debited_bonus + debited_main),
        "bank_transfer_log_id": int(transfer_log_id or tx_result.created_log_id or 0),
        "idempotency_key": str(idempotency_key),
        "message": f"shop_order_id={int(row['id'])}; status={row['status']}",
        "processed_at": row["created_at"],
    }


async def admin_list_items(db: AsyncSession) -> list[dict[str, Any]]:
    """Вернуть полный canonical каталог для Admin Shop Editor."""
    q = text(
        """
        SELECT id, sku, title, description, quantity_efhc,
               COALESCE(is_active, TRUE) AS is_active,
               extra, created_at, updated_at
          FROM efhc_core.shop_items
         ORDER BY COALESCE((extra->>'sort_order')::int, 100000), id ASC
        """
    )
    rows = (await db.execute(q)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        extra = _extra_obj(row)
        status = str(
            extra.get("status")
            or ("live" if bool(row.get("is_active")) else "hidden")
        )
        history = extra.get("history") or []
        if not isinstance(history, list):
            history = []
        out.append(
            {
                "id": int(row["id"]),
                "code": str(row.get("sku") or ""),
                "sku": str(row.get("sku") or ""),
                "title": str(row.get("title") or ""),
                "description": str(row.get("description") or ""),
                "item_type": str(
                    extra.get("item_type") or ITEM_TYPE_VIRTUAL
                ),
                "is_active": bool(row.get("is_active", True)),
                "status": status,
                "quantity_efhc": (
                    str(row.get("quantity_efhc"))
                    if row.get("quantity_efhc") is not None
                    else str(extra.get("quantity_efhc") or "")
                ),
                "image_url": str(extra.get("image_url") or ""),
                "price_efhc": str(extra.get("price_efhc") or ""),
                "price_ton": str(extra.get("price_ton") or ""),
                "price_usdt": str(extra.get("price_usdt") or ""),
                "price_diagnostics": {
                    asset: issue
                    for asset, issue in (
                        (
                            "TON",
                            shop_external_price_diagnostic(extra.get("price_ton")),
                        ),
                        (
                            "USDT",
                            shop_external_price_diagnostic(extra.get("price_usdt")),
                        ),
                    )
                    if issue is not None
                },
                "pay_currencies": _pay_methods_from_item(row),
                "category": str(extra.get("category") or "other"),
                "badge": str(extra.get("badge") or ""),
                "action_mode": str(extra.get("action_mode") or "checkout"),
                "external_url": str(extra.get("external_url") or ""),
                "delivery_mode": str(
                    extra.get("delivery_mode")
                    or (
                        "bank_credit"
                        if str(extra.get("item_type")) == ITEM_TYPE_EFHC_PACKAGE
                        else "manual"
                    )
                ),
                "sort_order": int(extra.get("sort_order") or 0),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "history_count": len(history),
                "history_tail": list(history)[:20],
            }
        )
    return out


def _admin_normalize_item_status(status: str | None) -> tuple[str, bool]:
    st = str(status or "draft").lower()
    if st not in {"live", "hidden", "draft"}:
        st = "draft"
    return st, st == "live"


def _admin_item_snapshot(row: Any) -> dict[str, Any]:
    extra = _extra_obj(row)
    return {
        "sku": str(row.get("sku") or ""),
        "title": str(row.get("title") or ""),
        "description": str(row.get("description") or ""),
        "item_type": str(extra.get("item_type") or ITEM_TYPE_VIRTUAL),
        "is_active": bool(row.get("is_active", True)),
        "status": str(extra.get("status") or "draft"),
        "quantity_efhc": (
            str(row.get("quantity_efhc"))
            if row.get("quantity_efhc") is not None
            else ""
        ),
        "image_url": str(extra.get("image_url") or ""),
        "price_efhc": str(extra.get("price_efhc") or ""),
        "price_ton": str(extra.get("price_ton") or ""),
        "price_usdt": str(extra.get("price_usdt") or ""),
        "pay_currencies": _pay_methods_from_item(row),
        "category": str(extra.get("category") or "other"),
        "badge": str(extra.get("badge") or ""),
        "action_mode": str(extra.get("action_mode") or "checkout"),
        "external_url": str(extra.get("external_url") or ""),
        "delivery_mode": str(extra.get("delivery_mode") or "manual"),
        "sort_order": int(extra.get("sort_order") or 0),
        "updated_at": str(row.get("updated_at") or ""),
    }


async def _admin_get_item_row(
    db: AsyncSession,
    *,
    code: str,
) -> Any | None:
    return (
        await db.execute(
            text(
                """
                SELECT id, sku, title, description, quantity_efhc,
                       COALESCE(is_active, TRUE) AS is_active,
                       extra, created_at, updated_at
                  FROM efhc_core.shop_items
                 WHERE sku = :code
                 LIMIT 1
                """
            ),
            {"code": str(code)},
        )
    ).mappings().first()


async def _admin_append_item_history(
    db: AsyncSession,
    *,
    code: str,
    action: str,
    detail: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    row = await _admin_get_item_row(db, code=code)
    if row is None:
        return
    extra = _extra_obj(row)
    history = extra.get("history") or []
    if not isinstance(history, list):
        history = []
    history.insert(
        0,
        {
            "at": datetime.now(UTC).isoformat(),
            "action": str(action),
            "detail": str(detail),
            "before": before,
            "after": after,
        },
    )
    extra["history"] = history[:50]
    await db.execute(
        text(
            """
            UPDATE efhc_core.shop_items
               SET extra = CAST(:extra AS jsonb), updated_at = NOW()
             WHERE sku = :code
            """
        ),
        {"code": str(code), "extra": json.dumps(extra)},
    )


def _admin_normalize_pay_currencies(
    values: list[str] | None,
    *,
    price_efhc: Decimal | None,
    price_ton: Decimal | None,
    price_usdt: Decimal | None,
) -> list[str]:
    allowed = {PAY_EFHC, PAY_TON, PAY_USDT}
    explicit = [
        str(value).strip().upper()
        for value in (values or [])
        if str(value).strip().upper() in allowed
    ]
    if explicit:
        return list(dict.fromkeys(explicit))
    inferred: list[str] = []
    if price_efhc is not None:
        inferred.append(PAY_EFHC)
    if price_ton is not None:
        inferred.append(PAY_TON)
    if price_usdt is not None:
        inferred.append(PAY_USDT)
    return inferred


async def admin_upsert_item(
    db: AsyncSession,
    *,
    code: str,
    title: str,
    description: str | None = None,
    item_type: str = ITEM_TYPE_EFHC_PACKAGE,
    quantity_efhc: Decimal | None = None,
    image_url: str | None = None,
    status: str = "draft",
    price_efhc: Decimal | None = None,
    price_ton: Decimal | None = None,
    price_usdt: Decimal | None = None,
    pay_currencies: list[str] | None = None,
    category: str | None = None,
    badge: str | None = None,
    action_mode: str = "checkout",
    external_url: str | None = None,
    delivery_mode: str | None = None,
    sort_order: int = 0,
) -> dict[str, Any]:
    """Создать или обновить карточку через единую canonical Shop model."""
    sku = str(code or "").strip()
    if not sku:
        raise ValueError("SHOP_ITEM_SKU_REQUIRED")
    st, active = _admin_normalize_item_status(status)
    pe = d8(price_efhc) if price_efhc is not None else None
    pt = (
        normalize_shop_external_price_d2(price_ton)
        if price_ton is not None else None
    )
    pu = (
        normalize_shop_external_price_d2(price_usdt)
        if price_usdt is not None else None
    )
    qty = d8(quantity_efhc) if quantity_efhc is not None else None
    mode = str(action_mode or "checkout").strip().lower()
    if mode not in {"checkout", "external_link"}:
        raise ValueError("SHOP_ITEM_ACTION_MODE_INVALID")
    url = str(external_url or "").strip()
    if mode == "external_link" and not url:
        raise ValueError("SHOP_ITEM_EXTERNAL_URL_REQUIRED")

    before_row = await _admin_get_item_row(db, code=sku)
    before = _admin_item_snapshot(before_row) if before_row else None
    extra = _extra_obj(before_row) if before_row else {}
    history = extra.get("history") or []
    if not isinstance(history, list):
        history = []
    pays = _admin_normalize_pay_currencies(
        pay_currencies,
        price_efhc=pe,
        price_ton=pt,
        price_usdt=pu,
    )
    item_type_value = str(item_type or ITEM_TYPE_VIRTUAL).strip()
    if delivery_mode is None:
        delivery = (
            "bank_credit"
            if item_type_value == ITEM_TYPE_EFHC_PACKAGE
            else "manual"
        )
    else:
        delivery = str(delivery_mode).strip().lower()
    if delivery not in {"bank_credit", "manual", "external"}:
        raise ValueError("SHOP_ITEM_DELIVERY_MODE_INVALID")

    extra.update(
        {
            "item_type": item_type_value,
            "status": st,
            "image_url": str(image_url or "").strip(),
            "price_efhc": str(pe) if pe is not None else None,
            "price_ton": str(pt) if pt is not None else None,
            "price_usdt": str(pu) if pu is not None else None,
            "pay_currencies": pays,
            "category": str(category or "other").strip() or "other",
            "badge": str(badge or "").strip(),
            "action_mode": mode,
            "external_url": url,
            "delivery_mode": delivery,
            "sort_order": int(sort_order),
            "history": history,
        }
    )
    if qty is not None:
        extra["quantity_efhc"] = str(qty)
    else:
        extra.pop("quantity_efhc", None)

    row = (
        await db.execute(
            text(
                """
                INSERT INTO efhc_core.shop_items (
                    sku, title, description, quantity_efhc,
                    is_active, extra, created_at, updated_at
                ) VALUES (
                    :sku, :title, :description, :quantity_efhc,
                    :is_active, CAST(:extra AS jsonb), NOW(), NOW()
                )
                ON CONFLICT (sku) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    quantity_efhc = EXCLUDED.quantity_efhc,
                    is_active = EXCLUDED.is_active,
                    extra = EXCLUDED.extra,
                    updated_at = NOW()
                RETURNING id
                """
            ),
            {
                "sku": sku,
                "title": str(title),
                "description": description,
                "quantity_efhc": qty,
                "is_active": active,
                "extra": json.dumps(extra),
            },
        )
    ).first()
    after_row = await _admin_get_item_row(db, code=sku)
    await _admin_append_item_history(
        db,
        code=sku,
        action="upsert",
        detail="admin shop item saved",
        before=before,
        after=_admin_item_snapshot(after_row) if after_row else None,
    )
    await db.commit()
    return {"ok": True, "id": int(row[0]) if row else None, "code": sku}


async def admin_set_price(
    db: AsyncSession,
    *,
    code: str,
    price_efhc: Decimal | None = None,
    price_ton: Decimal | None = None,
    price_usdt: Decimal | None = None,
    pay_currencies: list[str] | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    """Совместимо обновить цены через канонический extra JSON."""
    row = await _admin_get_item_row(db, code=code)
    if row is None:
        return {"updated": 0}
    before = _admin_item_snapshot(row)
    extra = _extra_obj(row)
    pe = d8(price_efhc) if price_efhc is not None else _price_from_extra(extra, "price_efhc")
    raw_pt = extra.get("price_ton")
    raw_pu = extra.get("price_usdt")
    pt = (
        normalize_shop_external_price_d2(price_ton)
        if price_ton is not None else _price_from_extra(extra, "price_ton")
    )
    pu = (
        normalize_shop_external_price_d2(price_usdt)
        if price_usdt is not None else _price_from_extra(extra, "price_usdt")
    )
    extra["price_efhc"] = str(pe) if pe is not None else None
    extra["price_ton"] = (
        str(pt) if pt is not None else raw_pt
        if price_ton is None and raw_pt is not None else None
    )
    extra["price_usdt"] = (
        str(pu) if pu is not None else raw_pu
        if price_usdt is None and raw_pu is not None else None
    )
    if pay_currencies is not None:
        extra["pay_currencies"] = _admin_normalize_pay_currencies(
            pay_currencies,
            price_efhc=pe,
            price_ton=pt,
            price_usdt=pu,
        )
    active = bool(row.get("is_active", True)) if is_active is None else bool(is_active)
    if is_active is not None:
        extra["status"] = "live" if active else "hidden"
    await db.execute(
        text(
            """
            UPDATE efhc_core.shop_items
               SET is_active = :active,
                   extra = CAST(:extra AS jsonb),
                   updated_at = NOW()
             WHERE sku = :code
            """
        ),
        {"code": str(code), "active": active, "extra": json.dumps(extra)},
    )
    after_row = await _admin_get_item_row(db, code=code)
    await _admin_append_item_history(
        db,
        code=code,
        action="price",
        detail="admin shop price compatibility update",
        before=before,
        after=_admin_item_snapshot(after_row) if after_row else None,
    )
    await db.commit()
    return {"updated": 1, "code": str(code)}


async def admin_set_item_status(
    db: AsyncSession,
    *,
    code: str,
    status: str,
) -> dict[str, Any]:
    """Изменить статус карточки без удаления её истории."""
    row = await _admin_get_item_row(db, code=code)
    if row is None:
        raise ValueError("SHOP_ITEM_NOT_FOUND")
    before = _admin_item_snapshot(row)
    st, active = _admin_normalize_item_status(status)
    extra = _extra_obj(row)
    extra["status"] = st
    await db.execute(
        text(
            """
            UPDATE efhc_core.shop_items
               SET is_active = :active,
                   extra = CAST(:extra AS jsonb),
                   updated_at = NOW()
             WHERE sku = :code
            """
        ),
        {"code": str(code), "active": active, "extra": json.dumps(extra)},
    )
    after_row = await _admin_get_item_row(db, code=code)
    await _admin_append_item_history(
        db,
        code=code,
        action="status",
        detail=f"admin shop status -> {st}",
        before=before,
        after=_admin_item_snapshot(after_row) if after_row else None,
    )
    await db.commit()
    return {"ok": True, "code": str(code), "status": st, "is_active": active}


async def admin_delete_item(
    db: AsyncSession,
    *,
    code: str,
) -> dict[str, Any]:
    """Удалить карточку только при полном отсутствии order history."""
    before_row = await _admin_get_item_row(db, code=code)
    if before_row is None:
        return {"deleted": 0, "code": str(code), "last_snapshot": None}
    used = int(
        (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*)
                      FROM efhc_core.shop_orders
                     WHERE COALESCE(extra->>'sku', '') = :code
                    """
                ),
                {"code": str(code)},
            )
        ).scalar()
        or 0
    )
    if used > 0:
        raise ValueError(
            "SHOP_ITEM_DELETE_BLOCKED_ORDER_HISTORY: archive or hide item"
        )
    row = (
        await db.execute(
            text(
                "DELETE FROM efhc_core.shop_items WHERE sku = :code RETURNING id"
            ),
            {"code": str(code)},
        )
    ).first()
    await db.commit()
    return {
        "deleted": 1 if row else 0,
        "code": str(code),
        "last_snapshot": _admin_item_snapshot(before_row),
    }


async def admin_order_status_counters(db: AsyncSession) -> dict[str, Any]:
    """Глобальные счётчики заказов по всей таблице, не по UI-странице."""
    status_rows = (
        await db.execute(
            text(
                """
                SELECT status, COUNT(*) AS count
                  FROM efhc_core.shop_orders
                 WHERE status NOT IN ('SELECTED', 'SELECTION_CANCELED')
                 GROUP BY status
                 ORDER BY status
                """
            )
        )
    ).mappings().all()
    payment_rows = (
        await db.execute(
            text(
                """
                SELECT COALESCE(extra->>'payment_method', 'UNKNOWN') AS method,
                       COUNT(*) AS count
                  FROM efhc_core.shop_orders
                 WHERE status NOT IN ('SELECTED', 'SELECTION_CANCELED')
                 GROUP BY COALESCE(extra->>'payment_method', 'UNKNOWN')
                 ORDER BY method
                """
            )
        )
    ).mappings().all()
    statuses = {str(row["status"]): int(row["count"]) for row in status_rows}
    methods = {str(row["method"]): int(row["count"]) for row in payment_rows}
    return {
        "total": sum(statuses.values()),
        "statuses": statuses,
        "payment_methods": methods,
        "pending": int(statuses.get("PENDING", 0)),
        "paid_auto": int(statuses.get("PAID_AUTO", 0)),
        "pending_manual": int(statuses.get("PAID_PENDING_MANUAL", 0)),
        "approved": int(statuses.get("APPROVED", 0)),
        "rejected": int(statuses.get("REJECTED", 0)),
        "cancelled": int(statuses.get("CANCELED", statuses.get("CANCELLED", 0))),
    }


async def admin_force_fulfill_order(
    db: AsyncSession,
    *,
    order_id: int,
    reason: str | None = None,
    actor_global_id: int | None = None,
    admin_id: int | None = None,
    admin_role: str | None = None,
) -> dict[str, Any]:
    """Emergency Admin fulfill с mandatory audit и canonical NFT payment gate."""
    note = str(reason or "").strip()
    if not note:
        raise ValueError("SHOP_FORCE_FULFILL_REASON_REQUIRED")
    if actor_global_id is None or admin_id is None or not str(admin_role or "").strip():
        raise ValueError("SHOP_FORCE_FULFILL_ACTOR_REQUIRED")

    row = (await db.execute(
        text(
            """
            SELECT id, global_id, type, status, quantity_efhc,
                   tx_hash, extra
              FROM efhc_core.shop_orders
             WHERE id = :oid
             FOR UPDATE
            """
        ),
        {"oid": int(order_id)},
    )).mappings().first()
    if row is None:
        raise ValueError("ORDER_NOT_FOUND")
    current = str(row.get("status") or "")
    order_type = str(row.get("type") or "")
    if current in {"REJECTED", "CANCELED", "CANCELLED"}:
        raise ValueError("ORDER_TERMINAL_STATUS_BLOCKS_FORCE_FULFILL")

    if order_type == "NFT":
        # Никакой отдельной force state machine: только canonical paid NFT decision.
        if current == "APPROVED":
            return {
                "ok": True, "order_id": int(order_id), "status": current,
                "credited": False, "already_fulfilled": True, "reason": note,
            }
        if current != "PAID_PENDING_MANUAL":
            raise ValueError("NFT_REQUEST_NOT_WAITING_FOR_DECISION")
        from app.services.admin.admin_vip_nft_service import (
            decide_vip_nft_request,
        )
        result = await decide_vip_nft_request(
            db, order_id=int(order_id), decision="issued", reason=note,
            actor_global_id=int(actor_global_id), admin_id=int(admin_id),
            admin_role=str(admin_role),
        )
        return {**result, "credited": False, "reason": note}

    target = "PAID_AUTO"
    if current == target:
        return {
            "ok": True, "order_id": int(order_id), "status": current,
            "credited": False, "already_fulfilled": True, "reason": note,
        }

    try:
        extra = row.get("extra") or {}
        if not isinstance(extra, dict):
            extra = {}
        payment_method = str(extra.get("payment_method") or "").upper()
        if payment_method in {PAY_TON, PAY_USDT}:
            lock_row = (await db.execute(
                text(
                    "SELECT trusted_operation_at, server_first_seen_at "
                    "FROM efhc_core.tx_hash_locks "
                    "WHERE tx_hash = :tx_hash AND order_id = :order_id LIMIT 1"
                ),
                {"tx_hash": str(row.get("tx_hash") or ""), "order_id": int(order_id)},
            )).mappings().first()
            time_decision = validate_external_financial_execution(
                trusted_operation_at=(lock_row.get("trusted_operation_at") if lock_row else None),
                server_first_seen_at=(lock_row.get("server_first_seen_at") if lock_row else None),
            )
            if not time_decision.allowed:
                raise ValueError(time_decision.code)

        qty = d8(Decimal(str(row.get("quantity_efhc") or "0")))
        if qty <= 0:
            raise ValueError("ORDER_EFHC_QUANTITY_REQUIRED")
        await bank.credit_user_from_bank_nocommit(
            db, global_id=int(row["global_id"]), amount_efhc=qty,
            reason="admin_force_fulfill_shop_order",
            idempotency_key=f"admin:force_fulfill:order:{int(order_id)}",
            meta={
                "module": "shop_service", "order_id": int(order_id),
                "recovery": True, "reason": note,
                "actor_global_id": int(actor_global_id),
                "admin_id": int(admin_id), "admin_role": str(admin_role),
            },
        )
        await db.execute(
            text(
                "UPDATE efhc_core.shop_orders SET status = :status, "
                "payment_error_log = :message, "
                "fulfilled_at = COALESCE(fulfilled_at, NOW()), updated_at = NOW() "
                "WHERE id = :oid"
            ),
            {"oid": int(order_id), "status": target, "message": f"manual fulfill: {note}"},
        )
        from app.services.admin.admin_logging import AdminLogger
        await AdminLogger.write(
            db, actor_global_id=int(actor_global_id), admin_id=int(admin_id),
            action="SHOP_FORCE_FULFILL", entity="shop_order", entity_id=int(order_id),
            details=f"global_id={int(row['global_id']):010d}; reason={note}",
            meta={"admin_role": str(admin_role), "credited_efhc": str(qty)},
            required=True,
        )
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    return {
        "ok": True, "order_id": int(order_id),
        "global_id": f"{int(row['global_id']):010d}",
        "status": target, "credited": True, "already_fulfilled": False,
        "reason": note,
    }



# ---- Витрина заказов пользователя (для WebApp)
# --------------------------------


async def list_orders_for_owner(
    db: AsyncSession,
    *,
    global_id: int,
    limit: int = 50,
    after_id: int | None = None,
    paid_only: bool = False,
) -> list[OrderDTO]:
    """Список заказов только по canonical ``global_id``."""
    limit = max(1, min(int(limit), 200))
    params: dict[str, Any] = {
        "global_id": int(global_id),
        "lim": limit,
    }
    if after_id is not None:
        params["after_id"] = int(after_id)
    if paid_only and after_id is not None:
        query = text(
            "SELECT id, global_id, type, status, quantity_efhc, "
            "expected_amount, memo, tx_hash, idempotency_key, "
            "created_at, updated_at, paid_at, extra "
            "FROM efhc_core.shop_orders "
            "WHERE global_id = :global_id "
            "AND status IN ('PAID_AUTO','PAID_PENDING_MANUAL','APPROVED',"
            "'REJECTED','FULFILLED','ISSUED') "
            "AND id < :after_id ORDER BY id DESC LIMIT :lim"
        )
    elif paid_only:
        query = text(
            "SELECT id, global_id, type, status, quantity_efhc, "
            "expected_amount, memo, tx_hash, idempotency_key, "
            "created_at, updated_at, paid_at, extra "
            "FROM efhc_core.shop_orders "
            "WHERE global_id = :global_id "
            "AND status IN ('PAID_AUTO','PAID_PENDING_MANUAL','APPROVED',"
            "'REJECTED','FULFILLED','ISSUED') "
            "ORDER BY id DESC LIMIT :lim"
        )
    elif after_id is not None:
        query = text(
            "SELECT id, global_id, type, status, quantity_efhc, "
            "expected_amount, memo, tx_hash, idempotency_key, "
            "created_at, updated_at, paid_at, extra "
            "FROM efhc_core.shop_orders "
            "WHERE global_id = :global_id "
            "AND status NOT IN ('SELECTED','SELECTION_CANCELED') "
            "AND id < :after_id ORDER BY id DESC LIMIT :lim"
        )
    else:
        query = text(
            "SELECT id, global_id, type, status, quantity_efhc, "
            "expected_amount, memo, tx_hash, idempotency_key, "
            "created_at, updated_at, paid_at, extra "
            "FROM efhc_core.shop_orders "
            "WHERE global_id = :global_id "
            "AND status NOT IN ('SELECTED','SELECTION_CANCELED') "
            "ORDER BY id DESC LIMIT :lim"
        )
    rows = (await db.execute(query, params)).mappings().all()
    return _order_rows_to_dto(rows)


def _order_rows_to_dto(rows: Sequence[Any]) -> list[OrderDTO]:
    out: list[OrderDTO] = []
    for row in rows:
        extra = row.get("extra") or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}
        out.append(
            OrderDTO(
                id=int(row["id"]),
                global_id=int(row["global_id"]),
                status=str(row["status"]),
                memo=row["memo"],
                tx_hash=row["tx_hash"],
                created_at=row["created_at"],
                updated_at=row.get("updated_at"),
                paid_at=row.get("paid_at"),
                idempotency_key=row.get("idempotency_key"),
                order_type=row.get("type"),
                quantity_efhc=(
                    str(row["quantity_efhc"])
                    if row.get("quantity_efhc") is not None
                    else None
                ),
                expected_amount=(
                    str(row["expected_amount"])
                    if row.get("expected_amount") is not None
                    else None
                ),
                payment_method=extra.get("payment_method"),
                sku=extra.get("sku"),
            )
        )
    return out


# ---- Админ-витрина заказов (глобальный список с курсором)
# ---------------------


async def admin_list_orders(
    db: AsyncSession,
    *,
    limit: int = 50,
    cursor: str | None = None,
    status: str | None = None,
    item_type: str | None = None,
    global_id: int | None = None,
) -> dict[str, Any]:
    """
    Админская витрина заказов с курсорной пагинацией.
    Сортировка: created_at DESC, id DESC.
    Курсор кодирует (created_at_iso, id)
    через encode_cursor/decode_cursor.

    Фильтры:
      • status    — ORDER_STATUS_*
      • item_type — ITEM_TYPE_EFHC_PACKAGE / ITEM_TYPE_NFT_VIP /
        ITEM_TYPE_VIRTUAL
      • global_id   — конкретный пользователь.
    """
    limit = max(1, min(int(limit or 50), 200))

    after_created_at: str | None = None
    after_id: int | None = None
    if cursor:
        try:
            payload = decode_cursor(cursor)
            ts = payload.get("ts")
            after_created_at = str(ts) if ts is not None else None
            pid = payload.get("id")
            after_id = int(pid) if pid is not None else None
        except Exception as e:
            logger.warning(
                "admin_list_orders: bad cursor %s: %s",
                cursor,
                e,
            )

    conds = ["o.status NOT IN ('SELECTED','SELECTION_CANCELED')"]
    params: dict[str, Any] = {}

    if status:
        conds.append("o.status = :st")
        params["st"] = status
    if global_id is not None:
        conds.append("o.global_id = :global_id")
        params["global_id"] = int(global_id)
    if item_type:
        conds.append("o.type = :itype")
        params["itype"] = item_type
    if after_created_at and after_id is not None:
        conds.append("(o.created_at, o.id) < (:ca, :cid)")
        params["ca"] = after_created_at
        params["cid"] = after_id

    where_clause = " AND ".join(conds)

    sql_tpl = """
            SELECT
          o.id,
          o.global_id,
          u.username,
          o.type,
          o.status,
          o.memo,
          o.tx_hash,
          o.payment_error_log,
          o.created_at,
          o.extra,
          o.quantity_efhc,
          o.expected_amount,
          o.paid_at,
          o.fulfilled_at,
          o.updated_at
        FROM efhc_core.shop_orders o
        LEFT JOIN efhc_core.users u ON u.global_id = o.global_id
        WHERE {where_clause}
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT :lim
        """
    q = text(sql_tpl.replace("{where_clause}", where_clause))
    params["lim"] = limit + 1
    # +1: определить наличие next_cursor

    rs = await db.execute(q, params)
    rows = rs.fetchall()

    items: list[dict[str, Any]] = []
    for r in rows[:limit]:
        payment_error_log = r[7]
        extra = r[9] or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}
        item_code = extra.get("sku")
        item_title = extra.get("item_title") or item_code
        payment_method = extra.get("payment_method")
        items.append(
            {
                "id": int(r[0]),
                "global_id": f"{int(r[1]):010d}",
                "username": r[2],
                "item_id": None,
                "item_code": item_code,
                "item_title": item_title,
                "item_type": r[3],
                "status": r[4],
                "payment_method": payment_method,
                "memo": r[5],
                "tx_hash": r[6],
                "payment_error_log": (
                    str(payment_error_log)
                    if payment_error_log is not None
                    else None
                ),
                "created_at": r[8].isoformat() if r[8] else None,
                "quantity_efhc": (
                    str(r[10]) if r[10] is not None else None
                ),
                "expected_amount": (
                    str(r[11]) if r[11] is not None else None
                ),
                "paid_at": r[12].isoformat() if r[12] else None,
                "fulfilled_at": r[13].isoformat() if r[13] else None,
                "updated_at": r[14].isoformat() if r[14] else None,
                "nft_delivery": (
                    extra.get("nft_delivery")
                    if isinstance(extra.get("nft_delivery"), dict)
                    else None
                ),
            }
        )

    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        last_created_at = last[8]
        last_id = last[0]
        if last_created_at:
            next_cursor = encode_cursor(
                {
                    "ts": last_created_at.isoformat(),
                    "id": int(last_id),
                }
            )

    return {"items": items, "next_cursor": next_cursor}


# ====================================================================
# Пояснения «для чайника»:
# • Этот модуль не рассылает деньги сам — все денежные движения проводит
# Банковский сервис (transactions_service); здесь мы
# только инициируем списания.
# EFHC.
# • EFHC-пакеты оплачиваются только внешне (TON/USDT).
#   Мы создаём заказ PENDING и генерируем MEMO.
# – EFHC-пакеты: кредит EFHC пользователю из Банка (read-through
# идемпотентность).
# – VIP NFT: создаётся заявка PAID_PENDING_MANUAL
#   (ручная выдача админом).
# • Внутренние EFHC-покупки (виртуальные товары, VIP за EFHC):
# – списание bonus→main с зачислением в Банк
#   (две операции с под-ключами idk).
# – заявка на VIP создаётся как PAID_PENDING_MANUAL (без автодоставки).
# • Безопасность/ИИ:
# – Идемпотентность: все денежные действия
#   используют idempotency_key (или client_nonce).
# client_order_id).
# – Витрина: возвращает флаги доступности методов оплаты
#   и причины отключения для UI.
# кнопок.
# – Запрет минуса: если EFHC не хватает — покупка
#   за EFHC не выполняется.
# выполняется.
# • Админ-витрина:
# – admin_list_orders даёт список заказов с фильтрами
#   и курсором по (created_at, id).
# (created_at,id),
# чтобы админка могла безопасно листать историю без OFFSET.
# ====================================================================

# ====================================================================
# Контрактный facade маршрутов без расхождения DTO
# ====================================================================

# NOTE (SSOT): фасад ShopFacade ожидает существование этих функций.
# В текущем контуре они служат как контрактные точки расширения.
# Если логика будет реализована в другом модуле, держите эти обёртки
# как стабильный API для routes/facade.


async def get_catalog(*, db: AsyncSession, owner_id: int):
    """Каталог магазина (SKU) для WebApp.

    Канон:
    - Только чтение из efhc_core.shop_items.
    - Никаких денежных операций.
    - Возвращаем items с methods, чтобы router мог добавить дизейблы.
    """
    q = text(
        """
            SELECT
          id, sku, title, description,
          quantity_efhc, COALESCE(is_active, TRUE) AS is_active,
          extra, created_at, updated_at
        FROM efhc_core.shop_items
        WHERE COALESCE(is_active, TRUE) = TRUE
        ORDER BY id ASC
    """
    )
    rows = (await db.execute(q)).mappings().all()
    items = []
    for r in rows:
        item = _item_to_dto(r)
        extra = _extra_obj(r)
        status = str(extra.get("status") or "live")
        if status != "live":
            continue
        if _is_selected_vip_number_item(item) and _active_vip_reservation(extra):
            continue

        methods = {}
        pays_norm = [str(x).upper() for x in item.pay_currencies]
        if PAY_EFHC in pays_norm and item.price_efhc is not None and item.price_efhc > 0:
            methods["EFHC"] = {"price": str(item.price_efhc)}
        if PAY_TON in pays_norm and item.price_ton is not None and item.price_ton > 0:
            methods["TON"] = {"price": str(item.price_ton)}
        if PAY_USDT in pays_norm and item.price_usdt is not None and item.price_usdt > 0:
            methods["USDT"] = {"price": str(item.price_usdt)}

        items.append(
            ShopCatalogItemOut(
                id=int(r["id"]),
                type=str(item.item_type),
                sku=str(item.code),
                title=str(r["title"]),
                description=(
                    str(r["description"]) if r["description"] else None
                ),
                active=bool(r["is_active"]),
                price_efhc=item.price_efhc,
                ton_enabled=(
                    PAY_TON in pays_norm
                    and item.price_ton is not None
                    and item.price_ton > 0
                ),
                ton_dest_address=getattr(
                    settings, "TON_MAIN_WALLET", None
                ),
                ton_price_hint=item.price_ton,
                memo_template=(None),
                max_per_user=None,
                stock_total=None,
                stock_left=None,
                image_url=extra.get("image_url"),
                category=str(extra.get("category") or "other"),
                badge=str(extra.get("badge") or ""),
                status=status,
                action_mode=str(extra.get("action_mode") or "checkout"),
                external_url=str(extra.get("external_url") or "") or None,
                delivery_mode=str(extra.get("delivery_mode") or "manual"),
                quantity_efhc=(
                    str(r["quantity_efhc"])
                    if r.get("quantity_efhc") is not None
                    else None
                ),
                sort_order=int(extra.get("sort_order") or 0),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                methods=methods,
            )
        )

    return ShopCatalogOut(items=items)


async def create_external_order(
    *,
    db: AsyncSession,
    global_id: int,
    payload: ShopOrderExternalIn,
    client_nonce: str | None,
):
    """Контрактная обёртка для routes: создаёт внешний заказ TON/USDT.

    Канон:
    - Денег в EFHC здесь не списываем.
    - Создаём PENDING-заказ в efhc_core.shop_orders.
    - Идемпотентность — через client_nonce (у нас = Idempotency-Key).
    """
    data = await create_order_external(
        db,
        global_id=int(global_id),
        item_code=str(payload.sku),
        payment_method=str(payload.pay_method).upper(),
        client_order_id=str(client_nonce or ""),
        quantity=int(payload.quantity),
        custom_efhc_amount_d8=payload.custom_efhc_amount_d8,
    )
    return data


class ShopFacade(ShopContract):
    """Фасад Shop‑контура: единая точка входа для роутов.

    Что делает:
      • Роуты обращаются только к ShopFacade (контрактный entrypoint).
      • Исключает рассинхрон между routes и services
        по DTO и названиям методов.
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_catalog(self, owner_id: int):
        return await get_catalog(db=self._db, owner_id=int(owner_id))

    async def create_external_order_in_transaction(
        self,
        global_id: int,
        payload: ShopOrderExternalIn,
        client_nonce: str | None,
    ) -> ShopOrderExternalOut:
        data = await create_order_external_in_transaction(
            self._db,
            global_id=int(global_id),
            item_code=str(payload.sku),
            payment_method=str(payload.pay_method).upper(),
            client_order_id=str(client_nonce or ""),
            quantity=int(payload.quantity),
            custom_efhc_amount_d8=payload.custom_efhc_amount_d8,
        )
        return ShopOrderExternalOut(**data)

    async def create_external_order(
        self,
        global_id: int,
        payload: ShopOrderExternalIn,
        client_nonce: str | None,
    ) -> ShopOrderExternalOut:
        data = await create_external_order(
            db=self._db,
            global_id=int(global_id),
            payload=payload,
            client_nonce=client_nonce,
        )
        return ShopOrderExternalOut(**data)

    async def purchase_by_efhc(
        self,
        global_id: int,
        payload: ShopPurchaseByEFHCIn,
        idempotency_key: str,
    ) -> ShopPurchaseByEFHCOut:
        data = await purchase_with_efhc(
            self._db,
            global_id=int(global_id),
            item_code=payload.sku,
            qty=int(payload.quantity),
            idempotency_key=idempotency_key,
        )
        return ShopPurchaseByEFHCOut(**data)

    async def list_orders_by_owner(
        self,
        global_id: int,
        limit: int,
        cursor: str | None,
    ) -> dict:
        after_id: int | None = None
        if cursor:
            try:
                cur = decode_cursor(cursor)
                raw = cur.get("after_id")
                after_id = int(raw) if raw else None
            except Exception:
                after_id = None

        rows = await list_orders_for_owner(
            self._db,
            global_id=int(global_id),
            limit=int(limit),
            after_id=after_id,
        )
        items = [asdict(r) for r in rows]
        next_cursor = None
        if items:
            next_cursor = encode_cursor(
                {"after_id": int(items[-1]["id"])}
            )
        return {"items": items, "next_cursor": next_cursor}




def get_shop_service(
    db: AsyncSession = Depends(get_db),
) -> ShopContract:
    """FastAPI dependency, возвращающая canonical Shop facade."""
    return ShopFacade(db)


# Конструктор совместимости для текущих hub/shopfront route modules.
# Это alias того же canonical facade, а не второй Shop service.
ShopService = ShopFacade
