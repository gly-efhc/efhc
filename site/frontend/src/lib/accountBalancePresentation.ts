import type { SyncSnapshot } from "../services/snapshot.service";
import type { CurrentAccountBalances } from "../services/accountBalance.service";

/** Keep the newer, owner-verified financial read over stale PWA snapshots. */
export function overlayVerifiedAccountBalances(
  snapshot: SyncSnapshot,
  balances: CurrentAccountBalances | null | undefined,
  owner: string | null,
  snapshotUpdatedAt: number,
  balanceUpdatedAt: number,
): SyncSnapshot {
  if (!owner || !balances || balances.global_id !== owner ||
    snapshot.profile.global_id !== owner ||
    !Number.isFinite(balanceUpdatedAt) || balanceUpdatedAt <= 0 ||
    (Number.isFinite(snapshotUpdatedAt) && snapshotUpdatedAt >= balanceUpdatedAt)) {
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
