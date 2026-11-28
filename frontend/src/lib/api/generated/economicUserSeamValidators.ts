// AUTO-GENERATED FILE. DO NOT EDIT MANUALLY.
// Source: ops/openapi/generate_frontend_user_economic_validators.py

import { z } from "zod";
import { dbIdSchema } from "../db-id";

export const PanelPublicIdSchema = z.string().regex(/^PNL-(?!00000000$)[0-9]{8}$/);

export const PanelItemResponseSchema = z.object({
  id: dbIdSchema,
  public_id: PanelPublicIdSchema,
  activated_at: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  expires_at: z.string().nullable().optional(),
  archived_at: z.string().nullable().optional(),
  remaining_seconds: z.number().nullable().optional(),
  base_gen_per_sec: z.string(),
  generated_kwh: z.string(),
  is_active: z.boolean(),
});

export const PanelsPageResponseSchema = z.object({
  items: z.array(PanelItemResponseSchema),
  next_cursor: z.string().nullable(),
  server_now_utc: z.string(),
});

export const PanelsSummaryResponseSchema = z.object({
  active_count: z.number().int().nonnegative(),
  total_generated_by_panels: z.string(),
  nearest_expire_at: z.string().nullable().optional(),
});

export const PanelActivationResponseSchema = z.object({
  panel: z.object({
    id: dbIdSchema,
    public_id: PanelPublicIdSchema,
    activated_at: z.string(),
    expires_at: z.string(),
  }),
  server_now_utc: z.string(),
});

export const ExchangePreviewResponseSchema = z.object({
  ok: z.boolean(),
  available_kwh: z.string(),
  max_exchangeable_kwh: z.string(),
  rate_kwh_to_efhc: z.string(),
  detail: z.string(),
});

export const ExchangeConvertRequestSchema = z.object({
  amount_kwh: z.string().min(1).optional(),
});

export const ExchangeConvertResponseSchema = z.object({
  ok: z.boolean(),
  exchanged_kwh: z.string(),
  credited_efhc: z.string(),
  new_available_kwh: z.string(),
  new__main__balance: z.string(),
  log_id: dbIdSchema.nullable().optional(),
  detail: z.string(),
});

export const WithdrawRequestCreateSchema = z.object({
  amount: z.string().min(1),
  wallet_id: dbIdSchema.nullable().optional(),
});

