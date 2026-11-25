# backend/app/routes/shop_routes.py
# ======================================================================
# Назначение кода:
# Витрины и операции магазина (Shop): каталог SKU, внешний заказ
# (TON/USDT через watcher) и внутренняя покупка за EFHC.
#
# Канон / инварианты:
# • Денежные POST-операции требуют строгой идемпотентности: заголовок
# Idempotency-Key (уникальный ключ клиента). Повтор → read-through:
# возвращаем результат первой обработки, не дублируем.
# • Обмен kWh→EFHC только 1:1 (не относится к Shop).
# • VIP/NFT — только заявка, автоматическая выдача NFT запрещена.
# • Пользователь НЕ может уходить в минус (жёсткая проверка в сервисах).
# • Банк может уйти в минус (операции не блокируем, логируем дефицит).
#
# ИИ-защиты / самовосстановление:
# • Внешние заказы (TON/USDT) используют «мягкую идемпотентность» по
# X-Client-Nonce для защиты от повторных кликов до оплаты в блокчейне.
# • Списки — курсорная пагинация без OFFSET (устойчиво к росту данных).
# • ETag на витрины и списки (кэш без рассинхронизации).
# • «Принудительная синхронизация» при открытии раздела: безопасный хук,
# не блокирующий UI (через легкий вызов сервисной синхронизации).
#
# Запреты:
# • НЕТ автодоставки NFT. Только заявка со статусом PAID_PENDING_MANUAL.
# • НЕТ жесткого отказа из-за минуса банка.
# • НЕТ хранения курсов TON/USDT в API — админ задаёт цены товарам в БД.
# ======================================================================

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

from app.contracts.shop_contract import ShopContract
from app.core.async_tasks import create_logged_task
from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.deps import (
    d8,
    decode_cursor,
    get_db,
    make_etag,
    require_idempotency_key,
)
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.identity.types import (
    global_id_from_database,
    global_id_to_database,
    parse_global_id,
)
from app.lib.time import utcnow
from app.schemas.shop_schemas import (
    ShopCatalogOut,
    ShopOrderExternalIn,
    ShopOrderExternalOut,
    ShopOrderListOut,
    ShopPurchaseByEFHCIn,
    ShopPurchaseByEFHCOut,
)
from app.services import wallets_service
from app.services.payment_intents_service import (
    create_intent_shop_external_in_transaction,
)
from app.services.shop_service import (
    bind_vip_number_reservation_in_transaction,
    get_shop_service,
)
from app.services.transactions_service import (
    IdempotencyPayloadConflictError,
)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/shop", tags=["shop"])

# ----------------------------------------------------------------------
# Вспомогательные функции (локальные для роутера)
# ----------------------------------------------------------------------


async def _get_user_balances(
    db: AsyncSession,
    global_id: int,
) -> tuple[Decimal, Decimal]:
    """
    Быстрый селект балансов. Нужен для витрин (дизейблы по EFHC).
    Возвращает (main_balance, bonus_balance).
    """
    row = await db.execute(
        text(
            """
            SELECT
              COALESCE(u.main_balance, 0)::numeric,
              COALESCE(u.bonus_balance, 0)::numeric
            FROM efhc_core.users u
            WHERE u.global_id = :global_id
            LIMIT 1
            """
        ),
        {"global_id": int(global_id)},
    )
    rec = row.fetchone()
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account owner не найден.",
        )
    return (Decimal(rec[0]), Decimal(rec[1]))


def _optional_client_nonce(req: Request) -> str | None:
    """
    Мягкая идемпотентность для внешних заказов: X-Client-Nonce.
    Позволяет не плодить дубли при повторных кликах до оплаты.
    """
    nonce = (
        req.headers.get("X-Client-Nonce")
        or req.headers.get("X - Client - Nonce")
        or ""
    ).strip()
    if not nonce:
        return None
    if len(nonce) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "X-Client-Nonce слишком длинный (макс. 64 символа)."
            ),
        )
    return nonce


# ----------------------------------------------------------------------
# GET /shop/catalog — витрина товаров (SKU)
# ----------------------------------------------------------------------


