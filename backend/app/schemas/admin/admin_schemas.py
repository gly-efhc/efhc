# backend/app/schemas/admin_schemas.py
# ====================================================================
# Назначение кода:
# Pydantic-схемы админского API EFHC Bot: эмиссия/сжигание через Банк,
# «насильные» движения между пользователем и Банком
# (строго через банк-сервис), реконсиляция TON-входящих,
# отчётность, управление витринами Shop/Tasks,
# модерация заявок на вывод EFHC и заявок на NFT.
#
# Канон / инварианты:
# • Все денежные операции — только через единый банковский сервис
# (transactions_service).
# • Денежные POST обязаны требовать Idempotency-Key
# (проверяется в роутере).
# • Банк может уходить в минус (это допустимо);
# пользователи — НЕТ (жёсткий запрет).
# • Внутренний курс фиксированный: 1 EFHC = 1 кВт·ч;
# обратной конверсии нет.
# • NFT — только по заявке (ручная выдача админом);
# автодоставки NFT нет.
#
# ИИ-защиты:
# • Все суммы нормализуем как строки с 8 знаками (ROUND_DOWN),
# единый формат
# для фронта.
# • В админских входных моделях предусмотрены поля audit/meta
# для трассировки.
# • Для тяжёлых операций (реконсиляция TON) — dry_run и лимиты, чтобы не
# «ронять» процесс.
#
# Запреты:
# • Нет прямого редактирования балансов пользователей — только через
# банк-операции.
# • Нет P2P-переводов user→user.
# • Нет «суточных» ставок; бизнес-логика не живёт в схемах (только форма
# данных).
# ====================================================================

from __future__ import annotations

# ====================================================================
# Импорты
# --------------------------------------------------------------------
from datetime import datetime
from typing import Any, Literal, cast

from app.identity.api_contract import ApiExternalGlobalId
from app.schemas.common_schemas import (
    BalancePair,
    CursorPage,
    EfhcBaseModel,
    IdempotencyContract,
    OkMeta,
    d8_str,
)
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import Field, field_validator

# ====================================================================
# Базовые вспомогательные DTO (админ-трассировка)
# --------------------------------------------------------------------


class AdminActor(EfhcBaseModel):
    """Кто инициировал действие (для аудита и UI - протоколирования)."""

    admin_global_id: ApiExternalGlobalId = Field(
        ...,
        description="Канонический global_id администратора.",
    )
    comment: str | None = Field(
        None,
        description="Короткая пометка/причина действия",
    )


# ====================================================================
# Блок: Эмиссия и «сжигание» EFHC (только через Банк)
# --------------------------------------------------------------------


class AdminEmitIn(IdempotencyContract):
    """
    Вход эмиссии EFHC в Банк.
    Денежная операция — требуется заголовок Idempotency-Key.
    """

    amount: str = Field(
        ...,
        description="Сумма EFHC строкой с 8 знаками",
    )
    actor: AdminActor

    @field_validator("amount", mode="before")
    def _q8(cls, v: Any) -> str:
        """Нормализация суммы EFHC в формат d8 (ROUND_DOWN)."""
        return cast(str, d8_str(v))


class AdminEmitOut(EfhcBaseModel):
    meta: OkMeta = Field(default_factory=OkMeta)
    emitted: str = Field(
        ...,
        description="Сколько эмитировано (str, 8)",
    )
    bank_balance_after: str = Field(
        ...,
        description="Итоговый баланс Банка (str, 8)",
    )
    note: str | None = Field(
        None,
        description="Примечание (например, 'manual_emission')",
    )


class AdminBurnIn(IdempotencyContract):
    """
    Вход «сжигания» EFHC из Банка (уменьшает баланс банка).
    Денежная операция — требует Idempotency-Key.
    """

    amount: str = Field(
        ...,
        description="Сумма EFHC строкой с 8 знаками",
    )
    actor: AdminActor

    @field_validator("amount", mode="before")
    def _q8(cls, v: Any) -> str:
        """Нормализация суммы EFHC в формат d8 (ROUND_DOWN)."""
        return cast(str, d8_str(v))


