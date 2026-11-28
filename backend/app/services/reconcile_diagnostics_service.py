from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def summarize_reconcile_diagnostics(
    db: AsyncSession,
    *,
    hours: int,
) -> dict[str, int]:
    q = text(
        """
        SELECT status, COUNT(*) AS cnt
          FROM efhc_core.ton_inbox_logs
         WHERE created_at >= NOW() - (:hours || ' hours')::interval
         GROUP BY status
        """
    )
    rows = (await db.execute(q, {"hours": int(hours)})).all()
    summary: dict[str, int] = {}
    for status, cnt in rows:
        summary[f"status:{status}"] = int(cnt or 0)

    q2 = text(
        """
        SELECT reason, COUNT(*) AS cnt
          FROM efhc_core.unmatched_incoming
         WHERE created_at >= NOW() - (:hours || ' hours')::interval
         GROUP BY reason
        """
    )
    rows2 = (await db.execute(q2, {"hours": int(hours)})).all()
    for reason, cnt in rows2:
        summary[f"unmatched:{reason}"] = int(cnt or 0)
    return summary
