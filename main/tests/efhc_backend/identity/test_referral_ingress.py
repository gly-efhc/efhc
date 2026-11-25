"""Узкие контракты provider-neutral referral ingress цикла 1638."""

from __future__ import annotations

import pytest
from app.identity.referral_ingress import (
    ReferralIngressError,
    build_referral_ingress_contract,
    parse_referral_start_param,
)


def test_пустой_referral_ingress_не_создаёт_код() -> None:
    assert parse_referral_start_param(None).normalized_code is None
    assert parse_referral_start_param("  ").supplied is False


def test_referral_ingress_нормализует_telegram_prefix() -> None:
    result = parse_referral_start_param("  ref_ABC_123  ")
    assert result.normalized_code == "ABC_123"
    assert result.supplied is True


def test_referral_ingress_отклоняет_невалидный_код() -> None:
    with pytest.raises(ReferralIngressError) as captured:
        parse_referral_start_param("ref_***")
    assert captured.value.reason == "invalid_code"


def test_contract_запрещает_owner_и_idempotency_из_raw_param() -> None:
    contract = build_referral_ingress_contract()
    assert contract["цикл"] == 1638
    assert contract["хранилище_фронтенда"] == "sessionStorage"
    assert contract["сырой_параметр_не_owner"] is True
    assert contract["сырой_параметр_не_idempotency"] is True
    assert contract["поздняя_привязка"] is False
