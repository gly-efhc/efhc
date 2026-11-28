// AUTO-GENERATED FILE. DO NOT EDIT MANUALLY.
// Checked-in generated contract artifact; historical generator removed from current HEAD.

import { z } from "zod";
import { dbIdSchema } from "../db-id";

export const AdminBankBalanceResponseSchema = z.object({
  bank_name: z.string(),
  efhc_main: z.string(),
});

export const AdminBankMutationRequestSchema = z.object({
  amount: z.string().min(1),
  reason: z.string(),
});

export const AdminBankMutationResponseSchema = z.object({
  ok: z.boolean(),
  bank_balance_after: z.string(),
});

export const AdminWithdrawalRecordSchema = z.object({
  id: dbIdSchema,
  global_id: z.string().regex(/^\d{10}$/),
  amount_efhc: z.string(),
  status: z.string(),
  external_address: z.string().nullable(),
  tx_hash: z.string().nullable(),
  created_at: z.string(),
  processed_at: z.string().nullable(),
  error_message: z.string().nullable(),
  is_vip: z.boolean(),
  payout_asset: z.string(),
  tonconnect_transport_kind: z.string().nullable(),
  jetton_master_address: z.string().nullable(),
  jetton_decimals: z.number().nullable(),
  fee_message_ton_amount: z.string().nullable(),
});

export const AdminWithdrawalListResponseSchema = z.array(
  AdminWithdrawalRecordSchema,
);

export const AdminWithdrawApproveRequestSchema = z.object({
  tx_hash: z.string().nullable().optional(),
  payout_ref: z.string().nullable().optional(),
  wallet_send_confirmed: z.boolean().optional(),
  wallet_provider: z.string().nullable().optional(),
  sender_wallet_address: z.string().nullable().optional(),
  confirmation_mode: z.enum(["wallet_send", "manual"]).nullable().optional(),
  reason: z.string().max(500).nullable().optional(),
  comment_override: z.string().nullable().optional(),
  comment_auto_translated: z.boolean().optional(),
}).strict();

export const AdminWithdrawPayoutReserveRequestSchema = z.object({
  sender_wallet_address: z.string().nullable().optional(),
  wallet_provider: z.string().nullable().optional(),
}).strict();

export const AdminWithdrawPayoutReservationSchema = z.object({
  ok: z.boolean(),
  status: z.string(),
  reserved: z.boolean(),
  safe_to_send: z.boolean(),
  recovered: z.boolean(),
  request_id: dbIdSchema,
  idempotency_key: z.string().optional(),
  payout_ref: z.string().optional(),
  sender_wallet_address: z.string().optional(),
  wallet_provider: z.string().nullable().optional(),
  recipient_external_address: z.string().optional(),
  amount_efhc: z.string().optional(),
});

export const AdminWithdrawPayoutReservationResponseSchema = z.object({
  ok: z.boolean(),
  result: AdminWithdrawPayoutReservationSchema,
});

export const AdminWithdrawRejectRequestSchema = z.object({
  reason: z.string().min(1).max(500),
  comment_override: z.string().nullable().optional(),
  comment_auto_translated: z.boolean().optional(),
});

export const AdminWithdrawActionResponseSchema = z.object({
  ok: z.boolean(),
  result: z.unknown(),
});

export const AdminWithdrawOutcomeCommentSchema = z.object({
  text: z.string(),
  template_key: z.string().nullable().optional(),
  source: z.string(),
  locale: z.string(),
  manual_override_used: z.boolean().optional(),
  auto_translated: z.boolean().optional(),
});

export const AdminWithdrawOutcomePromoSchema = z.object({
  enabled: z.boolean(),
  key: z.string().nullable().optional(),
  title: z.string().nullable().optional(),
  body: z.string().nullable().optional(),
  cta_label: z.string().nullable().optional(),
  cta_url: z.string().nullable().optional(),
  source: z.string().nullable().optional(),
});

export const AdminWithdrawOutcomeBundleSchema = z.object({
  request_id: dbIdSchema,
  global_id: z.string().regex(/^\d{10}$/),
  outcome_kind: z.string(),
  locale: z.string(),
  comment: AdminWithdrawOutcomeCommentSchema,
  promo: AdminWithdrawOutcomePromoSchema.nullable().optional(),
  top_zone_enabled: z.boolean(),
  metadata: z.record(z.string(), z.unknown()),
});

export const AdminWithdrawOutcomePreviewResponseSchema = z.object({
  request_id: dbIdSchema,
  withdrawal_status: z.string(),
  preview_mode: z.string(),
  bundle: AdminWithdrawOutcomeBundleSchema,
});

export const AdminReferralSummaryItemSchema = z.object({
  inviter_global_id: z.string().regex(/^\d{10}$/),
  active_count: z.number(),
  inactive_count: z.number(),
  total_bonus_efhc: z.string(),
  last_invited_at: z.string().nullable(),
});

export const AdminReferralSummaryResponseSchema = z.object({
  items: z.array(AdminReferralSummaryItemSchema),
  next_cursor: z.string().nullable(),
});

export const AdminReferralLogItemSchema = z.object({
  inviter_global_id: z.string().regex(/^\d{10}$/),
  invitee_global_id: z.string().regex(/^\d{10}$/),
  status: z.enum(["active", "inactive"]),
  invited_at: z.string(),
  activated_at: z.string().nullable(),
  reward_recorded: z.boolean(),
});

export const AdminReferralLogResponseSchema = z.object({
  global_id: z.string().regex(/^\d{10}$/),
  items: z.array(AdminReferralLogItemSchema),
  next_cursor: z.string().nullable(),
});

export function parseAdminBankBalanceResponse(value: unknown) {
  return AdminBankBalanceResponseSchema.parse(value);
}

export function ensureAdminBankMutationRequest(value: unknown) {
  return AdminBankMutationRequestSchema.parse(value);
}

export function parseAdminBankMutationResponse(value: unknown) {
  return AdminBankMutationResponseSchema.parse(value);
}

export function parseAdminWithdrawalListResponse(value: unknown) {
  return AdminWithdrawalListResponseSchema.parse(value);
}

export function ensureAdminWithdrawApproveRequest(value: unknown) {
  return AdminWithdrawApproveRequestSchema.parse(value);
}

export function ensureAdminWithdrawPayoutReserveRequest(value: unknown) {
  return AdminWithdrawPayoutReserveRequestSchema.parse(value);
}

export function parseAdminWithdrawPayoutReservationResponse(value: unknown) {
  return AdminWithdrawPayoutReservationResponseSchema.parse(value);
}

export function ensureAdminWithdrawRejectRequest(value: unknown) {
  return AdminWithdrawRejectRequestSchema.parse(value);
}

export function parseAdminWithdrawActionResponse(value: unknown) {
  return AdminWithdrawActionResponseSchema.parse(value);
}

export function parseAdminWithdrawOutcomePreviewResponse(
  value: unknown,
) {
  return AdminWithdrawOutcomePreviewResponseSchema.parse(value);
}

export function parseAdminReferralSummaryResponse(value: unknown) {
  return AdminReferralSummaryResponseSchema.parse(value);
}

export function parseAdminReferralLogResponse(value: unknown) {
  return AdminReferralLogResponseSchema.parse(value);
}

