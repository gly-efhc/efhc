from app.integrations.ton_memo import build_deposit_memo
from app.services.watcher_service import _parse_memo


def test_direct_open_memo_is_recognized_by_watcher_parser() -> None:
    memo = build_deposit_memo(123456789)

    kind, params = _parse_memo(memo)

    assert kind == "simple_efhc"
    assert params == {"tg_id": 123456789}


def test_canonical_direct_deposit_memo_is_not_bad() -> None:
    kind, params = _parse_memo("EFHC:123456789")

    assert kind != "bad"
    assert params["tg_id"] == 123456789


def test_legacy_direct_deposit_memo_still_has_safe_path() -> None:
    kind, params = _parse_memo("EFHC123456789")

    assert kind == "simple_efhc"
    assert params == {"tg_id": 123456789}
