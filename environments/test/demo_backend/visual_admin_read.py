"""Bounded read-only TEST Admin report exposure for temporary visual sessions.

This is not RBAC, not the SuperAdmin account, and not a release feature.
Only server-held visual-key sessions can reach these explicit aggregate GETs.
There is intentionally no wildcard, dynamic-ID, secrets or mutation route.
"""
from __future__ import annotations

# All listed handlers are aggregate/reporting GET-only, and have been reviewed.
_VISUAL_READ_PATHS = frozenset({
    "/api/admin/reports/overview",
    "/api/admin/reports/users",
    "/api/admin/reports/bank",
    "/api/admin/reports/panels",
    "/api/admin/reports/withdrawals",
    "/api/admin/reports/deposits",
    "/api/admin/bank/balance",
    "/api/admin/referrals/summary",
    "/api/admin/bonuses",
})


def visual_admin_report_allowed(path: str, method: str) -> bool:
    """Fail closed: exact path and safe HTTP method only, no prefix matching."""
    return method.upper() in {"GET", "HEAD"} and path in _VISUAL_READ_PATHS
