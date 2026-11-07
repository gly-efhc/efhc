// AUTO-GENERATED FILE. DO NOT EDIT MANUALLY.
// Source: ops/openapi/generate_frontend_user_economic_seams.py

import type { DbId } from "../../../types/db-id";

export const EXCHANGE_PREVIEW_PATH =
  "/exchange/preview" as const;
export const EXCHANGE_CONVERT_PATH =
  "/exchange/convert" as const;
export const WITHDRAW_LIST_PATH = "/withdraw/list" as const;
export const WITHDRAW_REQUEST_PATH = "/withdraw/request" as const;
export const WITHDRAW_DETAIL_PATH = "/withdraw/{request_id}" as const;
export const WITHDRAW_CANCEL_PATH =
  "/withdraw/{request_id}/cancel" as const;
export const PANELS_ACTIVE_PATH = "/panels/active" as const;
export const PANELS_ARCHIVE_PATH = "/panels/archive" as const;
export const PANELS_ACTIVATE_PATH = "/panels/activate" as const;
export const PANELS_SUMMARY_PATH =
  "/user/me/panels-summary" as const;

export type PanelItemResponse = {
  id: DbId;
  public_id: string;
  activated_at?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  archived_at?: string | null;
  remaining_seconds?: number | null;
  base_gen_per_sec: string;
  generated_kwh: string;
  is_active: boolean;
};

export type PanelsPageResponse = {
  items: PanelItemResponse[];
  next_cursor: string | null;
  server_now_utc: string;
};

export type PanelsSummaryResponse = {
  active_count: number;
  total_generated_by_panels: string;
  nearest_expire_at?: string | null;
};

export type PanelActivationResponse = {
  panel: {
    id: DbId;
    public_id: string;
    activated_at: string;
    expires_at: string;
  };
  server_now_utc: string;
};
export const SHOPFRONT_ACCESS_KEY_PATH =
  "/shopfront/access-key" as const;
export const HUB_SHOP_TRUTH_PATH = "/hub/shop-truth" as const;
export const SHOPFRONT_PROFILE_PATH = "/shopfront/profile" as const;
export const SHOPFRONT_BOOTSTRAP_PATH = "/shopfront/bootstrap" as const;
export const SHOPFRONT_CATALOG_PATH = "/shopfront/catalog" as const;
export const SHOPFRONT_CREATE_INTENT_PATH =
  "/shopfront/create-intent" as const;
export const SHOPFRONT_INTENT_STATUS_PATH =
  "/shopfront/intent-status" as const;

export type ExchangePreviewResponse = {
  ok: boolean;
  available_kwh: string;
  max_exchangeable_kwh: string;
  rate_kwh_to_efhc: string;
  detail: string;
};

export type ExchangeConvertRequest = {
  amount_kwh?: string;
};

export type ExchangeConvertResponse = {
  ok: boolean;
  exchanged_kwh: string;
  credited_efhc: string;
  new_available_kwh: string;
  new__main__balance: string;
  log_id?: DbId | null;
  detail: string;
};

export type WithdrawRequestCreate = {
  amount: string;
  wallet_id?: DbId | null;
};

