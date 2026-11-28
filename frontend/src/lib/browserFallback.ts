import type { SyncSnapshot } from "../services/snapshot.service";
import { parseGlobalId } from "../types/identity";

export function getBrowserFallbackSnapshot(): SyncSnapshot {
  return {
    profile: {
      // Zero-only visual placeholder. Server session is authoritative.
      global_id: parseGlobalId("0000000001"),
      tg_id: 0,
      username: "EFHC Player",
      is_vip: false,
      has_activ: false,
      main_balance: "0.00000000",
      bonus_balance: "0.00000000",
      available_kwh: "0.00000000",
      total_generated_kwh: "0.00000000",
      gen_per_sec_base: "0.00000000",
      gen_per_sec_vip: "0.00000000",
    },
    panels: {
      active_count: 0,
      total_generated_by_panels: "0.00000000",
      nearest_expire_at: null,
    },
    exchange_preview: {
      ok: true,
      available_kwh: "0.00000000",
      max_exchangeable_kwh: "0.00000000",
      rate_kwh_to_efhc: "1.00000000",
      detail: "",
    },
    meta: {
      server_now_iso: new Date(0).toISOString(),
      gen_per_sec_effective: "0.00000000",
      next_scheduler_eta_sec: 0,
      fallback_task_id: null,
    },
  };
}

/** Empty local display model for an owner who has not synchronized yet. */
// The pre-auth placeholder follows the existing browser display contract;
// it is never used as an authenticated owner or a query key.
export function emptyOwnerSnapshot(globalId: string = "0000000001"): SyncSnapshot {
  return {
    profile: {global_id: parseGlobalId(globalId), is_vip: false, has_activ: false,
      main_balance: "0.00000000", bonus_balance: "0.00000000", available_kwh: "0.00000000",
      total_generated_kwh: "0.00000000", gen_per_sec_base: "0.00000000", gen_per_sec_vip: "0.00000000"},
    panels: {active_count: 0, total_generated_by_panels: "0.00000000", nearest_expire_at: null},
    exchange_preview: {ok: false, available_kwh: "0.00000000", max_exchangeable_kwh: "0.00000000", rate_kwh_to_efhc: "0.00000000", detail: ""},
    meta: {server_now_iso: "", gen_per_sec_effective: "0.00000000", next_scheduler_eta_sec: 0, fallback_task_id: null},
  };
}
