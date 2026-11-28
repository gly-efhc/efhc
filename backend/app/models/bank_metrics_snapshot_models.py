"""Целочисленный singleton-снимок канонических метрик Admin → Банк."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, SmallInteger, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from .base import SCHEMA, Base


class BankMetricsSnapshot(Base):
    """Материализованные D8-значения и проценты для серверного Bank authority."""

    __tablename__ = "bank_metrics_snapshot"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_bank_metrics_snapshot_singleton"),
        CheckConstraint(
            "panel_spent_efhc_d8 >= 0",
            name="ck_bank_metrics_snapshot_spent_nonnegative",
        ),
        CheckConstraint(
            "generated_kwh_d8 >= 0",
            name="ck_bank_metrics_snapshot_generated_nonnegative",
        ),
        CheckConstraint(
            "converted_kwh_d8 >= 0",
            name="ck_bank_metrics_snapshot_converted_nonnegative",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        default=1,
        server_default=text("1"),
    )
    reserve_efhc_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    circulation_efhc_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    users_main_efhc_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    users_bonus_efhc_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    actual_mass_efhc_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    panel_spent_efhc_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    generated_kwh_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    new_obligations_efhcm_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    fixed_obligations_efhcm_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    converted_kwh_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    pending_kwh_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    expected_supply_efhc_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    integrity_delta_efhc_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    reserve_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    circulation_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    new_obligations_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    users_main_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    users_bonus_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    actual_mass_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    fixed_obligations_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    panel_spent_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    generated_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    converted_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    pending_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    integrity_pct_d8: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
