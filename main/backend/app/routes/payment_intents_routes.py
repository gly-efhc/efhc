# backend/app/routes/payment_intents_routes.py
# ----------------------------------------------------------------------
# Payment intents status (owner-only).
# Используется для UX "ожидание подтверждения".
# ----------------------------------------------------------------------

from __future__ import annotations

from app.deps import get_db
from app.identity.financial_owner import FinancialReadOwner
from app.identity.financial_read_dependency import (
    get_financial_read_owner,
)
from app.identity.types import global_id_from_database
from app.schemas.id_schemas import ApiLifetimeId
from app.schemas.payment_intents_schemas import PaymentIntentStatusOut
from app.services.payment_intents_service import (
    get_intent_status_for_user,
)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/payment-intents", tags=["payment_intents"])


@router.get(
    "/{intent_id}",
    response_model=PaymentIntentStatusOut,
    summary="Get payment intent status (owner-only)",
)
async def get_payment_intent_status(
    intent_id: ApiLifetimeId,
    db: AsyncSession = Depends(get_db),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> PaymentIntentStatusOut:
    row = await get_intent_status_for_user(
        db,
        global_id=str(global_id_from_database(owner.global_id)),
        intent_id=int(intent_id),
    )
    if not row or row.get("ok") is not True:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "E002_NOT_FOUND",
                "message": "Payment intent not found.",
                "details": {
                    "entity": "payment_intent",
                    "key": "intent_id",
                    "value": int(intent_id),
                },
            },
        )
    row.pop("ok", None)
    return PaymentIntentStatusOut(**row)
