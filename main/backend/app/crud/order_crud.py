# backend/app/crud/order_crud.py
# ======================================================================
# Назначение кода:
# CRUD-слой таблицы заказов магазина (ShopOrder). Дает безопасные
# операции БД:
# • создать «ожидающий оплаты» заказ (PENDING_PAYMENT) или «внутренний»
# оплаченный (EFHC);
# • найти по id / tx_hash / expected_memo;
# • аккуратно привязать tx_hash и отметить оплату (guarded-апдейты
# статуса);
# • курсорные списки (без OFFSET) и служебные счетчики/очистка.
#
# Канон / инварианты:
# • Денежная логика (списания/начисления EFHC, лимиты, банк) реализуется
# ТОЛЬКО
# в сервисах (transactions_service/shop_service). В CRUD — ни копейки
# логики
# денег.
# • Идемпотентность внешних платежей обеспечивается уникальным tx_hash
# (UNIQUE)
# и детерминированным expected_memo. CRUD поддерживает read-through
# поведение.
# • Все списки — курсорная пагинация по id (ASC), курсор = last_id.
#
# ИИ-защита / самовосстановление:
# • «Guarded» обновления статусов: меняем статус только из ожидаемого
# состояния.
# Это уменьшает гонки при параллельной обработке вотчером/роутами.
# • При конфликте UNIQUE (tx_hash) не валим процесс — читаем
# существующую
# запись
# и возвращаем её (read-through), предоставляя сервису дорешить
# ситуацию.
# • Никаких OFFSET — только курсоры: стабильнее под нагрузкой и при
# больших
# объёмах.
#
# Запреты:
# • Нет списаний/начислений EFHC, не трогаем балансы пользователей и
# банка.
# • Нет commit()/rollback() — транзакцией управляет вызывающий слой
# (service/route).
# • Нет «незавершённостей»/заглушек: функции готовы для продакшена.
# ======================================================================

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

from app.core.logging_core import get_logger
from app.lib.time import utcnow
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# d8 — каноническое округление в Decimal с 8 знаками (округление вниз).
# По проектному канону утилиты округления централизованы.
try:
    from app.deps import (
        d8,
    )
    # основной источник (централизация хелперов)
except Exception:  # pragma: no cover
    # Фолбэк, если deps недоступен на ранней стадии инициализации.
    from app.core.utils_core import d8  # type: ignore

# Модель заказов (ожидается в app.models.shop_models)
try:
    from app.models.shop_models import ShopOrder  # type: ignore
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "Ожидается модель ShopOrder в app.models.shop_models. "
        "Синхронизируйте модели/миграции "
        "перед использованием order_crud."
    ) from exc

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# Базовые «get»
# ----------------------------------------------------------------------


async def get_order_by_id(
    session: AsyncSession,
    order_id: int,
) -> ShopOrder | None:
    """
    Что делает: Возвращает заказ по первичному ключу.
    Исключения: не бросает — возвращает None, если не найден.
    """
    res = await session.execute(
        select(ShopOrder).where(ShopOrder.id == int(order_id)).limit(1)
    )
    return res.scalar_one_or_none()


async def get_order_by_tx_hash(
    session: AsyncSession,
    tx_hash: str,
) -> ShopOrder | None:
    """
    Что делает: Возвращает заказ по уникальному tx_hash.
    Внешняя оплата TON/USDT.
    Исключения: не бросает — возвращает None, если не найден.
    """
    res = await session.execute(
        select(ShopOrder).where(ShopOrder.tx_hash == tx_hash).limit(1)
    )
    return res.scalar_one_or_none()


async def find_pending_by_expected_memo(
    session: AsyncSession,
    *,
    expected_memo: str,
    allowed_statuses: Sequence[str] | None = None,
) -> ShopOrder | None:
    """
    Что делает: Находит «ожидающий оплаты» заказ.
    По детерминированному expected_memo.
    Идемпотентность: верхний слой может повторно вызывать создание.
    Но сначала
    стоит проверить наличие такой «заявки» по expected_memo.
    Чтобы не дублировать.
    """
    stmt = select(ShopOrder).where(
        ShopOrder.expected_memo == expected_memo
    )
    if allowed_statuses:
        stmt = stmt.where(ShopOrder.status.in_(list(allowed_statuses)))
    res = await session.execute(
        stmt.order_by(ShopOrder.id.desc()).limit(1)
    )
    return res.scalar_one_or_none()