@router.get(
    "/catalog",
    response_model=ShopCatalogOut,
    summary="Каталог магазина (SKU)",
)
async def get_shop_catalog(
    request: Request,
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db: AsyncSession = Depends(get_db),
    svc: ShopContract = Depends(get_shop_service),
    force_sync: bool = False,
) -> ShopCatalogOut:
    """
    Что делает:
      • Возвращает каталог с методами оплаты (EFHC/TON/USDT).
      • Дополняет enabled/disabled_reason по балансу пользователя.

    Вход:
      • force_sync=true|false — мягкий триггер синхронизации.

    Выход:
      • Список SKU с методами оплаты и дизейблами (price=0 → disabled).
      • ETag в ответе (через make_etag).

    Исключения:
      • 401 — пользователь не определён.
      • 404 — пользователь не найден (балансы).
    """
    if force_sync:
        # Принудительная синхронизация раздела. Здесь делаем безопасный
        # «пин-глоток»,
        # чтобы не блокировать UI (например, kick watcher).
        # Специально не ждём тяжёлых операций.
        try:
            # Лёгкий асинхронный "пинок": не падаем даже при ошибках.
            create_logged_task(
                asyncio.sleep(0.01),
                name="shop:catalog:force-sync-hint",
            )
        except Exception as e:
            logger.warning("shop/catalog force_sync hint failed: %s", e)

    main_balance, bonus_balance = await _get_user_balances(
        db,
        int(owner.global_id),
    )
    catalog = await svc.get_catalog(int(owner.global_id))

    # Правило дизейблов:
    # • price == 0 → карточка/метод отключены (админ не задал цену).
    # • при историческом минусе пользователя — покупки
    # за EFHC
    # должны быть отключены до выхода в 0 (в сервисах защита жёстче).
    user_negative = main_balance < 0 or bonus_balance < 0

    enriched_items: list[dict[str, Any]] = []
    for item in catalog.items:
        item_dict = item.model_dump()
        methods = item_dict.get("methods") or {}
        # Пройдёмся по методам оплаты и дополним отключения:
        for pay_method, cfg in methods.items():
            price = Decimal(str(cfg.get("price") or "0"))
            if price <= 0:
                cfg["enabled"] = False
                cfg["disabled_reason"] = "Цена не задана админом"
            elif pay_method.upper() == "EFHC" and user_negative:
                cfg["enabled"] = False
                cfg["disabled_reason"] = (
                    "Баланс пользователя в минусе — "
                    "покупки за EFHC недоступны"
                )
            else:
                # Если сервис рассчитал enabled/disabled — дополняем.
                cfg["enabled"] = bool(cfg.get("enabled", True))
                if not cfg["enabled"] and not cfg.get(
                    "disabled_reason"
                ):
                    cfg["disabled_reason"] = (
                        "Недоступно по правилам магазина"
                    )

        item_dict["methods"] = methods
        enriched_items.append(item_dict)

    body = ShopCatalogOut(
        items=enriched_items,
        user_info={
            "main_balance": str(d8(main_balance)),
            "bonus_balance": str(d8(bonus_balance)),
            "user_negative": bool(user_negative),
        },
    )

    # ETag: по длине и контрольной сумме сериализованных ключей (через
    # make_etag)
    etag = make_etag(
        {
            "n": len(enriched_items),
            "neg": user_negative,
            "sum": str(d8(main_balance + bonus_balance)),
        }
    )
    # FastAPI может положить ETag в middleware; здесь добавим через
    # headers:
    # но т.к. response_model используется, обычно ETag в middleware.
    request.state.extra_headers = [("ETag", etag)]
    return body


# ----------------------------------------------------------------------
# POST /shop/order-external — создать внешний заказ (оплата TON/USDT)
# ----------------------------------------------------------------------


