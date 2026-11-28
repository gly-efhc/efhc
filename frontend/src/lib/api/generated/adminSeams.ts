// AUTO-GENERATED FILE. DO NOT EDIT MANUALLY.
// Checked-in generated contract artifact; historical generator removed from current HEAD.

import {
  apiRequest,
  type ApiRequestOptions,
  type HttpMethod,
} from "../../api";
import type { DbId } from "../../../types/db-id";

export function adminPath(
  template: string,
  values: Record<string, string | number>,
): string {
  let out = template;
  for (const [key, value] of Object.entries(values)) {
    out = out.replace(
      `{${key}}`,
      encodeURIComponent(String(value)),
    );
  }
  return out;
}

export async function adminApiRequest<T>(
  path: string,
  method: HttpMethod,
  opts: ApiRequestOptions = {},
): Promise<T> {
  return apiRequest<T>(path, method, opts);
}

export const ADMIN_ACCESS_PATH =
  "/admin/access" as const;
export const ADMIN_ADS_PROVIDERS_PATH =
  "/admin/ads/providers" as const;
export const ADMIN_ADS_PROVIDER_PATH =
  "/admin/ads/providers/{code}" as const;
export const ADMIN_ADS_PROVIDER_SECRET_REPLACE_PATH =
  "/admin/ads/providers/{code}/secrets/replace" as const;
export const ADMIN_ADS_PROVIDER_SECRET_DELETE_PATH =
  "/admin/ads/providers/{code}/secrets/delete" as const;
export const ADMIN_ADS_PROVIDER_TEST_PATH =
  "/admin/ads/providers/{code}/test" as const;
export const ADMIN_ADS_PROVIDER_RESET_ERRORS_PATH =
  "/admin/ads/providers/{code}/reset-errors" as const;
export const ADMIN_ADS_DASHBOARD_PATH =
  "/admin/ads/dashboard" as const;
export const ADMIN_ADS_REVENUE_OPTIMIZER_PATH =
  "/admin/ads/revenue-optimizer" as const;
export const ADMIN_ADS_REVENUE_OPTIMIZER_APPLY_PATH =
  "/admin/ads/revenue-optimizer/apply" as const;
export const ADMIN_BANK_BALANCE_PATH =
  "/admin/bank/balance" as const;
export const ADMIN_BANK_BURN_PATH =
  "/admin/bank/burn" as const;
export const ADMIN_BANK_MINT_PATH =
  "/admin/bank/mint" as const;
export const ADMIN_BANK_TRANSFER_ROLLBACK_PATH =
  "/admin/bank/transfers/{transfer_log_id}/rollback" as const;
export const ADMIN_BONUSES_PATH =
  "/admin/bonuses" as const;
export const ADMIN_EFHC_DEPOSITS_PROCESS_PATH =
  "/admin/efhc-deposits/process" as const;
export const ADMIN_EFHC_DEPOSITS_INBOX_PATH =
  "/admin/efhc-deposits/inbox" as const;
export const ADMIN_EFHC_DEPOSITS_UNMATCHED_PATH =
  "/admin/efhc-deposits/unmatched" as const;
export const ADMIN_EFHC_DEPOSITS_REPROCESS_TX_HASH_PATH =
  "/admin/efhc-deposits/reprocess/{tx_hash}" as const;
export const ADMIN_EFHC_DEPOSITS_RUNTIME_SUMMARY_PATH =
  "/admin/efhc-deposits/runtime-summary" as const;

export type AdminEfhcDepositsRuntimeSummaryResponse = {
  ok: boolean;
  credited_efhc_operations_count: number;
  credited_efhc_total: string;
  credited_efhc_30d: string;
  credited_efhc_24h: string;
  generated_at?: string | null;
};
export const ADMIN_HUB_LINKS_PATH =
  "/admin/hub/links" as const;
export const ADMIN_HUB_LINKS_REORDER_PATH =
  "/admin/hub/links/reorder" as const;
export const ADMIN_HUB_LINKS_LINK_ID_PATH =
  "/admin/hub/links/{link_id}" as const;
export const ADMIN_HUB_LINKS_LINK_ID_TOGGLE_PATH =
  "/admin/hub/links/{link_id}/toggle" as const;
export const ADMIN_HUB_SUPPORT_LINKS_PATH =
  "/admin/hub/support-links" as const;
