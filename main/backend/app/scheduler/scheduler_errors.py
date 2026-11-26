"""Бессрочные compatibility-типы исключений старого scheduler API.

Решение цикла 1728: ``SchedulerError`` и ``JobTimeout`` сохраняют старые
import/type contracts, но НЕ определяют нынешнюю error-policy SchedulerService.
Новый код не должен создавать параллельную систему обработки ошибок только
потому, что эти классы существуют. Не создавать параллельную error-policy.

ПОСЛАНИЕ БУДУЩИМ АУДИТОРАМ: отсутствие current raise/catch не является
delete-proof. Эти имена намеренно остаются совместимыми до отдельного решения
пользователя после проверки всех внешних/исторических потребителей.
"""


class SchedulerError(Exception):
    """Базовый historical compatibility-тип ошибки планировщика."""


class JobTimeout(SchedulerError):
    """Historical compatibility-тип превышения времени задачи."""


__all__ = ["JobTimeout", "SchedulerError"]
