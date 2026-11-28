import { z } from "zod";
import { apiRequest } from "../lib/api";
import { parseGlobalId } from "../types/identity";

// Independent read-only account truth. Both Header and Balance share this,
// while transaction history is fetched through a separate paged resource.
const decimal = z.string().regex(/^\d+(?:\.\d{1,8})?$/);
export const currentAccountBalancesSchema = z.object({
  global_id: z.string().transform(parseGlobalId),
  main_balance: decimal,
  bonus_balance: decimal,
});
export type CurrentAccountBalances = z.infer<typeof currentAccountBalancesSchema>;

export async function readCurrentAccountBalances(signal?: AbortSignal): Promise<CurrentAccountBalances> {
  const response = await apiRequest<unknown>("/user/me", "GET", { signal });
  return currentAccountBalancesSchema.parse(response);
}
