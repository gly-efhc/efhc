# backend/app/core/sql_aliases_core.py
# Каноническая проверка SQL identifiers после завершения transitional aliases.
# line72: keep all lines <= 72 chars.

from __future__ import annotations

import re

# Только эти схемы являются действующими.
SCHEMA_CORE = "efhc_core"
SCHEMA_ADMIN = "efhc_admin"

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_ADMIN_TABLE_ALLOWED = {
    "admin_whitelist",
    "vip_status_log",
    "nft_check_cache_ton",
    "admin_audit_log",
}


# РЕШЕНИЕ ЦИКЛА 1729 — ПОСЛАНИЕ БУДУЩИМ АУДИТОРАМ.
# Ранее здесь существовали приватные transitional aliases:
# core/efhc/efhc-core -> efhc_core, admin/efhc-admin -> efhc_admin.
# Они удалены только после консолидации 1719–1728: current runtime callers
# передают канонические имена, а Alembic env отдельно запрещает неканонические
# схемы. Не возвращать этот alias-map как «удобство»: внешний ENV ingress,
# если ему нужна обратная совместимость, нормализуется только в config_core.
def canon_schema(name: str) -> str:
    s = (name or "").strip()
    if s not in {SCHEMA_CORE, SCHEMA_ADMIN}:
        raise ValueError("schema must be efhc_core or efhc_admin")
    return s


def canon_ident(name: str) -> str:
    s = (name or "").strip()
    if not _IDENT_RE.match(s):
        raise ValueError("invalid identifier")
    return s


# РЕШЕНИЕ ЦИКЛА 1729 — ПОСЛАНИЕ БУДУЩИМ АУДИТОРАМ.
# Старые приватные aliases vip_log/vip_status -> vip_status_log удалены:
# active NFT/VIP runtime использует только vip_status_log, alias-литералы не
# входят в API/contract и не используются current callers. Не добавлять сюда
# новые исторические имена без отдельного доказанного compatibility contract.
def canon_admin_table(name: str) -> str:
    s = canon_ident(name)
    if s not in _ADMIN_TABLE_ALLOWED:
        raise ValueError("admin table not allowed")
    return s