class AdminBurnOut(EfhcBaseModel):
    meta: OkMeta = Field(default_factory=OkMeta)
    burned: str = Field(..., description="Сколько сожжено (str, 8)")
    bank_balance_after: str = Field(
        ...,
        description="Итоговый баланс Банка (str, 8)",
    )
    note: str | None = Field(
        None,
        description="Примечание (например, 'manual_burn')",
    )


# ====================================================================
# Блок: «Насильные» операции Банк ↔ Пользователь (через банк-сервис)
# --------------------------------------------------------------------


class AdminForceDebitUserToBankIn(IdempotencyContract):
    """
    Принудительное списание EFHC с пользователя в пользу Банка.
    • Пользователь НЕ может уйти в минус — операция должна быть
      отклонена сервисом.
    • Списание: сначала bonus, затем main (реализует сервис).
    """

    global_id: ApiExternalGlobalId = Field(
        ...,
        description="Канонический global_id пользователя.",
    )
    amount: str = Field(
        ...,
        description="Сумма EFHC строкой с 8 знаками",
    )
    reason: str = Field(
        ...,
        description="Причина списания (для аудита)",
    )
    actor: AdminActor

    @field_validator("amount", mode="before")
    def _q8(cls, v: Any) -> str:
        """Нормализация суммы EFHC в формат d8 (ROUND_DOWN)."""
        return cast(str, d8_str(v))


class AdminForceDebitUserToBankOut(EfhcBaseModel):
    meta: OkMeta = Field(default_factory=OkMeta)
    debited: str = Field(..., description="Фактически списано (str, 8)")
    user_balances_after: BalancePair = Field(
        ...,
        description="Баланс пользователя после операции",
    )
    bank_balance_after: str = Field(
        ...,
        description="Баланс Банка после операции (str, 8)",
    )
    note: str | None = Field(
        None,
        description="Примечание (например, 'force_debit')",
    )


class AdminForceCreditUserFromBankIn(IdempotencyContract):
    """
    Принудительное начисление EFHC пользователю из Банка.
    • Банк может уйти в минус — это допустимо.
    """

    global_id: ApiExternalGlobalId = Field(
        ...,
        description="Канонический global_id пользователя.",
    )
    amount: str = Field(
        ...,
        description="Сумма EFHC строкой с 8 знаками",
    )
    reason: str = Field(
        ...,
        description="Причина начисления (для аудита)",
    )
    actor: AdminActor

    @field_validator("amount", mode="before")
    def _q8(cls, v: Any) -> str:
        """Нормализация суммы EFHC в формат d8 (ROUND_DOWN)."""
        return cast(str, d8_str(v))


class AdminForceCreditUserFromBankOut(EfhcBaseModel):
    meta: OkMeta = Field(default_factory=OkMeta)
    credited: str = Field(
        ...,
        description="Фактически начислено (str, 8)",
    )
    user_balances_after: BalancePair = Field(
        ...,
        description="Баланс пользователя после операции",
    )
    bank_balance_after: str = Field(
        ...,
        description="Баланс Банка после операции (str, 8)",
    )
    note: str | None = Field(
        None,
        description="Примечание (например, 'force_credit')",
    )


# ====================================================================
# Блок: Реконсиляция TON-входящих (по диапазону)
# --------------------------------------------------------------------


class AdminTonReconcileIn(EfhcBaseModel):
    """
    Параметры реконсиляции входящих TON-транзакций.

    • Можно указать диапазон по unixtime (utime_from/utime_to) и лимит.
    • dry_run=True — только анализ (без движений денег).
    """

    utime_from: int | None = Field(
        None,
        description="С какого unixtime включительно",
    )
    utime_to: int | None = Field(
        None,
        description="По какой unixtime включительно",
    )
    limit: int = Field(
        1000,
        gt=0,
        le=10000,
        description="Максимум событий за прогон",
    )
    dry_run: bool = Field(
        True,
        description="Только анализ без записей/движений",
    )
    actor: AdminActor


