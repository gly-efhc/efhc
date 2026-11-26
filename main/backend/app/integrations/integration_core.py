# backend/app/integrations/integration_core.py
# =====================================================================
# EFHC Bot — Integration Core (SSOT helper)
#
# Зачем:
# • Единый слой абстракции/нормализации для внешних интеграций
#   (TON / NFT / Ads провайдеры).
# • Handler'ы и сервисы работают с унифицированными объектами,
#   не завися от формата конкретного API.
#
# Канон:
# • Никаких новых идентификаторов пользователя: только global_id.
# • Никакой бизнес-логики и денег здесь.
# • Никаких секретов в логах/деталях.
# =====================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IntegrationError:
    """Нормализованная ошибка интеграции."""

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class IntegrationResult:
    """Нормализованный результат интеграции."""

    ok: bool
    data: dict[str, Any] | None = None
    error: IntegrationError | None = None
    raw: dict[str, Any] | None = None


def ok_result(
    data: dict[str, Any] | None = None,
    *,
    raw: dict[str, Any] | None = None,
) -> IntegrationResult:
    return IntegrationResult(
        ok=True,
        data=data or {},
        error=None,
        raw=raw,
    )


def error_result(
    *,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
    raw: dict[str, Any] | None = None,
) -> IntegrationResult:
    return IntegrationResult(
        ok=False,
        data=None,
        error=IntegrationError(
            code=code,
            message=message,
            retryable=retryable,
            details=details,
        ),
        raw=raw,
    )
