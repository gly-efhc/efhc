import type { SyncSnapshot } from "../services/snapshot.service";
import type { CurrentAccountBalances } from "../services/accountBalance.service";

/** A verified account GET outranks cached snapshots, regardless of client timestamps. */
export function overlayVerifiedAccountBalances(
  snapshot: SyncSnapshot,
  balances: CurrentAccountBalances | null | undefined,
  owner: string | null,
): SyncSnapshot {
  if (!owner || !balances || balances.global_id !== owner ||
    snapshot.profile.global_id !== owner) {
    return snapshot;
  }
  if (balances.main_balance === snapshot.profile.main_balance &&
    balances.bonus_balance === snapshot.profile.bonus_balance) return snapshot;
  return {
    ...snapshot,
    profile: {
      ...snapshot.profile,
      main_balance: balances.main_balance,
      bonus_balance: balances.bonus_balance,
    },
  };
}
