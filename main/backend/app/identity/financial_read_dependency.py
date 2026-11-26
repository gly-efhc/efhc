"""FastAPI dependency для provider-neutral financial reads."""

from __future__ import annotations

from typing import Annotated

from app.deps import get_db
from app.identity.auth_context import AuthContext
from app.identity.auth_dependencies import require_auth_context
from app.identity.financial_owner import (
    FinancialReadOwner,
    FinancialReadOwnerError,
    resolve_financial_read_owner,
)
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession


async def get_financial_read_owner(
    db: Annotated[AsyncSession, Depends(get_db)],
    context: Annotated[
        AuthContext,
        Depends(require_auth_context),
    ],
) -> FinancialReadOwner:
    """Разрешить financial owner только из Bearer GlobalId."""

    try:
        return await resolve_financial_read_owner(
            db,
            global_id=context.global_id.value,
        )
    except FinancialReadOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Financial owner mapping не готов",
        ) from exc


__all__ = ["get_financial_read_owner"]
