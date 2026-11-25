"""Серверный целочисленный authority метрик Admin → Банк.

Frontend отображает готовые значения и не пересобирает финансовые формулы.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

D8_SCALE = 100_000_000
PCT_SCALE = 100_000_000
INITIAL_SUPPLY_D8 = 5_000_000 * D8_SCALE
PANEL_PRICE_D8 = 100 * D8_SCALE


def _pct_d8(numerator: int, denominator: int) -> int:
    """Вернуть знаковый процент ×1e8 с целочисленным half-up округлением."""
    if denominator == 0:
        return 0
    negative = (numerator < 0) != (denominator < 0)
    n = abs(int(numerator))
    d = abs(int(denominator))
    scaled = (n * 100 * PCT_SCALE + d // 2) // d
    return -scaled if negative else scaled


def calculate_bank_metrics_snapshot(source: Mapping[str, Any]) -> dict[str, int]:
    """Рассчитать метрики Банка из нормализованных целочисленных D8-входов."""
    reserve = int(source.get("reserve_efhc_d8") or 0)
    users_main = int(source.get("users_main_efhc_d8") or 0)
    users_bonus = int(source.get("users_bonus_efhc_d8") or 0)
    panel_spent = max(0, int(source.get("panel_spent_efhc_d8") or 0))
    generated = max(0, int(source.get("generated_kwh_d8") or 0))
    converted = max(0, int(source.get("converted_kwh_d8") or 0))
    fixed_generated = int(source.get("fixed_generated_kwh_d8") or 0)
    fixed_population = max(0, int(source.get("fixed_population") or 0))
    minted = int(source.get("minted_efhc_d8") or 0)
    burned = int(source.get("burned_efhc_d8") or 0)

    circulation = users_main + users_bonus
    actual_mass = reserve + circulation
    expected_supply = INITIAL_SUPPLY_D8 + minted - burned

    # Владелец утвердил положительный знак расходов перед вычитанием.
    # Пример: 150 - 100 = 50; двойное вычитание отрицательного расхода запрещено.
    new_obligations = generated - panel_spent
    fixed_obligations = fixed_generated - fixed_population * PANEL_PRICE_D8
    generated_base = panel_spent + fixed_obligations
    pending = generated - converted
    integrity_delta = actual_mass - expected_supply

    return {
        "reserve_efhc_d8": reserve,
        "circulation_efhc_d8": circulation,
        "users_main_efhc_d8": users_main,
        "users_bonus_efhc_d8": users_bonus,
        "actual_mass_efhc_d8": actual_mass,
        "panel_spent_efhc_d8": panel_spent,
        "generated_kwh_d8": generated,
        "new_obligations_efhcm_d8": new_obligations,
        "fixed_obligations_efhcm_d8": fixed_obligations,
        "converted_kwh_d8": converted,
        "pending_kwh_d8": pending,
        "expected_supply_efhc_d8": expected_supply,
        "integrity_delta_efhc_d8": integrity_delta,
        # Базы процентов задаются server-side; исключения перечислены ниже.
        "reserve_pct_d8": _pct_d8(reserve, expected_supply),
        "circulation_pct_d8": _pct_d8(circulation, expected_supply),
        # Новые обязательства показываются относительно текущей фактической массы.
        "new_obligations_pct_d8": _pct_d8(new_obligations, actual_mass),
        "users_main_pct_d8": _pct_d8(users_main, expected_supply),
        "users_bonus_pct_d8": _pct_d8(users_bonus, expected_supply),
        "actual_mass_pct_d8": _pct_d8(actual_mass, expected_supply),
        "fixed_obligations_pct_d8": _pct_d8(fixed_obligations, expected_supply),
        # Расход Панелей считается относительно пользовательского EFHCm.
        "panel_spent_pct_d8": _pct_d8(panel_spent, users_main),
        # Генерация kWh сравнивается с расходами на панели + фиксированными обязательствами.
        "generated_pct_d8": _pct_d8(generated, generated_base) if generated_base > 0 else 0,
        # Конвертация и ожидание считаются относительно сгенерированного kWh.
        "converted_pct_d8": _pct_d8(converted, generated),
        "pending_pct_d8": _pct_d8(pending, generated),
        "integrity_pct_d8": _pct_d8(actual_mass, expected_supply),
    }


_SOURCE_SQL = text(
    """
    with
    bank as (
      select coalesce(max(balance) filter (where key = 'EFHC_MAIN'), 0)::numeric as reserve
      from efhc_core.bank_balance
    ),
    users_totals as (
      select
        coalesce(sum(main_balance), 0)::numeric as users_main,
        coalesce(sum(bonus_balance), 0)::numeric as users_bonus,
        coalesce(sum(exchanged_kwh_total), 0)::numeric as converted
      from efhc_core.users
    ),
    panels_totals as (
      select
        coalesce(sum(generated_kwh), 0)::numeric as generated,
        coalesce(sum(generated_kwh) filter (where not is_active or is_archived), 0)::numeric as fixed_generated,
        count(*) filter (where not is_active or is_archived)::bigint as fixed_population
      from efhc_core.panels
      where coalesce(meta ->> 'protectively_voided', 'false') <> 'true'
    ),
    panel_cashflow as (
      select
        coalesce(sum(amount), 0)::numeric as activation_spent
      from efhc_core.efhc_transfers_log
      where reason in (
        'panel_purchase',
        'panel_activation',
        'panel_reactivation'
      )
        and direction = 'debit'
    ),
    protective_voids as (
      select
        coalesce(
          sum(
            coalesce((event ->> 'original_payment_bonus')::numeric, 0)
            + coalesce((event ->> 'original_payment_main')::numeric, 0)
          ),
          0
        )::numeric as voided_spent
      from efhc_core.panels p
      cross join lateral jsonb_array_elements(
        case
          when jsonb_typeof(p.meta -> 'protective_events') = 'array'
            then p.meta -> 'protective_events'
          else '[]'::jsonb
        end
      ) as event
      where event ->> 'op' = 'protective_deactivate'
    ),
    supply as (
      select
        coalesce(sum(amount) filter (
          where system_entity = 'BANK_EFHC' and reason = 'admin_bank_mint'
        ), 0)::numeric as minted,
        coalesce(sum(amount) filter (
          where system_entity = 'BANK_EFHC' and reason = 'admin_bank_burn'
        ), 0)::numeric as burned
      from efhc_core.efhc_transfers_log
    )
    select
      trunc(bank.reserve * 100000000)::bigint as reserve_efhc_d8,
      trunc(users_totals.users_main * 100000000)::bigint as users_main_efhc_d8,
      trunc(users_totals.users_bonus * 100000000)::bigint as users_bonus_efhc_d8,
      trunc((panel_cashflow.activation_spent - protective_voids.voided_spent) * 100000000)::bigint as panel_spent_efhc_d8,
      trunc(panels_totals.generated * 100000000)::bigint as generated_kwh_d8,
      trunc(users_totals.converted * 100000000)::bigint as converted_kwh_d8,
      trunc(panels_totals.fixed_generated * 100000000)::bigint as fixed_generated_kwh_d8,
      panels_totals.fixed_population as fixed_population,
      trunc(supply.minted * 100000000)::bigint as minted_efhc_d8,
      trunc(supply.burned * 100000000)::bigint as burned_efhc_d8
    from bank
    cross join users_totals
    cross join panels_totals
    cross join panel_cashflow
    cross join protective_voids
    cross join supply
    """
)

_UPSERT_SQL = text(
    """
    insert into efhc_core.bank_metrics_snapshot (
      id,
      reserve_efhc_d8, circulation_efhc_d8, users_main_efhc_d8,
      users_bonus_efhc_d8, actual_mass_efhc_d8, panel_spent_efhc_d8,
      generated_kwh_d8, new_obligations_efhcm_d8,
      fixed_obligations_efhcm_d8, converted_kwh_d8, pending_kwh_d8,
      expected_supply_efhc_d8, integrity_delta_efhc_d8,
      reserve_pct_d8, circulation_pct_d8, new_obligations_pct_d8,
      users_main_pct_d8, users_bonus_pct_d8, actual_mass_pct_d8,
      fixed_obligations_pct_d8, panel_spent_pct_d8, generated_pct_d8,
      converted_pct_d8, pending_pct_d8, integrity_pct_d8, updated_at
    ) values (
      1,
      :reserve_efhc_d8, :circulation_efhc_d8, :users_main_efhc_d8,
      :users_bonus_efhc_d8, :actual_mass_efhc_d8, :panel_spent_efhc_d8,
      :generated_kwh_d8, :new_obligations_efhcm_d8,
      :fixed_obligations_efhcm_d8, :converted_kwh_d8, :pending_kwh_d8,
      :expected_supply_efhc_d8, :integrity_delta_efhc_d8,
      :reserve_pct_d8, :circulation_pct_d8, :new_obligations_pct_d8,
      :users_main_pct_d8, :users_bonus_pct_d8, :actual_mass_pct_d8,
      :fixed_obligations_pct_d8, :panel_spent_pct_d8, :generated_pct_d8,
      :converted_pct_d8, :pending_pct_d8, :integrity_pct_d8,
      timezone('utc', now())
    )
    on conflict (id) do update set
      reserve_efhc_d8 = excluded.reserve_efhc_d8,
      circulation_efhc_d8 = excluded.circulation_efhc_d8,
      users_main_efhc_d8 = excluded.users_main_efhc_d8,
      users_bonus_efhc_d8 = excluded.users_bonus_efhc_d8,
      actual_mass_efhc_d8 = excluded.actual_mass_efhc_d8,
      panel_spent_efhc_d8 = excluded.panel_spent_efhc_d8,
      generated_kwh_d8 = excluded.generated_kwh_d8,
      new_obligations_efhcm_d8 = excluded.new_obligations_efhcm_d8,
      fixed_obligations_efhcm_d8 = excluded.fixed_obligations_efhcm_d8,
      converted_kwh_d8 = excluded.converted_kwh_d8,
      pending_kwh_d8 = excluded.pending_kwh_d8,
      expected_supply_efhc_d8 = excluded.expected_supply_efhc_d8,
      integrity_delta_efhc_d8 = excluded.integrity_delta_efhc_d8,
      reserve_pct_d8 = excluded.reserve_pct_d8,
      circulation_pct_d8 = excluded.circulation_pct_d8,
      new_obligations_pct_d8 = excluded.new_obligations_pct_d8,
      users_main_pct_d8 = excluded.users_main_pct_d8,
      users_bonus_pct_d8 = excluded.users_bonus_pct_d8,
      actual_mass_pct_d8 = excluded.actual_mass_pct_d8,
      fixed_obligations_pct_d8 = excluded.fixed_obligations_pct_d8,
      panel_spent_pct_d8 = excluded.panel_spent_pct_d8,
      generated_pct_d8 = excluded.generated_pct_d8,
      converted_pct_d8 = excluded.converted_pct_d8,
      pending_pct_d8 = excluded.pending_pct_d8,
      integrity_pct_d8 = excluded.integrity_pct_d8,
      updated_at = excluded.updated_at
    returning *
    """
)


async def refresh_bank_metrics_snapshot(db: AsyncSession) -> dict[str, Any]:
    """Обновить singleton-снимок из канонических таблиц без скрытого commit."""
    await db.execute(text("SET LOCAL statement_timeout = '1500ms'"))
    source_row = (await db.execute(_SOURCE_SQL)).mappings().one()
    metrics = calculate_bank_metrics_snapshot(dict(source_row))
    row = (await db.execute(_UPSERT_SQL, metrics)).mappings().one()
    snapshot = dict(row)
    return snapshot



def format_scaled_d8(value: int) -> str:
    """Форматировать целое ×1e8 без float."""
    number = int(value)
    sign = "-" if number < 0 else ""
    absolute = abs(number)
    whole, fraction = divmod(absolute, D8_SCALE)
    return f"{sign}{whole}.{fraction:08d}"


def format_percent_d8(value: int) -> str:
    """Форматировать процент, хранимый как целое ×1e8."""
    return format_scaled_d8(int(value))


def snapshot_to_facts(snapshot: Mapping[str, Any]) -> dict[str, str]:
    """Преобразовать снимок в display-safe строки без клиентских формул."""
    amount_fields = {
        "bank_metrics_reserve_efhc": "reserve_efhc_d8",
        "bank_metrics_circulation_efhc": "circulation_efhc_d8",
        "bank_metrics_users_main_efhc": "users_main_efhc_d8",
        "bank_metrics_users_bonus_efhc": "users_bonus_efhc_d8",
        "bank_metrics_actual_mass_efhc": "actual_mass_efhc_d8",
        "bank_metrics_panel_spent_efhc": "panel_spent_efhc_d8",
        "bank_metrics_generated_kwh": "generated_kwh_d8",
        "bank_metrics_new_obligations_efhcm": "new_obligations_efhcm_d8",
        "bank_metrics_fixed_obligations_efhcm": "fixed_obligations_efhcm_d8",
        "bank_metrics_converted_kwh": "converted_kwh_d8",
        "bank_metrics_pending_kwh": "pending_kwh_d8",
        "bank_metrics_expected_supply_efhc": "expected_supply_efhc_d8",
        "bank_metrics_integrity_delta_efhc": "integrity_delta_efhc_d8",
    }
    percent_fields = {
        "bank_metrics_reserve_pct": "reserve_pct_d8",
        "bank_metrics_circulation_pct": "circulation_pct_d8",
        "bank_metrics_new_obligations_pct": "new_obligations_pct_d8",
        "bank_metrics_users_main_pct": "users_main_pct_d8",
        "bank_metrics_users_bonus_pct": "users_bonus_pct_d8",
        "bank_metrics_actual_mass_pct": "actual_mass_pct_d8",
        "bank_metrics_fixed_obligations_pct": "fixed_obligations_pct_d8",
        "bank_metrics_panel_spent_pct": "panel_spent_pct_d8",
        "bank_metrics_generated_pct": "generated_pct_d8",
        "bank_metrics_converted_pct": "converted_pct_d8",
        "bank_metrics_pending_pct": "pending_pct_d8",
        "bank_metrics_integrity_pct": "integrity_pct_d8",
    }
    facts = {
        key: format_scaled_d8(int(snapshot.get(column) or 0))
        for key, column in amount_fields.items()
    }
    facts.update(
        {
            key: format_percent_d8(int(snapshot.get(column) or 0))
            for key, column in percent_fields.items()
        }
    )
    facts["bank_metrics_ready"] = "1"
    facts["bank_metrics_integrity_ok"] = (
        "1" if int(snapshot.get("integrity_delta_efhc_d8") or 0) == 0 else "0"
    )
    facts["bank_metrics_updated_at"] = snapshot_updated_at_iso(snapshot.get("updated_at"))
    return facts

def snapshot_updated_at_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value or "")


__all__ = [
    "D8_SCALE",
    "PCT_SCALE",
    "calculate_bank_metrics_snapshot",
    "format_scaled_d8",
    "format_percent_d8",
    "refresh_bank_metrics_snapshot",
    "snapshot_to_facts",
    "snapshot_updated_at_iso",
]