export const ADMIN_HUB_SUPPORT_LINKS_REORDER_PATH =
  "/admin/hub/support-links/reorder" as const;
export const ADMIN_HUB_SUPPORT_LINKS_LINK_ID_PATH =
  "/admin/hub/support-links/{link_id}" as const;
export const ADMIN_HUB_SUPPORT_LINKS_LINK_ID_TOGGLE_PATH =
  "/admin/hub/support-links/{link_id}/toggle" as const;
export const ADMIN_LOGS_TRANSFERS_PATH =
  "/admin/logs/transfers" as const;
export const ADMIN_LOGS_EXPORT_CSV_PATH =
  "/admin/logs/export.csv" as const;
export const ADMIN_LOGS_EXPORT_XLSX_PATH =
  "/admin/logs/export.xlsx" as const;
export const ADMIN_OBSERVABILITY_EVENTS_PATH =
  "/admin/observability/events" as const;
export const ADMIN_OBSERVABILITY_HEALTH_PATH =
  "/admin/observability/health" as const;
export const ADMIN_OBSERVABILITY_SUMMARY_PATH =
  "/admin/observability/summary" as const;
export const ADMIN_OBSERVABILITY_TIMESERIES_PATH =
  "/admin/observability/timeseries" as const;
export const ADMIN_PANELS_PATH =
  "/admin/panels/" as const;
export const ADMIN_PANELS_PANEL_ID_PATH =
  "/admin/panels/{panel_id}" as const;
export const ADMIN_PANELS_PANEL_ID_ACTIVATE_PATH =
  "/admin/panels/{panel_id}/activate" as const;
export const ADMIN_PANELS_PANEL_ID_DEACTIVATE_PATH =
  "/admin/panels/{panel_id}/deactivate" as const;
export const ADMIN_REFERRALS_SUMMARY_PATH =
  "/admin/referrals/summary" as const;
export const ADMIN_REFERRALS_LOGS_PATH =
  "/admin/referrals/logs" as const;
export const ADMIN_REPORTS_BANK_PATH =
  "/admin/reports/bank" as const;
export const ADMIN_REPORTS_DEPOSITS_PATH =
  "/admin/reports/deposits" as const;
export const ADMIN_REPORTS_OVERVIEW_PATH =
  "/admin/reports/overview" as const;
export const ADMIN_REPORTS_PANELS_PATH =
  "/admin/reports/panels" as const;
export const ADMIN_REPORTS_USERS_PATH =
  "/admin/reports/users" as const;
export const ADMIN_REPORTS_WITHDRAWALS_PATH =
  "/admin/reports/withdrawals" as const;
export const ADMIN_SALE_PACKAGES_PATH =
  "/admin/sale-packages/" as const;
export const ADMIN_SALE_PACKAGES_PACKAGE_ID_PATH =
  "/admin/sale-packages/{package_id}" as const;
export const ADMIN_SALE_PACKAGES_PACKAGE_ID_TOGGLE_PATH =
  "/admin/sale-packages/{package_id}/toggle" as const;
export const ADMIN_SHOP_ITEMS_PATH =
  "/admin/shop/items" as const;
export const ADMIN_SHOP_ITEMS_DELETE_PATH =
  "/admin/shop/items/delete" as const;
export const ADMIN_SHOP_ITEMS_SET_PRICE_PATH =
  "/admin/shop/items/set-price" as const;
export const ADMIN_SHOP_ITEMS_STATUS_PATH =
  "/admin/shop/items/status" as const;
export const ADMIN_SHOP_ITEMS_UPSERT_PATH =
  "/admin/shop/items/upsert" as const;
export const ADMIN_SHOP_ORDER_ORDER_ID_PATH =
  "/admin/shop/order/{order_id}" as const;
export const ADMIN_SHOP_ORDERS_PATH =
  "/admin/shop/orders" as const;
export const ADMIN_SHOP_ORDERS_STATUS_COUNTERS_PATH =
  "/admin/shop/orders/status-counters" as const;
export const ADMIN_SHOP_NFT_REQUESTS_PATH =
  "/admin/shop/nft-requests" as const;
export const ADMIN_SHOP_NFT_REQUESTS_ORDER_ID_DECISION_PATH =
  "/admin/shop/nft-requests/{order_id}/decision" as const;
