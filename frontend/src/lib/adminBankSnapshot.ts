/** The Bank UI consumes one complete snapshot; missing values are never real zeroes. */
export const BANK_NUMERIC_FIELDS = [
  'reserve_efhc','circulation_efhc','expected_supply_efhc','actual_mass_efhc','integrity_delta_efhc',
  'users_main_efhc','users_bonus_efhc','new_obligations_efhcm','fixed_obligations_efhcm',
  'panel_spent_efhc','generated_kwh','converted_kwh','pending_kwh',
  'reserve_pct','circulation_pct','users_main_pct','users_bonus_pct','actual_mass_pct',
  'new_obligations_pct','fixed_obligations_pct','panel_spent_pct','generated_pct','converted_pct','pending_pct','integrity_pct',
] as const;

export type AdminBankSnapshot = {
  ok: boolean; facts: Record<string,string>; ts?: string; notes?: string|null;
};
export function requireBankSnapshot(value: unknown): AdminBankSnapshot {
  const response=value as AdminBankSnapshot|null;
  const facts=response?.facts;
  if (response?.ok !== true || !facts || facts.bank_metrics_ready !== '1' ||
      !['0','1'].includes(facts.bank_metrics_integrity_ok) ||
      BANK_NUMERIC_FIELDS.some(key=>typeof facts['bank_metrics_'+key] !== 'string' || !/^-?\d+\.\d{8}$/.test(facts['bank_metrics_'+key]))) {
    throw new Error('BANK_SNAPSHOT_INCOMPLETE');
  }
  return response;
}
