/**
 * Owner-controlled system ADS placements.
 *
 * System placements are not user earning tasks and must never appear in the
 * Tasks catalog. The withdrawal placement is mandatory before every valid
 * withdrawal submission, grants exactly zero EFHCb, has no fee/fee-waiver
 * meaning, and must not be constrained by a task-style daily reward limit.
 *
 * The physical v174.70 backend does not yet expose that exact unlimited
 * system-placement contract. Current frontend therefore fails closed until a
 * compatible backend contract is synchronized.
 */
export const WITHDRAW_REQUIRED_AD_PLACEMENT_CODE = "withdraw_required_ad" as const;

export function isSystemAdPlacementCode(code: string): boolean {
  return code === WITHDRAW_REQUIRED_AD_PLACEMENT_CODE;
}
