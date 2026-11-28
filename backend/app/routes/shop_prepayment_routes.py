"""Local API candidate; deliberately unregistered and disabled by default."""

from __future__ import annotations

from decimal import Decimal
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import get_nonfinancial_read_owner

from ..services.shop_prepayment import Attempt, Checkout, ShopRequest, ShopRequestError


_NO_STORE = {"Cache-Control": "no-store"}


class _NoStoreRoute(APIRoute):
    def get_route_handler(self):
        inner = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                response = await inner(request)
            except RequestValidationError as exc:
                # Default validation includes submitted values. Do not echo keys.
                raise _error(422, "SHOP_REQUEST_INVALID") from exc
            response.headers.update(_NO_STORE)
            return response

        return handle


router = APIRouter(prefix="/shopfront/checkout-requests", route_class=_NoStoreRoute)


class StatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=128)


class RequestInput(StatusInput):
    sku: str
    method: str
    quantity: int = Field(strict=True)
    custom_efhc_amount_d8: Decimal | None = None


class PayInput(RequestInput):
    review_id: str = Field(pattern=r"^[0-9a-f]{64}$")


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail, headers=_NO_STORE)


def get_checkout() -> Checkout:
    # Not an environment toggle: publishing/migration and owner-gate
    # integration must explicitly replace this dependency after verification.
    raise _error(503, "SHOP_PREPAYMENT_UNAVAILABLE")


async def get_trusted_owner(
    handoff: Annotated[str | None, Header(alias="X-EFHC-Handoff")] = None,
) -> str:
    token = (handoff or "").strip()
    if not token:
        raise _error(401, "SHOP_HANDOFF_REQUIRED")

    from app.core.database_core import new_session
    from app.core.security_core import decode_jwt_token
    from app.routes.hub_routes import _resolve_handoff_owner

    try:
        claims = decode_jwt_token(token, expected_audience="efhc_buy_site")
        if claims.get("kind") != "hub_efhc_handoff" or claims.get("aud") != "efhc_buy_site":
            raise _error(401, "SHOP_HANDOFF_INVALID")
        async with new_session() as db:
            return await _resolve_handoff_owner(db, claims)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise _error(401, "SHOP_HANDOFF_INVALID") from exc
        raise


def _request(body: RequestInput) -> ShopRequest:
    return ShopRequest(
        body.key, body.sku, body.method, body.quantity, body.custom_efhc_amount_d8,
    )


def _view(attempt: Attempt | None) -> dict:
    if attempt is None:
        return {"state": "not_seen"}
    out: dict = {"state": attempt.outcome.value}
    if attempt.review is not None:
        out["quote"] = {"asset": attempt.review.asset, "amount": attempt.review.amount}
        out["review_id"] = attempt.review.review_id
    if attempt.references is not None:
        out["order_id"] = attempt.references.order_id
        if attempt.references.intent_id is not None:
            out["intent_id"] = attempt.references.intent_id
    return out


def _domain_error(exc: ShopRequestError) -> HTTPException:
    code = str(exc)
    if code == "SHOP_REQUEST_METHOD_UNAVAILABLE":
        return _error(503, code)
    if code == "SHOP_REQUEST_INVALID":
        return _error(422, code)
    if code in {
        "SHOP_REQUEST_ACTIVE", "SHOP_REQUEST_ALREADY_ISSUED",
        "SHOP_REQUEST_PAYLOAD_MISMATCH", "SHOP_REQUEST_TRANSITION_REFUSED",
        "SHOP_REQUEST_NOT_PREPARED", "SHOP_REQUEST_ITEM_UNAVAILABLE",
        "SHOP_REQUEST_WALLET_REQUIRED", "SHOP_REQUEST_SNAPSHOT_MISMATCH",
        "SHOP_REQUEST_REVIEW_MISMATCH",
    }:
        return _error(409, code)
    return _error(503, "SHOP_PREPAYMENT_UNAVAILABLE")


