from decimal import Decimal

from app.domain.panels_rules import (
    allocate_panel_payment_splits,
    calculate_protective_refund_split,
    calculate_protective_void_amounts,
)


def test_protective_void_примеры_соответствуют_owner_contract() -> None:
    cases = [
        ("15", "40", "15", "0", "100"),
        ("15", "0", "0", "15", "85"),
        ("15", "6", "6", "9", "91"),
        ("75", "5", "5", "70", "30"),
        ("100", "0", "0", "100", "0"),
    ]
    for generated, available, unused, realized, net in cases:
        result = calculate_protective_void_amounts(
            generated_kwh=Decimal(generated),
            available_kwh=Decimal(available),
        )
        assert result.unused_kwh == Decimal(unused).quantize(Decimal("0.00000001"))
        assert result.realized_kwh == Decimal(realized).quantize(Decimal("0.00000001"))
        assert result.net_refund_efhc == Decimal(net).quantize(Decimal("0.00000001"))


def test_refund_offset_сначала_уменьшает_efhcb_затем_efhcm() -> None:
    result = calculate_protective_refund_split(
        original_bonus=Decimal("70"),
        original_main=Decimal("30"),
        realized_offset=Decimal("15"),
    )
    assert result.bonus_part == Decimal("55.00000000")
    assert result.main_part == Decimal("30.00000000")

    result = calculate_protective_refund_split(
        original_bonus=Decimal("20"),
        original_main=Decimal("80"),
        realized_offset=Decimal("70"),
    )
    assert result.bonus_part == Decimal("0.00000000")
    assert result.main_part == Decimal("30.00000000")


def test_batch_activation_split_детерминирован_правилом_bonus_first() -> None:
    splits = allocate_panel_payment_splits(
        panel_ids=[101, 102],
        spent_bonus=Decimal("130"),
        spent_main=Decimal("70"),
    )
    assert splits[101].bonus_part == Decimal("100.00000000")
    assert splits[101].main_part == Decimal("0.00000000")
    assert splits[102].bonus_part == Decimal("30.00000000")
    assert splits[102].main_part == Decimal("70.00000000")
