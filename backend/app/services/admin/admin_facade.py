# backend/app/services/admin/admin_facade.py
# ======================================================================
# EFHC Bot — AdminService (фасад админ-подсистемы)
# ----------------------------------------------------------------------
# Назначение:
# • Дать ЕДИНЫЙ высокий уровень API для админ-роутов и фоновых воркеров.
# • Инкапсулировать всю внутреннюю модульную структуру admin-модуля.
# • Дополнительно защищать канон проекта на уровне публичного
# интерфейса:
# - НЕТ P2P переводов «пользователь ↔ пользователь»;
# - ВСЕ бонусы → только бонусный баланс;
# - ВСЕ денежные операции идемпотентны (idempotency_key на нижнем
# уровне);
# - ВСЕ транзакции только «Банк ↔ Пользователь».
#
# ВНИМАНИЕ (жёсткий канон):
# 1) Начальный баланс банка: 5 000 000 EFHC. Любые корректировки только
# через банк-сервис (минт/бёрн/ручные транзакции «банк ↔ пользователь»).
# 2) Внутренние переводы между пользователями (user → user) ЗАПРЕЩЕНЫ.
# В этом фасаде нет и не будет методов, которые позволяли бы делать P2P.
# 3) Все бонусные начисления (реферальные, задания и др.) идут
# только
# на бонусный счет. Фасад не даёт доступ к «бонус→regular» конверсиям.
# 4) Все операции, двигающие EFHC (включая ручные действия админа),
# обязаны
# использовать идемпотентные сервисы нижнего уровня с явным ключом.
#
# Как использовать:
# from app.services.admin.admin_facade import AdminService
#
# admin = await AdminService.resolve_admin(db, global_id)
# stats = await AdminService.get_system_stats(db)
# ======================================================================

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

# Банк EFHC
from app.services.admin.admin_bank_service import (
    BankBalance,
    BankService,
    BankUserTransferRequest,
    MintBurnRequest,
)
from app.services.admin.admin_logging import (
    AdminLog,
    AdminLogger,
    Pagination,
)
from app.services.admin.admin_notifications import (
    AdminNotification,
)

# Панели пользователей
from app.services.admin.admin_panels_service import (
    AdminPanelsService,
    PanelToggleRequest,
)

# RBAC / логи / настройки / нотификации
from app.services.admin.admin_rbac import (
    RBAC,
    AdminAuthError,
    AdminRole,
    AdminUser,
)
from app.services.admin.admin_settings import (
    ALLOWED_SETTINGS,
    SettingsService,
    SystemSetting,
)

# Статистика
from app.services.admin.admin_stats_service import (
    AdminStatsService,
    CoinsStats,
    PanelsStats,
    ReferralsStats,
    ShopStats,
    SystemStats,
)

# Пользователи / прогресс / отладка
from app.services.admin.admin_users_service import (
    AdminUsersService,
    UserProgressSnapshot,
)

# Вывод EFHC / бонус-на-вывод
from app.services.admin.admin_withdrawals_service import (
    BonusAwardFilters,
    WithdrawalApproveRequest,
    WithdrawalFilters,
    WithdrawalRecord,
    WithdrawalsService,
)
from sqlalchemy.ext.asyncio import AsyncSession