@router.post("/prepare")
async def prepare(
    body: RequestInput, response: Response,
    checkout: Annotated[Checkout, Depends(get_checkout)],
    owner: Annotated[str, Depends(get_trusted_owner)],
) -> dict:
    response.headers.update(_NO_STORE)
    try:
        return _view(await checkout.prepare(owner, _request(body)))
    except ShopRequestError as exc:
        raise _domain_error(exc) from exc


@router.post("/cancel")
async def cancel(
    body: RequestInput, response: Response,
    checkout: Annotated[Checkout, Depends(get_checkout)],
    owner: Annotated[str, Depends(get_trusted_owner)],
) -> dict:
    response.headers.update(_NO_STORE)
    try:
        return _view(await checkout.cancel(owner, _request(body)))
    except ShopRequestError as exc:
        raise _domain_error(exc) from exc


@router.post("/status")
async def read_status(
    body: StatusInput, response: Response,
    checkout: Annotated[Checkout, Depends(get_checkout)],
    owner: Annotated[str, Depends(get_trusted_owner)],
) -> dict:
    # A committed snapshot of SHOP only. not_seen does not rule out an
    # in-flight writer and is not permission to allocate another request.
    response.headers.update(_NO_STORE)
    try:
        return _view(await checkout.status_by_key(owner, body.key))
    except ShopRequestError as exc:
        raise _domain_error(exc) from exc


def get_external_pay():
    # The actual canonical composition is included for verification, not
    # mounted or enabled in the application in this source candidate.
    raise _error(503, "SHOP_PREPAYMENT_UNAVAILABLE")


def build_staged_external_pay():
    from functools import partial

    from ..services.shop_prepayment_external_pay import CanonicalExternalPay, pay_external
    from ..services.shop_prepayment_store import build_local_store

    return partial(pay_external, store=build_local_store(), ops=CanonicalExternalPay())


@router.post("/pay")
async def pay(
    body: PayInput,
    external_pay: Annotated[Callable[[str, ShopRequest, str], Awaitable[dict]], Depends(get_external_pay)],
    owner: Annotated[str, Depends(get_trusted_owner)],
) -> dict:
    try:
        return await external_pay(owner, _request(body), body.review_id)
    except ShopRequestError as exc:
        raise _domain_error(exc) from exc


def get_balance_pay():
    # Explicitly disabled: candidate router is unregistered.
    raise _error(503, "SHOP_PREPAYMENT_UNAVAILABLE")


def build_staged_balance_pay():
    from app.core.database_core import new_session
    from ..services.shop_prepayment import freeze_review, verify_review
    from ..services.shop_prepared_vip_balance import pay_prepared_vip_balance

    async def run(owner: int, request: ShopRequest, review_id: str) -> dict:
        def require_review(saved: dict, incoming_id: str) -> None:
            verify_review(freeze_review(owner, request, saved), incoming_id)

        async with new_session() as db:
            async with db.begin():
                result = await pay_prepared_vip_balance(
                    db, verified_global_id=owner, request=request,
                    review_id=review_id, require_review=require_review,
                )
        return result

    return run


@router.post("/pay-balance")
async def pay_balance(
    body: PayInput,
    balance_pay: Annotated[Callable[[int, ShopRequest, str], Awaitable[dict]], Depends(get_balance_pay)],
    handoff_owner: Annotated[str, Depends(get_trusted_owner)],
    native_owner: Annotated[NonFinancialReadOwner, Depends(get_nonfinancial_read_owner)],
) -> dict:
    # The signed Shop handoff is not itself authority to debit the native account.
    if int(handoff_owner) != int(native_owner.global_id):
        raise _error(403, "SHOP_OWNER_MISMATCH")
    if body.method != "EFHC":
        raise _error(422, "SHOP_REQUEST_INVALID")
    try:
        result = await balance_pay(int(native_owner.global_id), _request(body), body.review_id)
        order_id = result.get("order_id")
        if result.get("status") != "PAID_PENDING_MANUAL" or type(order_id) is not int or order_id <= 0:
            raise _error(502, "SHOP_PAYMENT_RESULT_INVALID")
        return {"state": "paid", "order_id": str(order_id)}
    except ShopRequestError as exc:
        raise _domain_error(exc) from exc