# ----------------------------------------------------------------------
# Создание заказов (без бизнес-логики денег)
# ----------------------------------------------------------------------


async def create_order_pending_payment(
    session: AsyncSession,
    *,
    global_id: int,
    item_id: int,
    expected_amount: Decimal,
    expected_currency: str,
    expected_memo: str,
    quantity: int = 1,
    status: str = "PENDING_PAYMENT",
) -> ShopOrder:
    """
    Что делает: Создает заказ в статусе «ожидает внешней оплаты».
    Вход: детерминированный expected_memo.
    Для будущего маппинга на входящий платеж.
    Идемпотентность: контролируется верхним уровнем.
    Сначала find_pending_by_expected_memo.
    Побочные эффекты: только INSERT в таблицу заказов.
    """
    order = ShopOrder(
        global_id=int(global_id),
        item_id=int(item_id),
        status=status,
        expected_amount=d8(expected_amount),
        expected_currency=expected_currency,
        expected_memo=expected_memo,
        quantity=int(quantity),
    )
    session.add(order)
    # Коммит выполняет сервис/роут
    return order


async def create_order_internal_paid(
    session: AsyncSession,
    *,
    global_id: int,
    item_id: int,
    amount: Decimal,
    currency: str = "EFHC",
    comment: str | None = None,
    status: str = "PAID",
) -> ShopOrder:
    """
    Что делает: Создает «внутренний» оплаченный заказ.
    Например, покупка за EFHC.
    Важно: Денежные списания/начисления выполняет сервис.
    transactions_service.
    а CRUD только фиксирует факт заказа.
    """
    order = ShopOrder(
        global_id=int(global_id),
        item_id=int(item_id),
        status=status,
        expected_amount=d8(amount),
        expected_currency=currency,
        expected_memo=None,
        actual_amount=d8(amount),
        actual_currency=currency,
        actual_memo=None,
        admin_comment=(comment or None),
    )
    session.add(order)
    return order


# ----------------------------------------------------------------------
# Обновления статуса и платежных реквизитов (guarded + read-through)
# ----------------------------------------------------------------------


async def attach_tx_hash_if_absent(
    session: AsyncSession,
    *,
    order_id: int,
    tx_hash: str,
) -> ShopOrder:
    """
    Что делает: Привязывает к заказу tx_hash, если он еще не установлен.
    ИИ-защита: При конфликте UNIQUE.
    tx_hash уже привязан к другому заказу
    возвращаем существующую запись (read-through), не валим процесс.
    """
    order = await get_order_by_id(session, order_id)
    if not order:
        raise ValueError("Заказ не найден")

    if order.tx_hash and order.tx_hash != tx_hash:
        # Уже привязано «иное» поступление — отдаём как есть.
        # Пусть сервис
        # решит).
        return order

    order.tx_hash = tx_hash
    try:
        await session.flush()
    except IntegrityError:
        # tx_hash уже занят — возвращаем существующую запись.
        # С этим хэшем
        existing = await get_order_by_tx_hash(session, tx_hash)
        return existing or order
    return order


async def mark_paid_by_external(
    session: AsyncSession,
    *,
    order_id: int,
    tx_hash: str,
    actual_amount: Decimal,
    actual_currency: str,
    actual_memo: str | None,
    expected_prev_status: str = "PENDING_PAYMENT",
    next_status: str = "PAID",
) -> ShopOrder:
    """
    Что делает: Обновляет заказ как «оплаченный» внешним платежом.
    Guarded-логика: статус меняется только из ожидаемого.
    Уменьшаем гонки.
    Побочный эффект: фиксируем сумму/валюту/мемо входящего платежа.
    """
    order = await get_order_by_id(session, order_id)
    if not order:
        raise ValueError("Заказ не найден")

    if order.status != expected_prev_status:
        # Уже обработан кем-то ещё — возвращаем актуальное состояние.
        return order

    order.tx_hash = order.tx_hash or tx_hash
    order.actual_amount = d8(actual_amount)
    order.actual_currency = actual_currency
    order.actual_memo = actual_memo
    order.status = next_status
    await session.flush()
    return order


