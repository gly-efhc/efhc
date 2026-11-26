from __future__ import annotations
import pytest
from demo_backend.tonconnect import demo_proof_subject


def test_test_proof_binding_is_deterministic_and_separate():
    assert demo_proof_subject("0000000002") == 4_000_000_000_002
    assert demo_proof_subject("0000000088") != demo_proof_subject("0000000002")
    assert demo_proof_subject("0000000088") > 4_000_000_000_000


@pytest.mark.parametrize("value", ["88", "0000000000", "00000000ab", "000000008 8"])
def test_rejects_invalid_global_id(value):
    with pytest.raises(ValueError):
        demo_proof_subject(value)
