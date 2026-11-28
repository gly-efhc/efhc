# backend/app/schemas/facade.py
# ================================================================
# EFHC Bot — Public Schemas Facade
# ---------------------------------------------------------------
# Цель: короткие и стабильные импорты без агрегации в init.py.
# Канон d8: наружу Decimal сериализуется только как string d8.
# ================================================================

from __future__ import annotations

from app.schemas.common_schemas import EfhcBaseModel, d8_str

__all__ = [
    "EfhcBaseModel",
    "d8_str",
]