export const ADMIN_SHOP_ORDERS_USER_GLOBAL_ID_PATH =
  "/admin/shop/orders/user/{global_id}" as const;
export const ADMIN_SHOP_ORDERS_ORDER_ID_FORCE_FULFILL_PATH =
  "/admin/shop/orders/{order_id}/force-fulfill" as const;
export const ADMIN_TASKS_PATH =
  "/admin/tasks/" as const;
export const ADMIN_TASKS_REFRESH_STATUSES_PATH =
  "/admin/tasks/refresh-statuses" as const;
export const ADMIN_TASKS_SUBMISSIONS_SUBMISSION_ID_MODERATE_PATH =
  "/admin/tasks/submissions/{submission_id}/moderate" as const;
export const ADMIN_TASKS_TASK_ID_PATH =
  "/admin/tasks/{task_id}" as const;
export const ADMIN_TASKS_TASK_ID_SUBS_PATH =
  "/admin/tasks/{task_id}/subs" as const;
export const ADMIN_TEMPLATES_PATH =
  "/admin/templates" as const;
export const ADMIN_TEMPLATES_KEY_PATH =
  "/admin/templates/{key}" as const;
export const ADMIN_TON_RECONCILE_PATH =
  "/admin/ton/reconcile" as const;
export const ADMIN_TRANSFER_PATH =
  "/admin/transfer" as const;
export const ADMIN_USERS_SEARCH_PATH =
  "/admin/users/search" as const;
export const ADMIN_USERS_RESOLVE_PROVIDER_PATH =
  "/admin/users/resolve-provider" as const;
export const ADMIN_USERS_GLOBAL_ID_PATH =
  "/admin/users/{global_id}" as const;
export const ADMIN_USERS_GLOBAL_ID_ACTIVE_PATH =
  "/admin/users/{global_id}/active" as const;
export const ADMIN_USERS_GLOBAL_ID_HISTORY_PATH =
  "/admin/users/{global_id}/history" as const;
export const ADMIN_USERS_GLOBAL_ID_PANELS_ACTIVATE_PATH =
  "/admin/users/{global_id}/panels/activate" as const;
export const ADMIN_USERS_GLOBAL_ID_VIP_PATH =
  "/admin/users/{global_id}/vip" as const;
export const ADMIN_USERS_GLOBAL_ID_VIP_CHECK_PATH =
  "/admin/users/{global_id}/vip/check" as const;
export const ADMIN_USERS_VIP_CHECK_ALL_PATH =
  "/admin/users/vip/check-all" as const;
export const ADMIN_USERS_GLOBAL_ID_WALLET_RESET_PATH =
  "/admin/users/{global_id}/wallet/reset" as const;
export const ADMIN_WITHDRAWALS_PATH =
  "/admin/withdrawals" as const;
export const ADMIN_WITHDRAWALS_REPAIR_CONSISTENCY_PATH =
  "/admin/withdrawals/repair-consistency" as const;
export const ADMIN_WITHDRAWALS_REQUEST_ID_APPROVE_PATH =
  "/admin/withdrawals/{request_id}/approve" as const;
export const ADMIN_WITHDRAWALS_REQUEST_ID_MARK_PAID_PATH =
  "/admin/withdrawals/{request_id}/mark-paid" as const;
export const ADMIN_WITHDRAWALS_REQUEST_ID_PAYOUT_EVIDENCE_PATH =
  "/admin/withdrawals/{request_id}/payout-evidence" as const;
export const ADMIN_WITHDRAWALS_REQUEST_ID_PAYOUT_RESERVE_PATH =
  "/admin/withdrawals/{request_id}/payout-reserve" as const;
export const ADMIN_WITHDRAWALS_REQUEST_ID_PAYOUT_RESERVATION_PATH =
  "/admin/withdrawals/{request_id}/payout-reservation" as const;
export const ADMIN_WITHDRAWALS_REQUEST_ID_OUTCOME_PREVIEW_PATH =
  "/admin/withdrawals/{request_id}/outcome-preview" as const;
export const ADMIN_WITHDRAWALS_REQUEST_ID_REJECT_PATH =
  "/admin/withdrawals/{request_id}/reject" as const;
