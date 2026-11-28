import { z } from "zod";

import { apiRequest } from "../lib/api";

const decimalString = z.string().regex(/^\d+(?:\.\d{1,8})?$/);

export const rankItemSchema = z.object({
  global_id: z.string().regex(/^[0-9]{10}$/),
  username: z.string().nullable().optional(),
  total_generated_kwh: decimalString,
  rank_pos: z.number().int().nonnegative(),
  is_vip: z.boolean(),
});

export const myPlusTopSchema = z.object({
  snapshot_at: z.string().min(1),
  me: rankItemSchema,
  top: z.array(rankItemSchema),
  next_cursor: z.string().nullable(),
});

export const topPageSchema = z.object({
  snapshot_at: z.string().min(1),
  items: z.array(rankItemSchema),
  next_cursor: z.string().nullable(),
});

export type RankItem = z.infer<typeof rankItemSchema>;
export type MyPlusTop = z.infer<typeof myPlusTopSchema>;
export type TopPage = z.infer<typeof topPageSchema>;

export async function getMyRankWithTop(
  signal?: AbortSignal,
): Promise<MyPlusTop> {
  const params = new URLSearchParams({
    limit: "100",
    max_age_minutes: "10",
  });
  const raw = await apiRequest<unknown>(
    `/ranks/my-plus-top/me?${params.toString()}`,
    "GET",
    { signal },
  );
  return myPlusTopSchema.parse(raw);
}

export async function getRankTopPage(args: {
  cursor: string;
  signal?: AbortSignal;
}): Promise<TopPage> {
  const params = new URLSearchParams({
    limit: "100",
    cursor: args.cursor,
    max_age_minutes: "10",
  });
  const raw = await apiRequest<unknown>(
    `/ranks/top/me?${params.toString()}`,
    "GET",
    { signal: args.signal },
  );
  return topPageSchema.parse(raw);
}

export async function getRankContext(args: {
  signal?: AbortSignal;
} = {}): Promise<TopPage> {
  const params = new URLSearchParams({
    limit: "5",
    around_me: "true",
    max_age_minutes: "10",
  });
  const raw = await apiRequest<unknown>(
    `/ranks/top/me?${params.toString()}`,
    "GET",
    { signal: args.signal },
  );
  return topPageSchema.parse(raw);
}
