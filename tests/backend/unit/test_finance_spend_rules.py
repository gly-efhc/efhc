import pathlib
from decimal import Decimal

import pytest
from app.standards.finance_rules import split_bonus_then_main


def d(x: str) -> Decimal:
    return Decimal(x).quantize(Decimal("0.00000001"))


@pytest.mark.smoke
@pytest.mark.parametrize(
    "bonus,main,amount,exp_bonus,exp_main",
    [
        (
            "100.00000000",
            "50.00000000",
            "60.00000000",
            "60.00000000",
            "0.00000000",
        ),
        (
            "30.00000000",
            "50.00000000",
            "60.00000000",
            "30.00000000",
            "30.00000000",
        ),
        (
            "0.00000000",
            "50.00000000",
            "40.00000000",
            "0.00000000",
            "40.00000000",
        ),
        (
            "10.00000000",
            "30.00000000",
            "40.00000000",
            "10.00000000",
            "30.00000000",
        ),
    ],
)
def test_spend_rule_bonus_then_main(
    bonus,
    main,
    amount,
    exp_bonus,
    exp_main,
):
    br = split_bonus_then_main(
        bonus_balance=d(bonus),
        main_balance=d(main),
        amount=d(amount),
    )
    assert br.bonus_part == d(exp_bonus)
    assert br.main_part == d(exp_main)


@pytest.mark.smoke
def test_spend_rule_insufficient_raises():
    with pytest.raises(ValueError):
        split_bonus_then_main(
            bonus_balance=d("10.00000000"),
            main_balance=d("20.00000000"),
            amount=d("40.00000000"),
        )


@pytest.mark.smoke
def test_withdraw_is__main__only_no_bonus_debit_calls():
    root = (
        pathlib.Path(__file__).resolve().parents[3] / "backend" / "app"
    )
    forbidden = [
        "debit_user_bonus_to_bank",
        "bonus_to_bank",
        'balance_type="bonus"',
    ]
    for p in root.rglob("*.py"):
        if "withdraw" not in str(p).lower():
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for f in forbidden:
            assert (
                f not in txt
            ), f"Forbidden '{f}' found in withdraw-related file: {p}"
