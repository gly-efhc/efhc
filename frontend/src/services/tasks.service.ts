import { z } from "zod";

import { apiRequest } from "../lib/api";
import { dbIdSchema } from "../lib/api/db-id";
import type { DbId } from "../types/db-id";

// Validate wire amounts before they enter the query cache or strict formatter.
// A malformed update remains a data error and cannot crash the page renderer.
const taskAmountSchema = z.string().regex(/^-?\d+(?:\.\d{1,8})?$/);

const TaskCatalogItemSchema = z.object({
  id: dbIdSchema,
  code: z.string(),
  title: z.string(),
  description: z.unknown().optional(),
  bonus_efhc: taskAmountSchema,
  is_active: z.boolean().optional().default(true),
  kind: z.string().nullable().optional(),
  meta: z.record(z.string(), z.unknown()).nullable().optional(),
});

const MyTaskItemSchema = z.object({
  id: dbIdSchema.nullable(),
  task_id: dbIdSchema,
  status: z.string(),
  progress: z.record(z.string(), z.unknown()).nullable().optional(),
  bonus_efhc: taskAmountSchema,
  can_claim: z.boolean(),
  next_available_at: z.string().nullable().optional(),
});

const TaskCatalogResponseSchema = z.object({
  items: z.array(TaskCatalogItemSchema),
});

const MyTasksResponseSchema = z.object({
  items: z.array(MyTaskItemSchema),
});

const ClaimTaskResponseSchema = z.object({
  ok: z.boolean(),
  global_id: z.string(),
  task_id: dbIdSchema,
  bonus_efhc: z.string(),
  bonus_balance: z.string(),
  main_balance: z.string(),
  detail: z.string().optional(),
});

const AdSlotResponseSchema = z.object({
  token: z.string(),
  min_view_sec: z.number().optional(),
});

const TaskEarningsResponseSchema = z.object({
  total_bonus_earned: taskAmountSchema,
  bonus_asset: z.literal("EFHCb").default("EFHCb"),
  includes_ads: z.boolean().default(true),
});

const AdCallbackResponseSchema = z.object({
  ok: z.boolean().optional(),
  bonus_efhc: z.string().optional(),
  replayed: z.boolean().optional(),
  detail: z.string().optional(),
});

export type TaskCatalogItem = z.infer<typeof TaskCatalogItemSchema>;
export type MyTaskItem = z.infer<typeof MyTaskItemSchema>;
export type ClaimTaskResponse = z.infer<typeof ClaimTaskResponseSchema>;
export type TaskEarningsResponse = z.infer<
  typeof TaskEarningsResponseSchema
>;
export type AdSlotResponse = z.infer<typeof AdSlotResponseSchema>;
export type AdCallbackResponse = z.infer<
  typeof AdCallbackResponseSchema
>;

// Persisted queries from older builds must cross the same read boundary.
export const selectTaskCatalog = (data: unknown): TaskCatalogItem[] =>
  z.array(TaskCatalogItemSchema).parse(data);
export const selectMyTasks = (data: unknown): MyTaskItem[] =>
  z.array(MyTaskItemSchema).parse(data);
export const selectTaskEarnings = (data: unknown): TaskEarningsResponse =>
  TaskEarningsResponseSchema.parse(data);

export async function getTasksCatalog(): Promise<TaskCatalogItem[]> {
  const raw = await apiRequest<unknown>("/tasks/catalog", "GET");
  return TaskCatalogResponseSchema.parse(raw).items;
}

export async function getTaskEarnings(): Promise<TaskEarningsResponse> {
  const raw = await apiRequest<unknown>("/tasks/earnings/me", "GET");
  return TaskEarningsResponseSchema.parse(raw);
}

export async function getMyTasks(): Promise<MyTaskItem[]> {
  const raw = await apiRequest<unknown>("/tasks/my", "GET");
  return MyTasksResponseSchema.parse(raw).items;
}

export async function claimTask(args: {
  taskId: DbId;
  idempotencyKey: string;
}): Promise<ClaimTaskResponse> {
  const raw = await apiRequest<unknown>("/tasks/claim", "POST", {
    idempotencyKey: args.idempotencyKey,
    body: { task_id: args.taskId },
  });
  return ClaimTaskResponseSchema.parse(raw);
}

export async function getBuiltinAdSlot(
  taskCode: string,
): Promise<AdSlotResponse> {
  const query = new URLSearchParams({
    task_code: taskCode,
    provider: "builtin_timer",
  });
  const raw = await apiRequest<unknown>(
    `/ads/slot?${query.toString()}`,
    "GET",
  );
  return AdSlotResponseSchema.parse(raw);
}

export async function finishBuiltinTimerAd(
  token: string,
): Promise<AdCallbackResponse> {
  const raw = await apiRequest<unknown>(
    "/ads/callback/builtin_timer",
    "POST",
    { body: { token } },
  );
  return AdCallbackResponseSchema.parse(raw);
}
