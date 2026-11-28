"""Reserved EFHC Global IDs; never issued by ordinary account registration.

OWNER release canon: public SuperAdmin is 0000000088. Public Global ID is
an account reference, NEVER proof of identity or authorization. Retain the
legacy 1313131313 allocation reservation for existing database constraints.
"""
from __future__ import annotations

from typing import Final

SUPERADMIN_GLOBAL_ID_TEXT: Final[str] = "0000000088"
SUPERADMIN_GLOBAL_ID_DB: Final[int] = 88
LEGACY_SUPERADMIN_RESERVED_GLOBAL_ID_DB: Final[int] = 1_313_131_313
RESERVED_GLOBAL_ID_DB_VALUES: Final[frozenset[int]] = frozenset(
    {SUPERADMIN_GLOBAL_ID_DB, LEGACY_SUPERADMIN_RESERVED_GLOBAL_ID_DB}
)


def is_reserved_global_id_db(value: int) -> bool:
    """Prevent regular account allocation of either owner or legacy ID."""
    return int(value) in RESERVED_GLOBAL_ID_DB_VALUES


__all__ = [
    "RESERVED_GLOBAL_ID_DB_VALUES",
    "SUPERADMIN_GLOBAL_ID_DB",
    "SUPERADMIN_GLOBAL_ID_TEXT",
    "LEGACY_SUPERADMIN_RESERVED_GLOBAL_ID_DB",
    "is_reserved_global_id_db",
]
