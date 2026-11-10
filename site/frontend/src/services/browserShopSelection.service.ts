/** Server-confirmed external Shop selection. No cached price grants payment rights. */
import { z } from "zod";
import { apiRequest } from "../lib/api";
import type { BrowserShopCreateIntentRequest } from "../lib/api/generated/economicUserSeams";
import { ensureBrowserShopCreateIntentRequest } from "../lib/api/generated/economicUserSeamValidators";
import { dbIdSchema } from "../lib/api/db-id";

const selectionResponseSchema = z.object({
  global_id: z.string().regex(/^\d{10}$/),
  order_id: dbIdSchema,
  sku: z.string().min(1),
  pay_method: z.enum(["TON", "USDT"]),
  external_amount_display: z.string().min(1),
  external_amount_atomic: z.string().regex(/^\d+$/),
  expires_at: z.string().datetime({offset:true}),
});
export type BrowserShopSelectionResponse = z.infer<typeof selectionResponseSchema>;

export async function selectBrowserShop(
  request: BrowserShopCreateIntentRequest,
): Promise<BrowserShopSelectionResponse> {
  const body = ensureBrowserShopCreateIntentRequest(request);
  if (!body.token || !body.client_nonce || !["TON", "USDT"].includes(body.pay_method)) {
    throw new Error("SHOP_SELECTION_AUTH_REQUIRED");
  }
  const result = await apiRequest<unknown>("/shopfront/select", "POST", {body});
  const parsed = selectionResponseSchema.parse(result);
  if (parsed.sku !== body.sku || parsed.pay_method !== body.pay_method) {
    throw new Error("SHOP_SELECTION_SERVER_MISMATCH");
  }
  return parsed;
}
