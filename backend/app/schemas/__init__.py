"""EFHC Pydantic schemas package.

Канон:
- Схемы импортируются *явно* из конкретных модулей, например:
  from app.schemas.exchange_schemas import ExchangePreviewOut
- Этот пакет не агрегирует экспорты динамически, чтобы исключить
  конфликты имён и «тихие» переопределения.

Причина:
- Динамическая агрегация импортирует десятки модулей при одном
  `import app.schemas` и может приводить к конфликтам имён и
  нестабильному порядку экспортов.
"""

from __future__ import annotations

SCHEMAS_VERSION: str = "v2.0"

__all__ = [
    "SCHEMAS_VERSION",
]
