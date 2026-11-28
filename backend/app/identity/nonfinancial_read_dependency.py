"""FastAPI dependency для provider-neutral non-financial reads."""

from __future__ import annotations

from typing import Annotated

from app.deps import get_db
from app.identity.auth_context import AuthContext
from app.identity.auth_dependencies import require_auth_context
from app.identity.nonfinancial_owner import (
    NonFinancialReadOwner,
    NonFinancialReadOwnerError,
    resolve_nonfinancial_read_owner,
)
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession


async def get_nonfinancial_read_owner(
    db: Annotated[AsyncSession, Depends(get_db)],
    context: Annotated[
        AuthContext,
        Depends(require_auth_context),
    ],
) -> NonFinancialReadOwner:
    """Разрешить non-financial owner только из Bearer GlobalId."""

    try:
        return await resolve_nonfinancial_read_owner(
            db,
            global_id=context.global_id.value,
        )
    except NonFinancialReadOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Non-financial owner mapping не готов",
        ) from exc


__all__ = ["get_nonfinancial_read_owner"]
