from __future__ import annotations

from decimal import Decimal

from app.routes import admin_observability_routes, admin_reports_routes


def test_admin_observability_decimal_formatting_uses_decimals_kwarg():
    assert admin_observability_routes._numeric_str(
        Decimal("1.230000009")
    ) == "1.23"


def test_admin_reports_decimal_formatting_uses_decimals_kwarg():
    assert admin_reports_routes._num(Decimal("1.230000009")) == 1.23