class AdminTonReconcileOut(EfhcBaseModel):
    meta: OkMeta = Field(default_factory=OkMeta)
    scanned: int = Field(..., description="Сколько событий просмотрено")
    created_orders: int = Field(
        ...,
        description="Сколько создано/помечено заказов (Shop)",
    )
    credited_users: int = Field(
        ...,
        description="Сколько пользователей получило EFHC",
    )
    duplicates_skipped: int = Field(
        ...,
        description="Сколько дублей пропущено по tx_hash",
    )
    errors: int = Field(..., description="Сколько ошибок за прогон")
    last_seen_utime: int | None = Field(
        None,
        description="Последний utime в прогоне",
    )
    note: str | None = Field(
        None,
        description="Примечание (например, 'dry_run')",
    )


# ====================================================================
# Блок: Отчётность/наблюдаемость
# --------------------------------------------------------------------


class AdminReportsQueryIn(EfhcBaseModel):
    """
    Запрос агрегированной статистики для админ - панели.
    """

    period_from: datetime | None = Field(
        None,
        description="Начало периода (UTC)",
    )
    period_to: datetime | None = Field(
        None,
        description="Конец периода (UTC)",
    )
    include_latency: bool = Field(
        True,
        description="Собирать ли лаги догонов/вотчера",
    )
    include_deficit: bool = Field(
        True,
        description="Считать долю операций в дефиците банка",
    )


class AdminReportsOut(EfhcBaseModel):
    meta: OkMeta = Field(default_factory=OkMeta)

    # Денежные агрегаты
    efhc_emitted_total: str = Field(
        ...,
        description="Эмиссия EFHC за период (str, 8)",
    )
    efhc_burned_total: str = Field(
        ...,
        description="Сжигание EFHC за период (str, 8)",
    )
    ton_incoming_count: int = Field(
        ...,
        description="Количество входящих TON (логов)",
    )
    efhc_credited_users: int = Field(
        ...,
        description="Сколько пользователей получили EFHC",
    )
    bank_balance_now: str = Field(
        ...,
        description="Текущий баланс Банка (str, 8)",
    )

    # Качество обработки / устойчивость
    retries_total: int = Field(
        ...,
        description="Всего ретраев (вотчер/планировщик)",
    )
    processed_with_deficit_ratio: str = Field(
        ...,
        description=("Доля операций при дефиците (строкой, 8 знаков)"),
    )
    avg_backfill_lag_sec: int | None = Field(
        None,
        description="Средний лаг догонов энергии (сек)",
    )
    last_scheduler_fail_streak: int = Field(
        ...,
        description=(
            "Текущая длина серии неудач задач (макс. по задачам)"
        ),
    )


# ====================================================================
# Блок: Управление Shop (витрина и позиции)
# --------------------------------------------------------------------
ShopItemType = Literal["EFHC_PACKAGE", "NFT_VIP", "GOOD"]


