"""Pre-payment Shop requests; persistence and issuance belong to one owner unit."""

from __future__ import annotations

from hashlib import sha256
from hmac import compare_digest
import json

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Protocol


class ShopRequestError(ValueError):
    pass


class Outcome(str, Enum):
    PREPARED = "prepared"
    CANCELED = "canceled"
    ISSUED = "issued"
    PAID = "paid"
    TERMINAL_UNPAID = "terminal_unpaid"


@dataclass(frozen=True)
class ShopRequest:
    key: str
    sku: str
    method: str
    quantity: int
    custom_efhc_amount_d8: Decimal | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.key, str) or not self.key.strip()
            or self.key != self.key.strip() or len(self.key) > 128
            or not isinstance(self.sku, str) or not self.sku.strip()
            or self.sku != self.sku.strip()
            or self.method not in {"TON", "USDT", "EFHC"}
            or type(self.quantity) is not int or not 1 <= self.quantity <= 10
            or (self.method != "EFHC" and self.quantity != 1)
        ):
            raise ShopRequestError("SHOP_REQUEST_INVALID")
        value = self.custom_efhc_amount_d8
        if value is None:
            return
        try:
            amount = Decimal(str(value))
            if (
                self.sku != "EFHC_PACKAGE_CUSTOM" or self.method == "EFHC"
                or not amount.is_finite() or amount < 1
                or amount != amount.to_integral_value()
            ):
                raise ShopRequestError("SHOP_REQUEST_INVALID")
        except InvalidOperation as exc:
            raise ShopRequestError("SHOP_REQUEST_INVALID") from exc
        object.__setattr__(self, "custom_efhc_amount_d8", amount)


@dataclass(frozen=True)
class References:
    order_id: str
    intent_id: str | None = None


@dataclass(frozen=True)
class Review:
    asset: str
    amount: str
    review_id: str


def freeze_review(owner: int, request: ShopRequest, snapshot: dict) -> Review | None:
    """Project only the frozen amount; the identifier binds the full private snapshot."""
    quote = snapshot.get("quote")
    if not isinstance(quote, dict):
        return None
    amount = quote.get("expected_amount")
    if not isinstance(amount, str) or not 1 <= len(amount) <= 42:
        return None
    if not all(part.isascii() and part.isdecimal() for part in amount.split(".", maxsplit=1)):
        return None
    if Decimal(amount) <= 0:
        return None
    encoded = json.dumps(
        ["efhc.shop.review.v1", owner, request.key, snapshot],
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()
    return Review(request.method, amount, sha256(encoded).hexdigest())


def verify_review(review: Review | None, incoming_id: str) -> None:
    if review is None or not compare_digest(review.review_id, incoming_id):
        raise ShopRequestError("SHOP_REQUEST_REVIEW_MISMATCH")


@dataclass(frozen=True)
class Attempt:
    request: ShopRequest
    outcome: Outcome
    references: References | None = None
    review: Review | None = None


class OwnerTransaction(Protocol):
    async def find(self, key: str) -> Attempt | None:
        """Owner-only lookup. Project PAID only from canonical settlement proof.

        Unknown authoritative state stays ISSUED and occupies the owner lane.
        Release a terminal-unpaid issue only under existing server policy.
        """

    async def lane_busy(self, *, except_key: str | None = None) -> bool:
        """Exclude only this request; include every other active Shop operation."""

    async def save(self, attempt: Attempt) -> None:
        """Stage an immutable transition in the same transaction, never commit."""

    async def issue(self, request: ShopRequest) -> References:
        """Canonical server action, no root commit or external publication."""


class CheckoutStore(Protocol):
    def owner_unit(
        self, verified_owner: str, *, issuing: ShopRequest | None = None,
    ) -> AbstractAsyncContextManager[OwnerTransaction]:
        """Existing lock, single root transaction, commits only on successful exit.

        If issue needs a VIP item lock first, acquire in canonical order then
        re-read the request/owner lane. No alternate lock for the same lane.
        """


class Checkout:
    def __init__(self, store: CheckoutStore) -> None:
        self._store = store

    @staticmethod
    async def _matched(unit: OwnerTransaction, request: ShopRequest) -> Attempt | None:
        row = await unit.find(request.key)
        if row is not None and row.request != request:
            raise ShopRequestError("SHOP_REQUEST_PAYLOAD_MISMATCH")
        return row

    async def prepare(self, verified_owner: str, request: ShopRequest) -> Attempt:
        async with self._store.owner_unit(verified_owner) as unit:
            row = await self._matched(unit, request)
            if row is not None:
                return row
            if await unit.lane_busy():
                raise ShopRequestError("SHOP_REQUEST_ACTIVE")
            row = Attempt(request, Outcome.PREPARED)
            await unit.save(row)
            # Return the committed snapshot projection rather than a recomputed
            # quote; purely synthetic stores can also return the prepared row.
            stored = await unit.find(request.key)
            if stored is None or stored.outcome is not Outcome.PREPARED:
                raise ShopRequestError("SHOP_REQUEST_TRANSITION_REFUSED")
            return stored

    async def cancel(self, verified_owner: str, request: ShopRequest) -> Attempt:
        async with self._store.owner_unit(verified_owner) as unit:
            row = await self._matched(unit, request)
            if row is not None:
                if row.outcome == Outcome.CANCELED:
                    return row
                if row.outcome != Outcome.PREPARED:
                    raise ShopRequestError("SHOP_REQUEST_ALREADY_ISSUED")
            canceled = Attempt(request, Outcome.CANCELED)
            await unit.save(canceled)
            return canceled

    async def pay(self, verified_owner: str, request: ShopRequest) -> Attempt:
        async with self._store.owner_unit(verified_owner, issuing=request) as unit:
            row = await self._matched(unit, request)
            if row is not None and row.outcome in {
                Outcome.ISSUED, Outcome.PAID, Outcome.TERMINAL_UNPAID,
            }:
                return row
            if row is None or row.outcome != Outcome.PREPARED:
                raise ShopRequestError("SHOP_REQUEST_NOT_PREPARED")
            if await unit.lane_busy(except_key=request.key):
                raise ShopRequestError("SHOP_REQUEST_ACTIVE")
            references = await unit.issue(request)
            if not references.order_id or (
                (request.method == "EFHC") != (references.intent_id is None)
            ) or references.intent_id == "":
                raise ShopRequestError("SHOP_REQUEST_INCOMPLETE_RESULT")
            issued = replace(
                row,
                outcome=Outcome.PAID if request.method == "EFHC" else Outcome.ISSUED,
                references=references,
                review=None,
            )
            await unit.save(issued)
            return issued

    async def status(self, verified_owner: str, request: ShopRequest) -> Attempt | None:
        async with self._store.owner_unit(verified_owner) as unit:
            return await self._matched(unit, request)

    async def status_by_key(self, verified_owner: str, key: str) -> Attempt | None:
        if not key.strip() or key != key.strip() or len(key) > 128:
            raise ShopRequestError("SHOP_REQUEST_INVALID")
        async with self._store.owner_unit(verified_owner) as unit:
            return await unit.find(key)
