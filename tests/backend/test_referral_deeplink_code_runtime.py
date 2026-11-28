from app.identity.account_registration import (
    normalize_referral_start_param,
)


def test_normalize_referral_start_param():
    assert normalize_referral_start_param(" ref_ABC123 ") == "ABC123"
    assert normalize_referral_start_param("ABC123") == "ABC123"
    assert normalize_referral_start_param("ref_") is None
    assert normalize_referral_start_param("bad code") is None
