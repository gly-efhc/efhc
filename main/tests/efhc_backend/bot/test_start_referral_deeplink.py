from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "backend/app/bot/handlers/start_handlers.py"


def test_start_referral_payload_parser_preserves_invalid_payload():
    src = SRC.read_text(encoding="utf-8")
    assert "def _extract_start_payload" in src
    assert "split(maxsplit=1)" in src
    assert "payload = parts[1].strip()" in src
    assert "normalize_referral_start_param" not in src


def test_start_referral_is_atomic_with_first_user_creation():
    src = SRC.read_text(encoding="utf-8")
    payload_pos = src.index("payload = _extract_start_payload")
    onboard_pos = src.index("await onboard_user_at_first_creation_in_transaction")
    gate_pos = src.index("if required_channel_id and not is_subscribed")
    assert payload_pos < onboard_pos < gate_pos
    assert "await ensure_user" not in src
    assert "attach_referral_code_for_user" not in src


def test_invalid_new_referral_fails_closed():
    src = SRC.read_text(encoding="utf-8")
    assert "except ReferralOnboardingRejected as exc" in src
    assert "return" in src.split(
        "except ReferralOnboardingRejected as exc", 1
    )[1].split("except Exception", 1)[0]