async def set_status_guarded(
    session: AsyncSession,
    *,
    order_id: int,
    new_status: str,
    expected_prev: Sequence[str] | None = None,
    admin_comment: str | None = None,
) -> ShopOrder:
    """
    Что делает: Универсальный guarded-апдейт статуса.
    Правило: меняем статус, только если текущий входит в expected_prev.
    Если задан.
    Это снижает риск «перепрыгивания» этапов при параллельной обработке.
    """
    order = await get_order_by_id(session, order_id)
    if not order:
        raise ValueError("Заказ не найден")

    if expected_prev and order.status not in expected_prev:
        return order

    order.status = new_status
    if admin_comment is not None:
        order.admin_comment = admin_comment
    await session.flush()
    return order


# ----------------------------------------------------------------------
# Курсорные списки (без OFFSET)
# ----------------------------------------------------------------------


async def list_orders_admin(
    session: AsyncSession,
    *,
    limit: int = 50,
    after_id: int | None = None,
    statuses: Sequence[str] | None = None,
    global_id: int | None = None,
) -> tuple[list[ShopOrder], int | None]:
    """
    Что делает: Админ-витрина заказов.
    Курсорная пагинация по id (ASC).
    Фильтры: по статусам и конкретному пользователю (опционально).
    """
    stmt = select(ShopOrder)
    if statuses:
        stmt = stmt.where(ShopOrder.status.in_(list(statuses)))
    if global_id is not None:
        stmt = stmt.where(
            ShopOrder.global_id == int(global_id)
        )
    if after_id:
        stmt = stmt.where(ShopOrder.id > int(after_id))
    stmt = stmt.order_by(ShopOrder.id.asc()).limit(int(limit))

    res = await session.execute(stmt)
    items = list(res.scalars().all())
    next_cursor = None
    if items and len(items) == int(limit):
        next_cursor = items[-1].id
    return items, next_cursor


# ----------------------------------------------------------------------
# Наблюдаемость и периодическая уборка
# ----------------------------------------------------------------------


async def count_by_status(
    session: AsyncSession,
) -> list[tuple[str, int]]:
    """
    Что делает: Возвращает пары (status, count) — для админ-статистики.
    """
    res = await session.execute(
        select(
            ShopOrder.status,
            func.count(ShopOrder.id),
        ).group_by(ShopOrder.status)
    )
    return [(row[0], row[1]) for row in res.all()]


async def delete_cancelled_older_than(
    session: AsyncSession,
    *,
    days: int = 30,
    batch_limit: int = 1000,
) -> int:
    """
    Что делает: Мягкая очистка.
    Удаляет CANCELLED/EXPIRED/FAILED старше N дней партиями.
    Почему батчи: чтобы не держать долгую транзакцию.
    И не блокировать индексы.
    Возвращает: сколько записей удалено в текущем вызове.
    До batch_limit.
    """
    threshold = utcnow() - timedelta(days=int(days))
    res = await session.execute(
        select(ShopOrder)
        .where(
            and_(
                ShopOrder.updated_at < threshold,
                ShopOrder.status.in_(
                    ["CANCELLED", "EXPIRED", "FAILED"]
                ),
            )
        )
        .order_by(ShopOrder.id.asc())
        .limit(int(batch_limit))
    )
    items = list(res.scalars().all())
    for o in items:
        await session.delete(o)
    # flush/commit — на вызывающем уровне
    return len(items)


# ======================================================================
# Пояснения «для чайника»:
# • Почему без бизнес-логики денег?
# Любая денежная операция (списание/начисление EFHC) обязана идти через
# transactions_service, чтобы соблюсти канон: банк — единственный
# источник
# EFHC,
# идемпотентность, зеркальные логи и запреты (P2P/обратная конверсия).
#
# • Зачем guarded-апдейты статуса?
# Чтобы две параллельные обработки не «перепрыгнули» шаги друг друга: мы
# меняем
# статус только из ожидаемого, а при несовпадении возвращаем текущее
# состояние
# —
# пусть сервис решит, что делать дальше.
#
# • Почему курсорная пагинация?
# OFFSET медленный и нестабилен под нагрузкой. Курсор по id работает
# быстрее и
# предсказуемей, идеально для мобильного UI с «подгрузить ещё».
#
# • Что делать при конфликте tx_hash?
# CRUD не валит процесс: возвращает существующую запись (read-through).
# Логику
# итоговый статус решает сервис/вотчер по правилам идемпотентности.
# ======================================================================