class AdminShopItemUpsertIn(EfhcBaseModel):
    """
    Создание/обновление позиции в магазине.
    • EFHC_PACKAGE — упаковка EFHC
      (автодоставка по оплате TON через вотчер).
    • NFT_VIP — только заявка; выдача вручную
      (APPROVE/REJECT в админке).
    • GOOD — прочие виртуальные товары
      (начисление EFHC/бонусов по правилам сервиса).
    """

    item_id: ApiLifetimeId | None = Field(
        None,
        description="ID позиции (None — создать)",
    )
    item_type: ShopItemType = Field(..., description="Тип позиции")
    title: str = Field(
        ...,
        max_length=120,
        description="Название витринное",
    )
    description: str | None = Field(
        None,
        max_length=1000,
        description="Описание товара",
    )
    price_ton: str | None = Field(
        None,
        description="Цена в TON (строкой, если применимо)",
    )
    efhc_quantity: str | None = Field(
        None,
        description="Сколько EFHC выдаём (для EFHC_PACKAGE)",
    )
    is_active: bool = Field(
        True,
        description="Показывать ли позицию в витрине",
    )

    @field_validator("price_ton", "efhc_quantity", mode="before")
    def _q8(cls, v: Any) -> str | None:
        """Нормализация суммы EFHC в формат d8 (ROUND_DOWN)."""
        if v is None:
            return None
        return cast(str, d8_str(v))


class AdminShopItemOut(EfhcBaseModel):
    item_id: ApiLifetimeId
    item_type: ShopItemType
    title: str
    description: str | None
    price_ton: str | None
    efhc_quantity: str | None
    is_active: bool
    meta: OkMeta = Field(default_factory=OkMeta)


# ====================================================================
# Блок: Управление Заданиями (Tasks) — рекламные активности
# --------------------------------------------------------------------
TaskType = Literal["JOIN_CHANNEL", "WATCH_AD", "CUSTOM"]


class AdminTaskUpsertIn(EfhcBaseModel):
    """
    Создание/обновление задания.

    • JOIN_CHANNEL — проверка подписки на канал/чат.
    • WATCH_AD — просмотр рекламы (через провайдер/валидатор).
    • CUSTOM — произвольная проверка.

    Вознаграждение — БОНУС-EFHC (тратится первым и невыплатно).
    """

    task_id: ApiLifetimeId | None = Field(
        None,
        description="ID задания (None — создать)",
    )
    task_type: TaskType = Field(..., description="Тип задания")
    title: str = Field(..., max_length=140, description="Заголовок")
    description: str | None = Field(
        None,
        max_length=2000,
        description="Описание",
    )
    bonus_efhc: str = Field(
        ...,
        serialization_alias="bonus_efhc",
        description=(
            "Вознаграждение бонусами EFHC (строкой, 8 знаков)"
        ),
    )

    # Поля для JOIN_CHANNEL
    channel_username: str | None = Field(
        None,
        description="@username канала/чата (для JOIN_CHANNEL)",
    )

    # Поля для WATCH_AD
    ad_url: str | None = Field(
        None,
        description="URL рекламы/ролика (для WATCH_AD)",
    )
    min_watch_seconds: int | None = Field(
        None,
        ge=0,
        le=3600,
        description="Минимум секунд просмотра",
    )

    # Общие флаги
    is_active: bool = Field(
        True,
        description="Доступность задания в витрине",
    )
    daily_cap: int | None = Field(
        None,
        ge=1,
        le=100000,
        description="Дневной лимит завершений",
    )

    @field_validator("bonus_efhc", mode="before")
    def _q8(cls, v: Any) -> str:
        """Нормализация суммы EFHC в формат d8 (ROUND_DOWN)."""
        return cast(str, d8_str(v))


class AdminTaskOut(EfhcBaseModel):
    task_id: ApiLifetimeId
    task_type: TaskType
    title: str
    description: str | None
    bonus_efhc: str
    channel_username: str | None
    ad_url: str | None
    min_watch_seconds: int | None
    is_active: bool
    daily_cap: int | None
    meta: OkMeta = Field(default_factory=OkMeta)


# ====================================================================
# Блок: Модерация заявок (Withdraw EFHC, NFT-requests)
# --------------------------------------------------------------------
ModerationAction = Literal["APPROVE", "REJECT"]


