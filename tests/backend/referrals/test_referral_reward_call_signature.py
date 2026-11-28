from __future__ import annotations

from decimal import Decimal

import pytest
from app.services import referral_service

pytestmark = pytest.mark.asyncio


async def test_unit_reward_использует_номерной_slot_и_отдельный_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = object()
    slot_calls: list[tuple[object, int, int]] = []
    credit_calls: list[dict[str, object]] = []

    async def _reserve(
        candidate_db, *, inviter_global_id: int, buyer_global_id: int
    ) -> int:
        slot_calls.append(
            (candidate_db, int(inviter_global_id), int(buyer_global_id))
        )
        return 10

    async def _owner(candidate_db, *, global_id: int):
        assert candidate_db is db
        return referral_service._ReferralOwner(global_id=int(global_id))

    async def _telegram_subject(candidate_db, *, global_id: int):
        assert candidate_db is db
        assert global_id in {901001, 901002}
        return None

    async def _credit(**kwargs) -> None:
        credit_calls.append(kwargs)

    monkeypatch.setattr(
        referral_service,
        "_reserve_direct_reward_slot",
        _reserve,
    )
    monkeypatch.setattr(referral_service, "_load_referral_owner", _owner)
    monkeypatch.setattr(
        referral_service,
        "resolve_verified_telegram_subject",
        _telegram_subject,
    )
    monkeypatch.setattr(
        referral_service,
        "credit_user_bonus_from_bank_nocommit",
        _credit,
    )

    await referral_service._maybe_reward_active_unit_bonus(
        db,
        inviter_global_id=901001,
        buyer_global_id=901002,
    )

    assert slot_calls == [(db, 901001, 901002)]
    assert len(credit_calls) == 1
    assert credit_calls[0]["db"] is db
    assert credit_calls[0]["global_id"] == 901001
    assert credit_calls[0]["amount"] == Decimal("0.10000000")
    assert credit_calls[0]["reason"] == "referral_active_unit"
    assert (
        credit_calls[0]["idempotency_key"]
        == "REF_ACT_UNIT:G0000901001:N00010"
    )