class AdminService:
    """
    Высокоуровневый фасад над всеми админ-подсистемами.

    ВАЖНО:
      • Здесь НЕТ бизнес-логики по деньгам — только делегация.
      • Канон безопасности обеспечивается тем, ЧТО именно мы
      экспортируем:
          - нет методов P2P-переводов;
          - нет методов «прямого» изменения user.balance в обход банка;
          - нет обратных обменов EFHC↔kWh.
    """

    # ------------------------------------------------------------------
    # --- #
    # 0. RBAC / Аутентификация админа
    # #
    # ------------------------------------------------------------------
    # --- #

    @staticmethod
    async def resolve_admin(
        db: AsyncSession,
        global_id: int,
    ) -> AdminUser:
        """Разрешить администратора по canonical ``global_id``."""
        return await RBAC.resolve_admin(db, global_id=global_id)

    @staticmethod
    def require_role(admin: AdminUser, minimal: str) -> None:
        """
        Проверка, что роль admin «не ниже», чем требуемая minimal.
        """
        RBAC.require_role(admin, minimal)

    # ------------------------------------------------------------------
    # --- #
    # 1. ЛОГИ АДМИНОВ
    # #
    # ------------------------------------------------------------------
    # --- #

    @staticmethod
    async def list_admin_logs(
        db: AsyncSession,
        pg: Pagination,
        actor_global_id: int | None = None,
        admin_id: int | None = None,
        action: str | None = None,
        entity: str | None = None,
    ) -> Any:
        """
        Возвращает список логов действий админов (для аудита).
        """
        return await AdminLogger.list(
            db,
            pg=pg,
            actor_global_id=actor_global_id,
            admin_id=admin_id,
            action=action,
            entity=entity,
        )

    # ------------------------------------------------------------------
    # --- #
    # 2. СИСТЕМНЫЕ НАСТРОЙКИ АДМИНКИ (+ ежедневные снапшоты / откат)
    # #
    # ------------------------------------------------------------------
    # --- #

    @staticmethod
    async def get_setting(
        db: AsyncSession,
        key: str,
    ) -> SystemSetting | None:
        """Прочитать одну настройку (или None, если не существует)."""
        return await SettingsService.get(db, key)

    @staticmethod
    async def mget_settings(
        db: AsyncSession,
        keys: list[str],
    ) -> Any:
        """Пакетное чтение нескольких настроек."""
        return await SettingsService.mget(db, keys)

    @staticmethod
    async def set_setting(
        db: AsyncSession,
        key: str,
        value: str,
        admin: AdminUser,
    ) -> None:
        """
        Установить/обновить одну настройку.

        ИИ-страховка:
          • key проверяется на принадлежность ALLOWED_SETTINGS.
          • Значения проходят валидацию (числа/пороги/строки).
        """
        await SettingsService.set(
            db,
            key,
            value,
            actor_global_id=admin.global_id,
            admin_id=admin.id,
        )
        return None

    @staticmethod
    async def mset_settings(
        db: AsyncSession,
        items: dict[str, str],
        admin: AdminUser,
    ) -> None:
        """
        Пакетное обновление настроек (каждая — через set_setting).
        """
        await SettingsService.mset(
            db,
            items,
            actor_global_id=admin.global_id,
            admin_id=admin.id,
        )
        return None

    @staticmethod
    async def snapshot_settings_daily(db: AsyncSession) -> None:
        """
        Сохранение слепка настроек (для отката). Вызывается
        планировщиком раз в сутки.
        """
        await SettingsService.snapshot_all(db)

    @staticmethod
    async def restore_settings_from_snapshot(
        db: AsyncSession,
        snapshot_id: int,
        admin: AdminUser,
    ) -> None:
        """
        Откат настроек к выбранному снапшоту (ИИ-защита от ошибочных
        изменений).
        """
        RBAC.require_role(admin, AdminRole.SUPERADMIN)
        await SettingsService.restore_from_snapshot(
            db,
            snapshot_id=snapshot_id,
            actor_global_id=admin.global_id,
            admin_id=admin.id,
        )

    # ------------------------------------------------------------------
    # --- #
    # 3. БАНК EFHC: минт/бёрн/ручные транзакции Банк↔Пользователь
    # #
    # ------------------------------------------------------------------
    # --- #

    @staticmethod
    async def get_bank_balance(db: AsyncSession) -> BankBalance:
        """
        Возвращает агрегированный баланс банка EFHC (для дашборда).
        """
        return await BankService.get_bank_balance(db)

    @staticmethod
    async def mint_efhc(
        db: AsyncSession,
        req: MintBurnRequest,
        admin: AdminUser,
    ) -> Any:
        """
        Минт EFHC в банк. НЕ начисляет пользователям напрямую.
        """
        return await BankService.mint_efhc(
            db,
            req=req,
            admin=admin,
        )

    @staticmethod
    async def burn_efhc(
        db: AsyncSession,
        req: MintBurnRequest,
        admin: AdminUser,
    ) -> Any:
        """
        Сжигание EFHC из банка (требуется достаточный остаток).
        """
        return await BankService.burn_efhc(
            db,
            req=req,
            admin=admin,
        )

    @staticmethod
    async def manual_bank_user_transfer(
        db: AsyncSession,
        req: BankUserTransferRequest,
        admin: AdminUser,
    ) -> Any:
        """
        Ручная операция Банк↔Пользователь.

        req.direction = credit|debit
          - credit: user credit ⇒ bank debit
          - debit:  user debit  ⇒ bank credit
        """
        return await BankService.manual_bank_user_transfer(
            db,
            req=req,
            admin=admin,
        )

    @staticmethod
    async def rollback_bank_user_tx(
        db: AsyncSession,
        *,
        transfer_log_id: int,
        idempotency_key: str,
        admin: AdminUser,
    ) -> Any:
        """Компенсировать одну исходную Admin Bank operation."""
        return await BankService.rollback_bank_user_tx(
            db,
            transfer_log_id=transfer_log_id,
            idempotency_key=idempotency_key,
            admin=admin,
        )

    # ------------------------------------------------------------------
    # --- #
    # 5. ПАНЕЛИ ПОЛЬЗОВАТЕЛЕЙ
    # #
    # ------------------------------------------------------------------
    # --- #

    @staticmethod
    async def toggle_user_panel(
        db: AsyncSession,
        req: PanelToggleRequest,
        admin: AdminUser,
    ) -> Any:
        """
        Включение/выключение панелей пользователя (ручная
        корректировка).
        """
        return await AdminPanelsService.toggle_panel(
            db,
            req=req,
            admin=admin,
        )

    # ------------------------------------------------------------------
    # --- #
    # 7. КОШЕЛЬКИ ПОЛЬЗОВАТЕЛЕЙ
    # #
    # ------------------------------------------------------------------
    # --- #

    # PACK-02 tail cleanup:
    # legacy admin crypto-wallet facade methods were removed from
    # active runtime. Wallet ownership is managed only by
    # app.services.wallets_service through TonConnect proof,
    # wallet_bindings, replay protection and idempotency.

    # ------------------------------------------------------------------
    # --- #
    # 8. СТАТИСТИКА ДЛЯ ДАШБОРДА
    # #
    # ------------------------------------------------------------------
    # --- #

    @staticmethod
    async def get_coins_stats(db: AsyncSession) -> CoinsStats:
        """Метод класса AdminService.
        Асинхронная функция `get_coins_stats` выполняет операцию в
        контуре бота EFHC.
        Назначение: получить/прочитать данные и вернуть результат без
        побочных эффектов (кроме логирования).

        Параметры:
        - `db` (AsyncSession): входной параметр.

        Возвращает:
        - Значение типа/структуры: CoinsStats.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service)."""
        return await AdminStatsService.get_coins_stats(db)

    @staticmethod
    async def get_panels_stats(db: AsyncSession) -> PanelsStats:
        """Метод класса AdminService.
        Асинхронная функция `get_panels_stats` выполняет операцию в
        контуре бота EFHC.
        Назначение: получить/прочитать данные и вернуть результат без
        побочных эффектов (кроме логирования).

        Параметры:
        - `db` (AsyncSession): входной параметр.

        Возвращает:
        - Значение типа/структуры: PanelsStats.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service)."""
        return await AdminStatsService.get_panels_stats(db)

    @staticmethod
    async def get_referrals_stats(db: AsyncSession) -> ReferralsStats:
        """Метод класса AdminService.
        Асинхронная функция `get_referrals_stats` выполняет операцию в
        контуре бота EFHC.
        Назначение: получить/прочитать данные и вернуть результат без
        побочных эффектов (кроме логирования).

        Параметры:
        - `db` (AsyncSession): входной параметр.

        Возвращает:
        - Значение типа/структуры: ReferralsStats.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service)."""
        return await AdminStatsService.get_referrals_stats(db)

    @staticmethod
    async def get_shop_stats(db: AsyncSession) -> ShopStats:
        """Метод класса AdminService.
        Асинхронная функция `get_shop_stats` выполняет
        операцию в commerce-domain Shop, а не в
        Hub links manager, в контуре бота EFHC.
        Назначение: получить/прочитать данные и вернуть результат без
        побочных эффектов (кроме логирования).

        Параметры:
        - `db` (AsyncSession): входной параметр.

        Возвращает:
        - Значение типа/структуры: ShopStats.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service)."""
        return await AdminStatsService.get_shop_stats(db)

    @staticmethod
    async def get_system_stats(db: AsyncSession) -> SystemStats:
        """Метод класса AdminService.
        Асинхронная функция `get_system_stats` выполняет операцию в
        контуре бота EFHC.
        Назначение: получить/прочитать данные и вернуть результат без
        побочных эффектов (кроме логирования).

        Параметры:
        - `db` (AsyncSession): входной параметр.

        Возвращает:
        - Значение типа/структуры: SystemStats.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service)."""
        return await AdminStatsService.get_system_stats(db)

    # ------------------------------------------------------------------
    # --- #
    # 9. ПОЛЬЗОВАТЕЛИ / БАЛАНСЫ / ПРОГРЕСС / ОТЛАДКА
    # #
    # ------------------------------------------------------------------
    # --- #

    @staticmethod
    async def get_user_balances(
        db: AsyncSession,
        global_id: int,
    ) -> Any:
        """Вернуть балансы аккаунта по canonical owner."""
        return await AdminUsersService.get_user_snapshot(
            db,
            global_id=global_id,
        )

    @staticmethod
    async def debug_user_progress(
        db: AsyncSession,
        global_id: int,
    ) -> UserProgressSnapshot:
        """Вернуть административный снимок прогресса аккаунта."""
        return await AdminUsersService.get_user_progress(
            db,
            global_id=global_id,
        )

    @staticmethod
    async def credit_bonus_efhc(
        db: AsyncSession,
        global_id: int,
        amount: Decimal,
        *,
        reason: str = "ADMIN",
        idempotency_key: str,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """Compatibility entrypoint: делегирует бонусное начисление в единый BankService.

        Сохранён для старых callers. Новый Admin UI использует только
        ``POST /admin/transfer`` и не создаёт параллельную денежную логику.
        """
        return cast(
            dict[str, Any],
            await AdminUsersService.credit_bonus_efhc(
                db,
                global_id=global_id,
                amount=amount,
                reason=reason,
                idempotency_key=idempotency_key,
                admin=admin,
            ),
        )

    @staticmethod
    async def credit_regular_efhc(
        db: AsyncSession,
        global_id: int,
        amount: Decimal,
        *,
        reason: str = "ADMIN",
        idempotency_key: str,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """Compatibility entrypoint: делегирует основное начисление в единый BankService.

        Сохранён для старых callers. Новый Admin UI использует только
        ``POST /admin/transfer`` и не создаёт параллельную денежную логику.
        """
        return cast(
            dict[str, Any],
            await AdminUsersService.credit_regular_efhc(
                db,
                global_id=global_id,
                amount=amount,
                reason=reason,
                idempotency_key=idempotency_key,
                admin=admin,
            ),
        )

    # ------------------------------------------------------------------
    # --- #
    # 10. ЗАЯВКИ НА ВЫВОД EFHC / БОНУСЫ НА ВЫВОД / NFT ПО ЗАЯВКАМ
    # #
    # ------------------------------------------------------------------
    # --- #

    @staticmethod
    async def list_withdraw_requests(
        db: AsyncSession,
        filters: WithdrawalFilters,
    ) -> Any:
        """
        Список заявок на вывод EFHC (для обработки админами).
        """
        return await WithdrawalsService.list_withdrawals(
            db,
            filters=filters,
        )

    @staticmethod
    async def admin_approve_withdraw(
        db: AsyncSession,
        withdrawal_id: int,
        req: WithdrawalApproveRequest,
        admin: AdminUser,
    ) -> Any:
        """
        Админ утвердил вывод через актуальный withdrawals service.

        Внутренний facade делегирует в canonical withdrawals service
        и не содержит собственной money-логики.
        """
        return await WithdrawalsService.approve_withdrawal(
            db,
            withdrawal_id=withdrawal_id,
            req=req,
            admin=admin,
        )

    @staticmethod
    async def admin_reject_withdraw(
        db: AsyncSession,
        withdrawal_id: int,
        admin: AdminUser,
        reason: str,
        *,
        idempotency_key: str,
        comment_override: str | None = None,
        comment_auto_translated: bool = False,
    ) -> Any:
        """
        Админ отклонил вывод через актуальный withdrawals service.

        Idempotency key обязателен, потому что reject выполняет refund
        по каноническому withdraw-flow.
        """
        return await WithdrawalsService.reject_withdrawal(
            db,
            withdrawal_id=withdrawal_id,
            reason=reason,
            idempotency_key=idempotency_key,
            admin=admin,
            comment_override=comment_override,
            comment_auto_translated=comment_auto_translated,
        )



    @staticmethod
    async def admin_mark_withdraw_paid(
        db: AsyncSession,
        request_id: int,
        admin: AdminUser,
        *,
        payout_ref: str | None = None,
    ) -> Any:
        """Compatibility entrypoint, заменён каноническим подтверждением вывода.

        Почему сохранён: старые callers могут ссылаться на имя метода, поэтому
        fail-closed policy запрещает удалять его без отдельного доказательства.
        Почему не используется новым UI: финальное состояние выплаты должен
        устанавливать ``approve_withdrawal()``, где сохранены действующие
        проверки, идемпотентность и финансовая семантика.
        """
        _ = db
        _ = request_id
        _ = admin
        _ = payout_ref
        raise ValueError("Функция заменена: используйте approve_withdrawal")

    @staticmethod
    async def list_bonus_payouts(
        db: AsyncSession,
        filters: BonusAwardFilters,
    ) -> Any:
        """Legacy compatibility entrypoint старого ``bonus_awards`` контура.

        Новый Admin UI не использует этот метод: активная история бонусов
        собирается из заданий, рефералов и банковского ledger. Имя сохранено
        только для совместимости и не является основанием возвращать dead table.
        """
        return await WithdrawalsService.list_bonus_awards(
            db,
            filters=filters,
        )


# ======================================================================
# Публичный API модуля
# #
# ======================================================================

__all__ = [
    "AdminService",
    # Базовые сущности для удобства использования в роутерах:
    "AdminUser",
    "AdminRole",
    "AdminAuthError",
    "AdminLog",
    "Pagination",
    "SystemSetting",
    "ALLOWED_SETTINGS",
    "AdminNotification",
    "PanelToggleRequest",
    "MintBurnRequest",
    "BankUserTransferRequest",
    "BankBalance",
    "CoinsStats",
    "PanelsStats",
    "ReferralsStats",
    "ShopStats",
    "SystemStats",
    "UserProgressSnapshot",
    "WithdrawalRecord",
    "WithdrawalFilters",
    "BonusAwardFilters",
]