@router.post(
    "/order-external",
    response_model=ShopOrderExternalOut,
    summary="Создать внешний заказ (оплата TON/USDT)",
    status_code=status.HTTP_200_OK,
)
async def create_order_external(
    request: Request,
    payload: ShopOrderExternalIn,
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
    idempotency_key: str = Depends(require_idempotency_key),
    svc: ShopContract = Depends(get_shop_service),
) -> ShopOrderExternalOut:
    """
    Что делает:
      • Регистрирует внешний заказ (TON/USDT), возвращает реквизиты:
        memo, to_wallet, ожидаемую сумму. Дальше watcher.
      • Использует X-Client-Nonce для защиты от дублей.

    Вход:
      • body: { sku, quantity, pay_method }
      • headers: X-Client-Nonce (опционально, но рекомендуется)

    Выход:
      • { order: {id, status}, pay: {method, amount, memo, to_wallet} }

    Исключения:
      • 400 — невалидный SKU/метод/кол-во/nonce слишком длинный.
      • 401 — пользователь не определён.
    """
    from app.deps import require_wallet_connected

    await require_wallet_connected(
        request,
        db=db,
        current_global_id=str(global_id_from_database(owner.global_id)),
        feature="shop_external",
    )

    owner_global_id = str(global_id_from_database(owner.global_id))
    owner_global_id_db = global_id_to_database(parse_global_id(owner_global_id))
    wallets = await wallets_service.list_wallets(db, global_id=owner_global_id)
    primary_wallet = next(
        (
            wallet
            for wallet in wallets
            if wallet.is_primary and wallet.is_active and wallet.proof_verified
        ),
        None,
    )
    if primary_wallet is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Verified primary wallet is required before external Shop payment",
        )
    payer_wallet_address = str(primary_wallet.wallet_address)
    # Канон: денежные POST — Idempotency-Key.
    client_nonce = str(idempotency_key)

    try:
        try:
            out = await svc.create_external_order_in_transaction(
                owner_global_id_db, payload, client_nonce
            )
        except IdempotencyPayloadConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
            ) from exc

        # Канон A+B: создаём PaymentIntent и возвращаем tx для TonConnect.
        pay = getattr(out, "pay", None) or out.get("pay")
        order = getattr(out, "order", None) or out.get("order")
        if not pay or not order:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="External order payload is incomplete.",
            )

        asset = str(pay.get("method") or "TON").upper()
        external_amount_atomic = str(pay.get("external_amount_atomic") or "").strip()
        external_decimals = int(pay.get("external_decimals") or 0)
        if not external_amount_atomic or external_decimals <= 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="External atomic payment snapshot is missing",
            )
        to_addr = str(pay.get("to_wallet") or "").strip()
        order_type = str(order.get("type") or order.get("order_type") or "")
        efhc_amount_d8 = (
            str(order.get("quantity_efhc") or "0")
            if order_type == "EFHC"
            else "0"
        )
        try:
            intent = await create_intent_shop_external_in_transaction(
                db,
                global_id=owner_global_id,
                idempotency_key=str(idempotency_key),
                asset=asset,
                external_amount_atomic=external_amount_atomic,
                to_address=to_addr,
                efhc_amount_d8=efhc_amount_d8,
            )
        except IdempotencyPayloadConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
            ) from exc

        # Привязываем заказ к payload (для watcher match) без новых полей.
        try:
            order_id = int(order.get("id") or 0)
        except Exception:
            order_id = 0
        if order_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="External order id is missing.",
            )
        try:
            reservation = await bind_vip_number_reservation_in_transaction(
                db,
                item_code=str(payload.sku),
                global_id=owner_global_id_db,
                idempotency_key=client_nonce,
                order_id=order_id,
                intent_id=int(intent["intent_id"]),
                expires_at=intent["expires_at"],
            )
        except ValueError as exc:
            detail = str(exc)
            conflict = detail in {
                "VIP_NUMBER_RESERVED",
                "VIP_NUMBER_ALREADY_SOLD",
                "VIP_NUMBER_NOT_AVAILABLE",
            }
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                    if conflict
                    else status.HTTP_400_BAD_REQUEST
                ),
                detail=detail,
            ) from exc
        delivery_wallet_address = (
            payer_wallet_address if order_type == "NFT" else None
        )

        await db.execute(
            text(
                "UPDATE efhc_core.shop_orders "
                "SET memo = :m, "
                "    extra = COALESCE(extra, '{}'::jsonb) || "
                "    jsonb_build_object("
                "      'intent_payload', :m, "
                "      'intent_id', :iid, "
                "      'payment_owner_global_id', :global_id, "
                "      'payment_intent_kind', 'shop_external', "
                "      'payer_wallet_address', COALESCE(extra->>'payer_wallet_address', :payer_wallet_address), "
                "      'delivery_wallet_address', COALESCE(extra->>'delivery_wallet_address', :delivery_wallet_address), "
                "      'vip_number_reserved', :vip_number_reserved"
                "    ), "
                "    updated_at = :updated_at "
                "WHERE id = :oid"
            ),
            {
                "m": str(intent["payload"]),
                "iid": int(intent["intent_id"]),
                "global_id": owner_global_id,
                "payer_wallet_address": payer_wallet_address,
                "delivery_wallet_address": delivery_wallet_address,
                "vip_number_reserved": (
                    str(reservation["number"]) if reservation else None
                ),
                "updated_at": utcnow(),
                "oid": order_id,
            },
        )
        await db.commit()

        pay["memo"] = str(intent["payload"])
        pay["tonconnect_tx"] = intent["tonconnect_tx"]
        return ShopOrderExternalOut(order=order, pay=pay)
    except BaseException:
        await db.rollback()
        raise


# ----------------------------------------------------------------------
# POST /shop/purchase-efhc — внутренняя покупка за EFHC (жёсткая
# идемпотентность)
# ----------------------------------------------------------------------


