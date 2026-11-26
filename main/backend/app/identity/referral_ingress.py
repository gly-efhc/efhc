"""Provider-neutral transport referral start param цикла 1638.

Модуль отвечает только за безопасную нормализацию входа. Создание
``referral_links`` выполняет ``AccountRegistrationService`` для Bot,
Telegram WebApp и TON callers после миграции цикла 1639.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.identity.account_registration import (
    normalize_referral_start_param,
)


class ReferralIngressError(ValueError):
    """Referral ingress отклонён до account/session side effects."""

    code = "auth.referral_start_invalid"
    message = "Реферальный параметр входа недействителен"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class ReferralIngress:
    """Нормализованный provider-neutral referral transport."""

    normalized_code: str | None
    supplied: bool


def parse_referral_start_param(value: str | None) -> ReferralIngress:
    """Нормализовать вход или отклонить непустой некорректный код."""

    if value is None:
        return ReferralIngress(normalized_code=None, supplied=False)
    raw = str(value).strip()
    if not raw:
        return ReferralIngress(normalized_code=None, supplied=False)
    normalized = normalize_referral_start_param(raw)
    if normalized is None:
        raise ReferralIngressError("invalid_code")
    return ReferralIngress(normalized_code=normalized, supplied=True)


def build_referral_ingress_contract() -> dict[str, object]:
    """Вернуть машинно-проверяемый transport contract цикла 1638."""

    return {
        "цикл": 1638,
        "каналы_входа": ["telegram", "ton", "browser_pwa"],
        "хранилище_фронтенда": "sessionStorage",
        "нормализация_до_сервиса": True,
        "сырой_параметр_не_owner": True,
        "сырой_параметр_не_idempotency": True,
        "поздняя_привязка": False,
        "существующий_account_игнорирует": True,
        "создание_referral_link": "AccountRegistrationService",
        "caller_migration": "bot_webapp_ton",
    }


__all__ = [
    "ReferralIngress",
    "ReferralIngressError",
    "build_referral_ingress_contract",
    "parse_referral_start_param",
]