export type WithdrawItem = {
  id: DbId;
  global_id: string;
  amount: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type WithdrawDetail = WithdrawItem & {
  idempotency_key: string;
  hold_done: boolean;
  refund_done: boolean;
  payout_ref?: string | null;
  wallet_address?: string | null;
};

export type WithdrawPageResponse = {
  items: WithdrawItem[];
  next_cursor: string | null;
};

export type ShopfrontAccessResponse = {
  redirect_url: string;
  expires_at: string;
  transport: "external_url";
  mode: "signed_token";
};


export type BrowserShopActiveIntent = {
  intent_id: DbId;
  purpose: string;
  asset: string;
  amount_asset_d8: string;
  external_amount_atomic?: string | null;
  external_decimals?: number | null;
  external_amount_display?: string | null;
  efhc_amount_d8?: string | null;
  status: string;
  payload: string;
  to_address: string;
  order_id?: DbId | null;
  order_status?: string | null;
  created_at: string;
  expires_at: string;
  flow_truth?: PaymentIntentFlowTruth | null;
};

export type BrowserShopFlowTruth = {
  handoff_configured: boolean;
  handoff_mode: "connected" | "missing_config";
  wallet_linked: boolean;
  wallet_sync_required: boolean;
  wallet_ready: boolean;
  wallet_blocked: boolean;
  action_allowed: boolean;
  action_denied: boolean;
  readiness_state: string;
  primary_cta: string;
  active_intent?: BrowserShopActiveIntent | null;
  active_order_id?: DbId | null;
  active_order_status?: string | null;
  product_state: string;
  next_action: string;
  return_path: string;
  canonical_center: string;
  next_step:
    | "connect_handoff"
    | "sync_wallet"
    | "resume_intent"
    | "create_intent";
  blocker_codes: string[];
  browser_shop_path: string;
  truth_label: "shop_hub_truth_layer";
};

export type HubShopTruthResponse = {
  handoff_configured: boolean;
  handoff_mode: "connected" | "missing_config";
  wallet_linked: boolean;
  wallet_sync_required: boolean;
  active_wallet_address?: string | null;
  bot_open_url: string | null;
  telegram_sync_url: string | null;
  wallet_sync_url: string | null;
  flow_truth: BrowserShopFlowTruth;
};

export type BrowserShopProfileWallet = {
  id: DbId;
  wallet_address: string;
  wallet_app: string | null;
  is_primary: boolean;
  is_active: boolean;
  proof_verified: boolean;
  created_at: string;
};

export type BrowserShopProfileOrder = {
  id: DbId;
  type: string;
  sku: string;
  quantity: number;
  status: string;
  global_id: string;
  tx_hash?: string | null;
  payment_method?: string | null;
  expected_amount?: string | null;
  paid_at?: string | null;
  debited_bonus_efhc?: string | null;
  debited__main__efhc?: string | null;
  idempotency_key?: string | null;
  created_at: string;
  updated_at: string;
};

export type PaymentIntentFlowTruth = {
  lifecycle_stage: string;
  product_state: string;
  lifecycle_terminal: boolean;
  next_step: string;
  next_action: string;
  return_path: string;
  canonical_center: string;
  message_key: string;
  watcher_status?: string | null;
  watcher_tx_hash?: string | null;
  watcher_last_error?: string | null;
  order_id?: DbId | null;
  order_status?: string | null;
  payment_error_log?: string | null;
};

export type OutcomeComment = {
  text: string;
  template_key?: string | null;
  source: string;
  locale: string;
  manual_override_used?: boolean;
  auto_translated?: boolean;
};

export type OutcomePromo = {
  enabled: boolean;
  key?: string | null;
  title?: string | null;
  body?: string | null;
  cta_label?: string | null;
  cta_url?: string | null;
  source?: string | null;
};

export type WithdrawOutcomeBundle = {
  request_id: DbId;
  global_id: string;
  outcome_kind: string;
  locale: string;
  comment: OutcomeComment;
  promo?: OutcomePromo | null;
  top_zone_enabled: boolean;
  metadata: Record<string, unknown>;
};

export type BrowserShopProfileResponse = {
  global_id: string;
  wallets: BrowserShopProfileWallet[];
  orders: BrowserShopProfileOrder[];
  access_mode: "telegram_handoff";
  profile_mode: "web_profile";
  bot_open_url: string | null;
  wallet_sync_url: string | null;
  telegram_sync_url: string | null;
  flow_truth?: BrowserShopFlowTruth | null;
  active_payment?: PaymentIntentStatusResponse | null;
  intent_history: PaymentIntentStatusResponse[];
  latest_withdraw_request_id?: DbId | null;
  latest_withdraw_status?: string | null;
  latest_withdraw_outcome?: WithdrawOutcomeBundle | null;
};

export type BrowserShopBootstrapWallet = {
  id: DbId;
  wallet_address: string;
  wallet_app: string | null;
  is_primary: boolean;
  is_active: boolean;
  created_at: string;
};

export type BrowserShopBootstrapResponse = {
  mode: "guest" | "handoff_bound";
  tg_linked: boolean;
  global_id?: string | null;
  wallet_linked: boolean;
  active_wallet_address: string | null;
  wallets: BrowserShopBootstrapWallet[];
  wallet_sync_required: boolean;
  bot_open_url: string | null;
  telegram_sync_url: string | null;
  wallet_sync_url: string | null;
  storefront_mode: "browser_shop_mvp";
  access_mode: "telegram_handoff";
  future_game_entry_enabled: boolean;
  available_modules: string[];
  usdt_checkout_mode?: string;
  flow_truth?: BrowserShopFlowTruth | null;
  active_payment?: PaymentIntentStatusResponse | null;
  intent_history: PaymentIntentStatusResponse[];
};

export type BrowserShopCatalogMethod = {
  price?: string;
};

export type BrowserShopCatalogItem = {
  sku: string;
  title: string;
  description: string | null;
  translations?: Record<string, { title?: string; description?: string }>;
  item_type: string;
  ton_enabled: boolean;
  usdt_enabled: boolean;
  methods: Record<string, BrowserShopCatalogMethod> | null;
  image_url?: string | null;
  category?: string;
  badge?: string;
  status?: string;
  action_mode?: string;
  external_url?: string | null;
  delivery_mode?: string;
  quantity_efhc?: string | null;
  sort_order?: number;
};

export type BrowserShopCatalogResponse = {
  items: BrowserShopCatalogItem[];
};

export type BrowserShopCreateIntentRequest = {
  token?: string | null;
  sku: string;
  quantity: number;
  pay_method: string;
  custom_efhc_amount_d8?: string | null;
  client_nonce?: string | null;
};

export type BrowserShopCreateIntentResponse = {
  global_id: string;
  intent_id: DbId;
  order_id: DbId;
  item_type: string;
  pay_method: string;
  amount: string;
  external_amount_atomic: string;
  external_decimals: number;
  external_amount_display: string;
  memo: string;
  to_wallet: string;
  tonconnect_tx?: Record<string, unknown> | null;
  tonconnect_transport_kind?: string | null;
  jetton_master_address?: string | null;
  jetton_decimals?: number | null;
  forward_payload_text?: string | null;
  fee_message_ton_amount?: string | null;
  forward_ton_amount?: string | null;
  recipient_strategy?: string | null;
  usdt_checkout_mode?: string | null;
  expires_at: string;
};

export type PaymentIntentStatusResponse = {
  id: DbId;
  purpose: string;
  asset: string;
  amount_asset_d8: string;
  external_amount_atomic?: string | null;
  external_decimals?: number | null;
  external_amount_display?: string | null;
  efhc_amount_d8?: string | null;
  status: string;
  payload: string;
  to_address: string;
  external_tx_hash?: string | null;
  tonconnect_transport_kind?: string | null;
  jetton_master_address?: string | null;
  jetton_decimals?: number | null;
  forward_payload_text?: string | null;
  fee_message_ton_amount?: string | null;
  forward_ton_amount?: string | null;
  recipient_strategy?: string | null;
  usdt_checkout_mode?: string | null;
  flow_truth?: PaymentIntentFlowTruth | null;
  created_at: string;
  expires_at: string;
};