class AdminWithdrawModerateIn(IdempotencyContract):
    """
    Модерация заявки на вывод EFHC (денежная операция внутри контура):
    • APPROVE — списать EFHC у пользователя в пользу Банка,
      пометить заявку одобренной.
    • REJECT — отклонить (балансы не трогаем).
    """

    request_id: ApiLifetimeId = Field(..., description="ID заявки на вывод")
    action: ModerationAction
    admin_note: str | None = Field(
        None,
        description="Причина/комментарий",
    )
    actor: AdminActor


class AdminWithdrawModerateOut(EfhcBaseModel):
    meta: OkMeta = Field(default_factory=OkMeta)
    request_id: ApiLifetimeId
    action: ModerationAction
    global_id: ApiExternalGlobalId
    new_status: Literal["APPROVED", "REJECTED"] = Field(
        ...,
        description="Итоговый статус заявки",
    )
    user_balances_after: BalancePair | None = Field(
        None,
        description=(
            "Баланс пользователя после APPROVE (для REJECT — None)"
        ),
    )
    bank_balance_after: str | None = Field(
        None,
        description="Баланс Банка после APPROVE (str, 8)",
    )
    note: str | None = Field(None, description="Примечание")


class AdminNftRequestModerateIn(IdempotencyContract):
    """
    Модерация заявки на NFT (из Shop):
    • APPROVE — факт ручной выдачи NFT выполнен (вне системы),
      ставим статус APPROVED.
    • REJECT — отклонить (деньги не возвращаем автоматически;
      политика — на стороне админа).
    """

    request_id: ApiLifetimeId = Field(..., description="ID заявки на NFT")
    action: ModerationAction
    admin_note: str | None = Field(
        None,
        description="Причина/комментарий",
    )
    actor: AdminActor


class AdminNftRequestModerateOut(EfhcBaseModel):
    meta: OkMeta = Field(default_factory=OkMeta)
    request_id: ApiLifetimeId
    action: ModerationAction
    new_status: Literal["APPROVED", "REJECTED"]
    note: str | None = Field(None)


# ====================================================================
# Блок: Курсорные страницы административных списков (примеры)
# --------------------------------------------------------------------


class TonInboxLogRow(EfhcBaseModel):
    """Строка журнала входящих TON (свёрнутая форма для админ-вью)."""

    id: ApiLifetimeId
    tx_hash: str
    from_address: str
    to_address: str
    amount: str
    memo: str | None
    status: str
    retries_count: int
    next_retry_at: datetime | None
    created_at: datetime

    @field_validator("amount", mode="before")
    def _q8(cls, v: Any) -> str:
        """Нормализация суммы EFHC в формат d8 (ROUND_DOWN)."""
        return cast(str, d8_str(v))


TonInboxPage = CursorPage[TonInboxLogRow]


class WithdrawRow(EfhcBaseModel):
    """Строка заявок на вывод EFHC (для админ - таблиц)."""

    id: ApiLifetimeId
    global_id: ApiExternalGlobalId
    amount: str
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    created_at: datetime
    updated_at: datetime | None

    @field_validator("amount", mode="before")
    def _q8(cls, v: Any) -> str:
        """Нормализация суммы EFHC в формат d8 (ROUND_DOWN)."""
        return cast(str, d8_str(v))


WithdrawPage = CursorPage[WithdrawRow]


# ====================================================================
# Пояснения:
# • Все суммы — только строки с 8 знаками (d8_str). Так фронтенд
# получает
# стабильный формат без рассинхрона.
# • Любое «денежное» действие в админке должно требовать Idempotency-Key
# (в роутере будет верификация заголовка).
# • Прямых правок балансов нет: любые изменения проходят
# через bank-сервис
# (credit/debit, бонус-логика и т.д.), что обеспечивает аудит
# и зеркальные
# логи.
# • Реконсиляция TON имеет dry_run, лимиты и аккуратный протокол —
# это помогает
# самовосстановлению и защищает от перегрузок.
# • DTO для Shop/Tasks — это форма данных; бизнес-правила
# применяются в соответствующих сервисах
# (shop_service, tasks_service и др.).
# ====================================================================
