# backend/app/services/facade.py
# ===================================================================
# EFHC Bot — Public Services Facade
# -------------------------------------------------------------------
# Цель: короткие и стабильные импорты без магии в init.py.
# ВАЖНО: фасад не должен тянуть весь проект и не должен иметь
# побочных эффектов на import-time.
# ===================================================================

from __future__ import annotations

# Публичные доменные ошибки (роуты маппят их на HTTP).
from app.services.common_errors import (
    EfhcConflictError,
    EfhcServiceError,
)

# Денежные commit (канон: только через transactions_service).
from app.services.transactions_service import (
    credit_user_bonus_from_bank,
    credit_user_from_bank,
    debit_user_bonus_to_bank,
    debit_user_to_bank,
    exchange_kwh_to_efhc,
)

# Денежные операции бизнес-уровня.
from app.services.withdraw_service import approve_withdraw_request

__all__ = [
    "EfhcConflictError",
    "EfhcServiceError",
    "approve_withdraw_request",
    "credit_user_from_bank",
    "credit_user_bonus_from_bank",
    "debit_user_to_bank",
    "debit_user_bonus_to_bank",
    "exchange_kwh_to_efhc",
]
