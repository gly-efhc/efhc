import { z } from "zod";

import { apiRequest } from "../lib/api";

const decimalString = z.string().regex(/^\d+(?:\.\d{1,8})?$/);

export const referralLevelStepSchema = z.object({
  level: z.number().int().min(1).max(5),
  required_active: z.number().int().positive(),
  level_bonus: decimalString,
  direct_bonus_total: decimalString,
  cumulative_level_bonus: decimalString,
  cumulative_total_reward: decimalString,
});

export const referralStatsSchema = z.object({
  bonus_balance: decimalString,
  referrals_bonus_total: decimalString,
  total_referrals: z.number().int().nonnegative(),
  active_referrals: z.number().int().nonnegative(),
  inactive_referrals: z.number().int().nonnegative(),
  level: z.number().int().min(0).max(5),
  current_level_min: z.number().int().nonnegative(),
  next_level: z.number().int().min(1).max(5).nullable(),
  next_level_min: z.number().int().positive().nullable(),
  refs_to_next: z.number().int().nonnegative(),
  progress: z.number().min(0).max(1),
  unit_bonus_per_active: decimalString,
  max_active_for_unit_bonus: z.number().int().positive(),
  bonus_asset: z.literal("EFHCb"),
  full_cycle_direct_bonus: decimalString,
  full_cycle_level_bonus: decimalString,
  full_cycle_total_bonus: decimalString,
  level_steps: z.array(referralLevelStepSchema).length(5),
  referral_code: z.string().min(1),
  referral_link: z.string().nullable(),
});

export const referralItemSchema = z.object({
  child_global_id: z.string().regex(/^\d{10}$/),
  global_id: z.string().regex(/^\d{10}$/),
  username: z.string().nullable().optional(),
  joined_at: z.string().min(1),
  is_active: z.boolean(),
  total_generated_kwh: decimalString,
  panels_count: z.number().int().nonnegative(),
  invited_at: z.string().min(1),
  activated_at: z.string().min(1).nullable(),
});

export const referralsPageSchema = z.object({
  items: z.array(referralItemSchema),
  next_cursor: z.string().nullable(),
});

export type ReferralStats = z.infer<typeof referralStatsSchema>;
export type ReferralItem = z.infer<typeof referralItemSchema>;
export type ReferralsPage = z.infer<typeof referralsPageSchema>;
export type ReferralTab = "active" | "inactive";

export function sortReferralItemsNewestFirst(
  items: readonly ReferralItem[],
): ReferralItem[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const leftInvited = Date.parse(left.item.invited_at);
      const rightInvited = Date.parse(right.item.invited_at);
      const invitedDiff =
        (Number.isFinite(rightInvited) ? rightInvited : Number.NEGATIVE_INFINITY) -
        (Number.isFinite(leftInvited) ? leftInvited : Number.NEGATIVE_INFINITY);
      if (invitedDiff !== 0) return invitedDiff;

      const leftJoined = Date.parse(left.item.joined_at);
      const rightJoined = Date.parse(right.item.joined_at);
      const joinedDiff =
        (Number.isFinite(rightJoined) ? rightJoined : Number.NEGATIVE_INFINITY) -
        (Number.isFinite(leftJoined) ? leftJoined : Number.NEGATIVE_INFINITY);
      if (joinedDiff !== 0) return joinedDiff;

      return left.index - right.index;
    })
    .map(({ item }) => item);
}

export const REFERRALS_ACTIVE_PATH =
  "/referrals/active/me" as const;
export const REFERRALS_INACTIVE_PATH =
  "/referrals/inactive/me" as const;

export async function getReferralStats(
  signal?: AbortSignal,
): Promise<ReferralStats> {
  const raw = await apiRequest<unknown>("/referrals/stats/me", "GET", {
    signal,
  });
  return referralStatsSchema.parse(raw);
}

export async function getReferralsPage(args: {
  tab: ReferralTab;
  cursor?: string | null;
  signal?: AbortSignal;
}): Promise<ReferralsPage> {
  const params = new URLSearchParams({ limit: "20" });
  if (args.cursor) params.set("cursor", args.cursor);
  const path = args.tab === "active"
    ? `${REFERRALS_ACTIVE_PATH}?${params.toString()}`
    : `${REFERRALS_INACTIVE_PATH}?${params.toString()}`;
  const raw = await apiRequest<unknown>(
    path,
    "GET",
    { signal: args.signal },
  );
  return referralsPageSchema.parse(raw);
}