export const WithdrawItemSchema = z.object({
  id: dbIdSchema,
  global_id: z.string().regex(/^[0-9]{10}$/),
  amount: z.string(),
  status: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const WithdrawDetailSchema = WithdrawItemSchema.extend({
  idempotency_key: z.string(),
  hold_done: z.boolean(),
  refund_done: z.boolean(),
  payout_ref: z.string().nullable().optional(),
  wallet_address: z.string().nullable().optional(),
});

export const WithdrawPageResponseSchema = z.object({
  items: z.array(WithdrawItemSchema),
  next_cursor: z.string().nullable(),
});

export const ShopfrontAccessResponseSchema = z.object({
  redirect_url: z.string(),
  expires_at: z.string(),
  transport: z.literal("external_url"),
  mode: z.literal("signed_token"),
});


export const PaymentIntentFlowTruthSchema = z.object({
  lifecycle_stage: z.string(),
  product_state: z.string(),
  lifecycle_terminal: z.boolean(),
  next_step: z.string(),
  next_action: z.string(),
  return_path: z.string(),
  canonical_center: z.string(),
  message_key: z.string(),
  watcher_status: z.string().nullable().optional(),
  watcher_tx_hash: z.string().nullable().optional(),
  watcher_last_error: z.string().nullable().optional(),
  order_id: dbIdSchema.nullable().optional(),
  order_status: z.string().nullable().optional(),
  payment_error_log: z.string().nullable().optional(),
});

export const BrowserShopProfileResponseSchema = z.object({
  global_id: z.string().regex(/^[0-9]{10}$/),
  wallets: z.array(z.lazy(() => BrowserShopProfileWalletSchema)),
  orders: z.array(z.lazy(() => BrowserShopProfileOrderSchema)),
  access_mode: z.literal("telegram_handoff"),
  profile_mode: z.literal("web_profile"),
  bot_open_url: z.string().nullable(),
  wallet_sync_url: z.string().nullable(),
  telegram_sync_url: z.string().nullable(),
  flow_truth: z.lazy(
    () => BrowserShopFlowTruthSchema,
  ).nullable().optional(),
  active_payment: z.lazy(() => PaymentIntentStatusResponseSchema)
    .nullable()
    .optional(),
  intent_history: z.array(
    z.lazy(() => PaymentIntentStatusResponseSchema),
  ),
  latest_withdraw_request_id: dbIdSchema.nullable().optional(),
  latest_withdraw_status: z.string().nullable().optional(),
  latest_withdraw_outcome: z.lazy(() => WithdrawOutcomeBundleSchema)
    .nullable()
    .optional(),
});

export const BrowserShopBootstrapWalletSchema = z.object({
  id: dbIdSchema,
  wallet_address: z.string(),
  wallet_app: z.string().nullable(),
  is_primary: z.boolean(),
  is_active: z.boolean(),
  created_at: z.string(),
});

export const BrowserShopBootstrapResponseSchema = z.object({
  mode: z.union([z.literal("guest"), z.literal("handoff_bound")]),
  tg_linked: z.boolean(),
  global_id: z.string().regex(/^[0-9]{10}$/).nullable().optional(),
  wallet_linked: z.boolean(),
  active_wallet_address: z.string().nullable(),
  wallets: z.array(BrowserShopBootstrapWalletSchema),
  wallet_sync_required: z.boolean(),
  bot_open_url: z.string().nullable(),
  telegram_sync_url: z.string().nullable(),
  wallet_sync_url: z.string().nullable(),
  storefront_mode: z.literal("browser_shop_mvp"),
  access_mode: z.literal("telegram_handoff"),
  future_game_entry_enabled: z.boolean(),
  available_modules: z.array(z.string()),
  usdt_checkout_mode: z.string().optional(),
  flow_truth: z.lazy(
    () => BrowserShopFlowTruthSchema,
  ).nullable().optional(),
  active_payment: z.lazy(() => PaymentIntentStatusResponseSchema)
    .nullable()
    .optional(),
  intent_history: z.array(
    z.lazy(() => PaymentIntentStatusResponseSchema),
  ),
});

export const BrowserShopCatalogMethodSchema = z.object({
  price: z.string().optional(),
});

export const BrowserShopCatalogItemSchema = z.object({
  sku: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  translations: z.record(z.string(), z.object({ title: z.string().optional(), description: z.string().optional() })).optional(),
  item_type: z.string(),
  ton_enabled: z.boolean(),
  usdt_enabled: z.boolean(),
  methods: z.record(z.string(), BrowserShopCatalogMethodSchema).nullable(),
  image_url: z.string().nullable().optional(),
  category: z.string().optional(),
  badge: z.string().optional(),
  status: z.string().optional(),
  action_mode: z.string().optional(),
  external_url: z.string().nullable().optional(),
  delivery_mode: z.string().optional(),
  quantity_efhc: z.string().nullable().optional(),
  sort_order: z.number().optional(),
});

export const BrowserShopCatalogResponseSchema = z.object({
  items: z.array(BrowserShopCatalogItemSchema),
});

export const BrowserShopCreateIntentRequestSchema = z.object({
  token: z.string().min(1).nullable().optional(),
  sku: z.string().min(1),
  quantity: z.number().int().min(1),
  pay_method: z.string().min(1),
  custom_efhc_amount_d8: z.string().min(1).nullable().optional(),
  client_nonce: z.string().min(1).nullable().optional(),
});

export const BrowserShopCreateIntentResponseSchema = z.object({
  global_id: z.string().regex(/^[0-9]{10}$/),
  intent_id: dbIdSchema,
  order_id: dbIdSchema,
  item_type: z.string(),
  pay_method: z.string(),
  amount: z.string(),
  external_amount_atomic: z.string().regex(/^\d+$/),
  external_decimals: z.number().int().nonnegative(),
  external_amount_display: z.string(),
  memo: z.string(),
  to_wallet: z.string(),
  tonconnect_tx: z.record(z.string(), z.unknown()).nullable().optional(),
  tonconnect_transport_kind: z.string().nullable().optional(),
  jetton_master_address: z.string().nullable().optional(),
  jetton_decimals: z.number().nullable().optional(),
  forward_payload_text: z.string().nullable().optional(),
  fee_message_ton_amount: z.string().nullable().optional(),
  forward_ton_amount: z.string().nullable().optional(),
  recipient_strategy: z.string().nullable().optional(),
  usdt_checkout_mode: z.string().nullable().optional(),
  expires_at: z.string(),
});

export const OutcomeCommentSchema = z.object({
  text: z.string(),
  template_key: z.string().nullable().optional(),
  source: z.string(),
  locale: z.string(),
  manual_override_used: z.boolean().optional(),
  auto_translated: z.boolean().optional(),
});

export const OutcomePromoSchema = z.object({
  enabled: z.boolean(),
  key: z.string().nullable().optional(),
  title: z.string().nullable().optional(),
  body: z.string().nullable().optional(),
  cta_label: z.string().nullable().optional(),
  cta_url: z.string().nullable().optional(),
  source: z.string().nullable().optional(),
});

export const WithdrawOutcomeBundleSchema = z.object({
  request_id: dbIdSchema,
  global_id: z.string().regex(/^[0-9]{10}$/),
  outcome_kind: z.string(),
  locale: z.string(),
  comment: OutcomeCommentSchema,
  promo: OutcomePromoSchema.nullable().optional(),
  top_zone_enabled: z.boolean(),
  metadata: z.record(z.string(), z.unknown()),
});

export const BrowserShopActiveIntentSchema = z.object({
  intent_id: dbIdSchema,
  purpose: z.string(),
  asset: z.string(),
  amount_asset_d8: z.string(),
  external_amount_atomic: z.string().nullable().optional(),
  external_decimals: z.number().int().nonnegative().nullable().optional(),
  external_amount_display: z.string().nullable().optional(),
  efhc_amount_d8: z.string().nullable().optional(),
  status: z.string(),
  payload: z.string(),
  to_address: z.string(),
  order_id: dbIdSchema.nullable().optional(),
  order_status: z.string().nullable().optional(),
  created_at: z.string(),
  expires_at: z.string(),
  flow_truth: PaymentIntentFlowTruthSchema.nullable().optional(),
});

export const BrowserShopFlowTruthSchema = z.object({
  handoff_configured: z.boolean(),
  handoff_mode: z.union([
    z.literal("connected"),
    z.literal("missing_config"),
  ]),
  wallet_linked: z.boolean(),
  wallet_sync_required: z.boolean(),
  wallet_ready: z.boolean(),
  wallet_blocked: z.boolean(),
  action_allowed: z.boolean(),
  action_denied: z.boolean(),
  readiness_state: z.string(),
  primary_cta: z.string(),
  active_intent: BrowserShopActiveIntentSchema.nullable().optional(),
  active_order_id: dbIdSchema.nullable().optional(),
  active_order_status: z.string().nullable().optional(),
  product_state: z.string(),
  next_action: z.string(),
  return_path: z.string(),
  canonical_center: z.string(),
  next_step: z.union([
    z.literal("connect_handoff"),
    z.literal("sync_wallet"),
    z.literal("resume_intent"),
    z.literal("create_intent"),
  ]),
  blocker_codes: z.array(z.string()),
  browser_shop_path: z.string(),
  truth_label: z.literal("shop_hub_truth_layer"),
});

export const HubShopTruthResponseSchema = z.object({
  handoff_configured: z.boolean(),
  handoff_mode: z.union([
    z.literal("connected"),
    z.literal("missing_config"),
  ]),
  wallet_linked: z.boolean(),
  wallet_sync_required: z.boolean(),
  active_wallet_address: z.string().nullable().optional(),
  bot_open_url: z.string().nullable(),
  telegram_sync_url: z.string().nullable(),
  wallet_sync_url: z.string().nullable(),
  flow_truth: BrowserShopFlowTruthSchema,
});

export const BrowserShopProfileWalletSchema = z.object({
  id: dbIdSchema,
  wallet_address: z.string(),
  wallet_app: z.string().nullable(),
  is_primary: z.boolean(),
  is_active: z.boolean(),
  proof_verified: z.boolean(),
  created_at: z.string(),
});

export const BrowserShopProfileOrderSchema = z.object({
  id: dbIdSchema,
  type: z.string(),
  sku: z.string(),
  quantity: z.number(),
  status: z.string(),
  global_id: z.string().regex(/^[0-9]{10}$/),
  tx_hash: z.string().nullable().optional(),
  payment_method: z.string().nullable().optional(),
  expected_amount: z.string().nullable().optional(),
  paid_at: z.string().nullable().optional(),
  debited_bonus_efhc: z.string().nullable().optional(),
  debited__main__efhc: z.string().nullable().optional(),
  idempotency_key: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const PaymentIntentStatusResponseSchema = z.object({
  id: dbIdSchema,
  purpose: z.string(),
  asset: z.string(),
  amount_asset_d8: z.string(),
  external_amount_atomic: z.string().nullable().optional(),
  external_decimals: z.number().int().nonnegative().nullable().optional(),
  external_amount_display: z.string().nullable().optional(),
  efhc_amount_d8: z.string().nullable().optional(),
  status: z.string(),
  payload: z.string(),
  to_address: z.string(),
  external_tx_hash: z.string().nullable().optional(),
  tonconnect_transport_kind: z.string().nullable().optional(),
  jetton_master_address: z.string().nullable().optional(),
  jetton_decimals: z.number().nullable().optional(),
  forward_payload_text: z.string().nullable().optional(),
  fee_message_ton_amount: z.string().nullable().optional(),
  forward_ton_amount: z.string().nullable().optional(),
  recipient_strategy: z.string().nullable().optional(),
  usdt_checkout_mode: z.string().nullable().optional(),
  created_at: z.string(),
  expires_at: z.string(),
  flow_truth: PaymentIntentFlowTruthSchema.nullable().optional(),
});

export function parsePanelsPageResponse(value: unknown) {
  return PanelsPageResponseSchema.parse(value);
}

export function parsePanelsSummaryResponse(value: unknown) {
  return PanelsSummaryResponseSchema.parse(value);
}

export function parsePanelActivationResponse(value: unknown) {
  return PanelActivationResponseSchema.parse(value);
}

export function parseExchangePreviewResponse(value: unknown) {
  return ExchangePreviewResponseSchema.parse(value);
}

export function ensureExchangeConvertRequest(value: unknown) {
  return ExchangeConvertRequestSchema.parse(value);
}

export function parseExchangeConvertResponse(value: unknown) {
  return ExchangeConvertResponseSchema.parse(value);
}

export function ensureWithdrawRequestCreate(value: unknown) {
  return WithdrawRequestCreateSchema.parse(value);
}

export function parseWithdrawDetail(value: unknown) {
  return WithdrawDetailSchema.parse(value);
}

export function parseWithdrawPageResponse(value: unknown) {
  return WithdrawPageResponseSchema.parse(value);
}
export function parseWithdrawOutcomeBundle(value: unknown) {
  return WithdrawOutcomeBundleSchema.parse(value);
}


export function parseShopfrontAccessResponse(value: unknown) {
  return ShopfrontAccessResponseSchema.parse(value);
}

export function parseBrowserShopProfileResponse(value: unknown) {
  return BrowserShopProfileResponseSchema.parse(value);
}

export function parseBrowserShopBootstrapResponse(value: unknown) {
  return BrowserShopBootstrapResponseSchema.parse(value);
}

export function parseBrowserShopCatalogResponse(value: unknown) {
  return BrowserShopCatalogResponseSchema.parse(value);
}

export function ensureBrowserShopCreateIntentRequest(value: unknown) {
  return BrowserShopCreateIntentRequestSchema.parse(value);
}

export function parseBrowserShopCreateIntentResponse(value: unknown) {
  return BrowserShopCreateIntentResponseSchema.parse(value);
}

export function parsePaymentIntentStatusResponse(value: unknown) {
  return PaymentIntentStatusResponseSchema.parse(value);
}

export function parseHubShopTruthResponse(value: unknown) {
  return HubShopTruthResponseSchema.parse(value);
}