export const ADMIN_WITHDRAW_APPROVE_PATH =
  ADMIN_WITHDRAWALS_REQUEST_ID_APPROVE_PATH;
export const ADMIN_WITHDRAW_REJECT_PATH =
  ADMIN_WITHDRAWALS_REQUEST_ID_REJECT_PATH;
export const ADMIN_WITHDRAW_OUTCOME_PREVIEW_PATH =
  ADMIN_WITHDRAWALS_REQUEST_ID_OUTCOME_PREVIEW_PATH;
export const ADMIN_HUB_LINK_CREATE_PATH = ADMIN_HUB_LINKS_PATH;
export const ADMIN_HUB_LINK_UPDATE_PATH = ADMIN_HUB_LINKS_LINK_ID_PATH;
export const ADMIN_HUB_LINK_TOGGLE_PATH =
  ADMIN_HUB_LINKS_LINK_ID_TOGGLE_PATH;
export const ADMIN_HUB_LINK_REORDER_PATH = ADMIN_HUB_LINKS_REORDER_PATH;
export const ADMIN_REFERRAL_SUMMARY_PATH = ADMIN_REFERRALS_SUMMARY_PATH;
export const ADMIN_REFERRAL_LOGS_PATH = ADMIN_REFERRALS_LOGS_PATH;

export type AdminReferralSummaryItem = {
  inviter_global_id: string;
  active_count: number;
  inactive_count: number;
  total_bonus_efhc: string;
  last_invited_at: string | null;
};

export type AdminReferralSummaryResponse = {
  items: AdminReferralSummaryItem[];
  next_cursor: string | null;
};

export type AdminReferralLogItem = {
  inviter_global_id: string;
  invitee_global_id: string;
  status: "active" | "inactive";
  invited_at: string;
  activated_at: string | null;
  reward_recorded: boolean;
};

export type AdminReferralLogResponse = {
  global_id: string;
  items: AdminReferralLogItem[];
  next_cursor: string | null;
};

export type AdminWithdrawalRecord = {
  id: DbId;
  global_id: string;
  amount_efhc: string;
  status: string;
  external_address: string | null;
  tx_hash: string | null;
  created_at: string;
  processed_at: string | null;
  error_message: string | null;
  is_vip: boolean;
  payout_asset: string;
  tonconnect_transport_kind: string | null;
  jetton_master_address: string | null;
  jetton_decimals: number | null;
  fee_message_ton_amount: string | null;
};

export type AdminWithdrawRepairOut = {
  ok: boolean;
  auto_fixed_hold: number;
  auto_fixed_refund: number;
};

export type AdminWithdrawPayoutReserveRequest = {
  sender_wallet_address?: string | null;
  wallet_provider?: string | null;
};

export type AdminWithdrawPayoutReservation = {
  ok: boolean;
  status: string;
  reserved: boolean;
  safe_to_send: boolean;
  recovered: boolean;
  request_id: DbId;
  idempotency_key?: string;
  payout_ref?: string;
  sender_wallet_address?: string;
  wallet_provider?: string | null;
  recipient_external_address?: string;
  amount_efhc?: string;
};

export type AdminWithdrawPayoutReservationResponse = {
  ok: boolean;
  result: AdminWithdrawPayoutReservation;
};

export type AdminBankMintBurnRequest = {
  amount: string;
  reason: string | null;
  idempotency_key: string;
};

export type AdminHubLink = {
  id: DbId;
  code: string;
  title: string;
  subtitle: string | null;
  url: string;
  target_kind: string;
  open_mode: string;
  sort_order: number;
  is_active: boolean;
  icon_key: string | null;
  created_at: string;
  updated_at: string;
};

export type AdminHubLinkCreateRequest = {
  code: string;
  title: string;
  subtitle: string | null;
  url: string;
  target_kind: string;
  open_mode: string;
  sort_order: number;
  is_active: boolean;
  icon_key: string | null;
};

export type AdminHubLinkUpdateRequest = {
  title: string;
  subtitle: string | null;
  url: string;
  target_kind: string;
  open_mode: string;
  sort_order: number;
  is_active: boolean;
  icon_key: string | null;
};

export type AdminHubLinkToggleRequest = {
  is_active: boolean;
};

export type AdminHubLinkReorderItem = {
  id: DbId;
  sort_order: number;
};

