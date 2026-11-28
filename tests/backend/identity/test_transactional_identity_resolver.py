"""Причинные tests transactional IdentityResolver цикла 1612."""

from __future__ import annotations

import pytest
from app.identity import (
    AuthProvider,
    GlobalId,
    IdentityConflictCode,
    IdentityResolutionStatus,
    IdentityResolverCandidate,
    InvalidIdentityResolution,
    build_identity_resolver_contract,
)
from app.identity.identity_resolver import (
    _classify_candidates,
    _identity_advisory_lock_key,
)


def test_lock_key_детерминирован_и_не_равен_subject() -> None:
    first = _identity_advisory_lock_key(
        provider=AuthProvider.TELEGRAM,
        provider_tenant="default",
        provider_subject="123456789",
    )
    second = _identity_advisory_lock_key(
        provider=AuthProvider.TELEGRAM,
        provider_tenant="default",
        provider_subject="123456789",
    )
    other = _identity_advisory_lock_key(
        provider=AuthProvider.TELEGRAM,
        provider_tenant="default",
        provider_subject="123456780",
    )
    assert first == second
    assert first != other
    assert -(2**63) <= first < 2**63
    assert str(first) != "123456789"


def test_empty_candidates_возвращают_not_found() -> None:
    result = _classify_candidates(())
    assert result.status is IdentityResolutionStatus.NOT_FOUND
    assert result.global_id is None
    assert result.conflict_code is None


def test_active_verified_candidate_возвращает_global_id() -> None:
    result = _classify_candidates(
        (
            IdentityResolverCandidate(
                global_id=42,
                status="active",
                is_verified=True,
                verified_at_present=True,
            ),
        )
    )
    assert result.status is IdentityResolutionStatus.RESOLVED
    assert result.global_id == GlobalId(42)
    assert result.conflict_code is None


@pytest.mark.parametrize(
    ("candidate", "code"),
    [
        (
            IdentityResolverCandidate(
                global_id=42,
                status="disabled",
                is_verified=True,
                verified_at_present=True,
            ),
            IdentityConflictCode.IDENTITY_INACTIVE,
        ),
        (
            IdentityResolverCandidate(
                global_id=42,
                status="active",
                is_verified=False,
                verified_at_present=False,
            ),
            IdentityConflictCode.IDENTITY_UNVERIFIED,
        ),
        (
            IdentityResolverCandidate(
                global_id=0,
                status="active",
                is_verified=True,
                verified_at_present=True,
            ),
            IdentityConflictCode.INVALID_GLOBAL_ID,
        ),
    ],
)
def test_invalid_candidate_возвращает_fail_closed_conflict(
    candidate: IdentityResolverCandidate,
    code: IdentityConflictCode,
) -> None:
    result = _classify_candidates((candidate,))
    assert result.status is IdentityResolutionStatus.CONFLICT
    assert result.global_id is None
    assert result.conflict_code is code


def test_multiple_candidates_не_выбирают_account() -> None:
    candidate = IdentityResolverCandidate(
        global_id=42,
        status="active",
        is_verified=True,
        verified_at_present=True,
    )
    result = _classify_candidates((candidate, candidate))
    assert result.status is IdentityResolutionStatus.CONFLICT
    assert result.global_id is None
    assert (
        result.conflict_code
        is IdentityConflictCode.MULTIPLE_MATCHES
    )


def test_conflict_code_нельзя_передать_сырой_строкой() -> None:
    from app.identity import IdentityResolution

    with pytest.raises(InvalidIdentityResolution):
        IdentityResolution.conflict(  # type: ignore[arg-type]
            "multiple_matches"
        )


def test_machine_contract_фиксирует_transactional_guards() -> None:
    contract = build_identity_resolver_contract()
    assert contract["цикл"] == 1612
    assert contract["логический_owner"] == "global_id"
    assert contract["физическая_owner_reference"] == "users.global_id"
    assert contract["блокировки"] == {
        "missing_row": "pg_advisory_xact_lock",
        "existing_row": "SELECT_FOR_UPDATE",
        "ключ_детерминирован": True,
        "ключ_не_содержит_raw_subject": True,
    }
    assert contract["side_effects"]["auto_merge"] is False
    assert contract["side_effects"]["account_creation"] is False