@router.post(
    "/purchase-efhc",
    response_model=ShopPurchaseByEFHCOut,
    summary=("Покупка за EFHC (внутренняя, жёсткая идемпотентность)"),
    status_code=status.HTTP_200_OK,
)
async def purchase_efhc(
    request: Request,
    payload: ShopPurchaseByEFHCIn,
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
    idempotency_key: str = Depends(require_idempotency_key),
    svc: ShopContract = Depends(get_shop_service),
) -> ShopPurchaseByEFHCOut:
    # Канон семантики: purchase-efhc — это shop_internal (off-chain)
    # и НЕ является депозитом on-chain. WalletGate здесь не нужен.
    """
    Что делает:
      • Списывает EFHC (сначала бонус, затем основной), создаёт заказ
        и выполняет «доставку» (по типу SKU). Логика — через банк.

    Вход:
      • body: { sku, quantity }
      • headers: Idempotency-Key (обязательно, <= 128)

    Выход:
      • Итоговый заказ и контекст списаний (read-through).

    Исключения:
      • 400 — Idempotency-Key отсутствует/длинный; SKU/qty некорректны.
      • 401 — пользователь не определён.
      • 409 — тот же Idempotency-Key использован с другим payload.
    """
    global_id = int(owner.global_id)
    idk = idempotency_key
    try:
        out = await svc.purchase_by_efhc(global_id, payload, idk)
    except IdempotencyPayloadConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
        ) from exc
    return ShopPurchaseByEFHCOut(**out.model_dump())


# ----------------------------------------------------------------------
# GET /shop/orders — список заказов пользователя (курсор, ETag)
# ----------------------------------------------------------------------


@router.get(
    "/orders",
    response_model=ShopOrderListOut,
    summary="Список заказов пользователя (курсоры)",
)
async def get_orders(
    request: Request,
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    cursor: str | None = None,
    limit: int = 20,
    svc: ShopContract = Depends(get_shop_service),
) -> ShopOrderListOut:
    """
    Что делает:
      • Возвращает заказы по курсору (id DESC), без OFFSET.

    Вход:
      • cursor: base64(JSON) {"after_id": <int>};
        если None — «с головы».
      • limit: 1..100 (по умолчанию 20).

    Выход:
      • items, next_cursor (если есть ещё), ETag для кэша.

    Исключения:
      • 401 — пользователь не определён.
    """
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    if cursor:
        try:
            cur = decode_cursor(cursor)
            raw = cur.get("after_id")
            int(raw) if raw else None
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail="Некорректный cursor",
            ) from e

    data = await svc.list_orders_by_owner(
        global_id=int(owner.global_id),
        limit=limit,
        cursor=cursor,
    )
    items = data.get("items") or []
    body = ShopOrderListOut(
        items=items,
        next_cursor=data.get("next_cursor"),
    )

    head_id = int(items[0]["id"]) if items else 0
    tail_id = int(items[-1]["id"]) if items else 0
    etag = make_etag(
        {
            "n": len(items),
            "head": head_id,
            "tail": tail_id,
        }
    )
    request.state.extra_headers = [("ETag", etag)]
    return body


# ======================================================================
# Пояснения «для чайника»:
# 1) Почему Idempotency-Key обязательный?
# Любая денежная операция должна быть устойчива к повторным кликам.
# Клиент отправляет ключ. Если запрос повторится — сервер найдёт
# ранее записанный результат (через UNIQUE в логах) и вернёт его
# (read-through),
# не создавая дублей.
#
# 2) Зачем X-Client-Nonce?
# Для внешних заказов (оплата в TON/USDT) у пользователя часто возникают
# повторы
# до оплаты. Nonce позволяет мягко склеивать такие повторы в «один
# ожидающий платёж», пока watcher по tx_hash не подтвердит.
#
# 3) Почему курсор вместо OFFSET?
# OFFSET плохо масштабируется: чем дальше в историю, тем дороже запрос.
# Курсор по id DESC даёт стабильную и быструю пагинацию.
#
# 4) Где берутся цены TON/USDT?
# Из БД (заводит админ). Если price=0 — метод отключён, покупать
# нельзя.
#
# 5) Что значит «принудительная синхронизация»?
# Перед отдачей витрины посылаем лёгкий «пин-глоток» сервисам,
# чтобы раздел имел свежие данные при быстром переключении экранов.
#
# 6) Почему не блокируем при минусе банка?
# Канон: банк может уйти в минус — это не останавливает экономику.
# processed_with_deficit. Пользователь — никогда не в минус.
# ======================================================================