export type AdminHubLinkReorderRequest = {
  items: AdminHubLinkReorderItem[];
};

export type AdminBankBalanceResponse = {
  bank_name: string;
  efhc_main: string;
};

export type AdminBankMutationResponse = {
  ok: boolean;
  bank_balance_after: string;
};

export type AdminWithdrawApproveRequest = {
  tx_hash?: string | null;
  payout_ref?: string | null;
  wallet_send_confirmed?: boolean;
  wallet_provider?: string | null;
  sender_wallet_address?: string | null;
  confirmation_mode?: "wallet_send" | "manual" | null;
  reason?: string | null;
  comment_override?: string | null;
  comment_auto_translated?: boolean;
};

export type AdminWithdrawRejectRequest = {
  reason: string;
  comment_override?: string | null;
  comment_auto_translated?: boolean;
};

export type AdminWithdrawActionResponse = {
  ok: boolean;
  result: unknown;
};

export type AdminWithdrawOutcomeComment = {
  text: string;
  template_key?: string | null;
  source: string;
  locale: string;
  manual_override_used?: boolean;
  auto_translated?: boolean;
};

export type AdminWithdrawOutcomePromo = {
  enabled: boolean;
  key?: string | null;
  title?: string | null;
  body?: string | null;
  cta_label?: string | null;
  cta_url?: string | null;
  source?: string | null;
};

export type AdminWithdrawOutcomeBundle = {
  request_id: DbId;
  global_id: string;
  outcome_kind: string;
  locale: string;
  comment: AdminWithdrawOutcomeComment;
  promo?: AdminWithdrawOutcomePromo | null;
  top_zone_enabled: boolean;
  metadata: Record<string, unknown>;
};

export type AdminWithdrawOutcomePreviewResponse = {
  request_id: DbId;
  withdrawal_status: string;
  preview_mode: string;
  bundle: AdminWithdrawOutcomeBundle;
};

export type AdminDomainReportTrendPoint = {
  bucket: string;
  value: number;
};

export type AdminBankPolicy = {
  system_entity: 'BANK_EFHC';
  balance_key: 'EFHC_MAIN';
  initial_balance: string;
  negative_balance_allowed: boolean;
  p2p_allowed: boolean;
  bank_global_id: null;
  bank_tg_id: null;
  user_owner: 'global_id';
};

export type AdminDomainReportResponse = {
  ok: boolean;
  data_kind: 'real_timeseries';
  synthetic: boolean;
  domain: string;
  range_hours: number;
  generated_at: string;
  snapshot: Record<string, string | number>;
  policy?: AdminBankPolicy | null;
  trend: AdminDomainReportTrendPoint[];
  empty_reason: string | null;
};

export type AdminObservabilitySeriesPoint = {
  ts: string;
  value: string;
  label?: string | null;
};

export type AdminObservabilityTimeseriesResponse = {
  ok: boolean;
  data_kind: 'real_timeseries';
  synthetic: boolean;
  metric:
    | 'users_created'
    | 'panels_created'
    | 'withdrawals_created'
    | 'payment_intents_created'
    | 'efhc_transfer_count'
    | 'efhc_transfer_amount'
    | 'efhc_credit_amount'
    | 'efhc_debit_amount';
  bucket: 'hour' | 'day';
  range_hours: number;
  unit: string;
  source: string;
  points: AdminObservabilitySeriesPoint[];
  empty_reason?: string | null;
};

export type AdminObservabilitySummaryMetric = {
  key: string;
  label: string;
  value: string;
  unit: string;
  source: string;
  data_kind: 'raw' | 'derived';
};

export type AdminObservabilitySummaryResponse = {
  ok: boolean;
  data_kind: 'raw' | 'derived';
  generated_at: string;
  source: string;
  metrics: AdminObservabilitySummaryMetric[];
};

export type AdminObservabilityEvent = {
  id: string;
  type: string;
  severity: 'info' | 'success' | 'warning' | 'danger';
  title: string;
  description?: string | null;
  ts: string;
  route?: string | null;
  source: string;
};

export type AdminObservabilityEventsResponse = {
  ok: boolean;
  data_kind: 'disabled_duplicate';
  status: 'disabled_duplicate';
  source: string;
  reason: string;
  replacement: string;
  items: AdminObservabilityEvent[];
};

