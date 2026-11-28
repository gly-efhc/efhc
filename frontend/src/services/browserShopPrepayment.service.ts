import { matchesExternalShopReview, readShopReview, type ShopReview } from "../features/browser-shop/shopCheckoutReview";
import { apiRequest } from "../lib/api";
import { getAuthAuthorizationHeader } from "../lib/auth-session";
import { parseBrowserShopCreateIntentResponse } from "../lib/api/generated/economicUserSeamValidators";
import { dbIdFromApi } from "../types/db-id";
import type { DraftShopState, ShopAction } from "../features/browser-shop/shopCheckoutLifecycle";

export type PrepareSelection = {
  sku: string;
  method: "TON" | "USDT" | "EFHC";
  quantity: 1;
  custom_efhc_amount_d8: string | null;
};
const states: readonly DraftShopState[] = ["not_seen","prepared","canceled","issued","paid","terminal_unpaid"];
export async function callShopPrepayment(
  action: ShopAction, token: string, key: string, selection?: PrepareSelection, reviewed?: ShopReview | null,
) {
  if (!token || !key || (action !== "status" && !selection) ||
      (action === "pay" && (!reviewed || reviewed.quote.asset !== selection?.method))) throw new Error("SHOP_PREPAYMENT_CONTEXT_REQUIRED");
  const payingBalance = action === "pay" && selection?.method === "EFHC";
  // Read only readiness; the canonical transport supplies the bearer, never this feature.
  if (payingBalance && !getAuthAuthorizationHeader()) throw new Error("SHOP_PREPAYMENT_NATIVE_SESSION_REQUIRED");
  const route = payingBalance ? "pay-balance" : action;
  const raw = await apiRequest<unknown>(`/shopfront/checkout-requests/${route}`, "POST", {
    headers: { "X-EFHC-Handoff": token },
    body: action === "status" ? { key } : {
      key, ...selection, ...(action === "pay" ? { review_id: reviewed?.review_id } : {}),
    },
  });
  if (!raw || typeof raw !== "object") throw new Error("SHOP_PREPAYMENT_RESPONSE_INVALID");
  const data = raw as Record<string, unknown>;
  const state = data.state as DraftShopState;
  if (!states.includes(state)) throw new Error("SHOP_PREPAYMENT_RESPONSE_INVALID");
  const order_id = data.order_id === undefined ? undefined : dbIdFromApi(data.order_id);
  const intent_id = data.intent_id === undefined ? undefined : dbIdFromApi(data.intent_id);
  if (payingBalance && (state !== "paid" || !order_id || intent_id || data.payment !== undefined)) {
    throw new Error("SHOP_PREPAYMENT_BALANCE_RESPONSE_INVALID");
  }
  // Other actions and replays are status-only. Old create-intent payloads do not
  // imply fresh issuance from this endpoint.
  const payment = action === "pay" && state === "issued" && data.payment !== undefined
    ? parseBrowserShopCreateIntentResponse(data.payment) : null;
  if (payment && (!order_id || !intent_id || !reviewed || String(payment.order_id) !== order_id ||
      String(payment.intent_id) !== intent_id || !matchesExternalShopReview(reviewed, payment))) {
    throw new Error("SHOP_PREPAYMENT_PAYMENT_LINK_MISMATCH");
  }
  const review = state === "prepared" ? readShopReview(data) : null;
  if ((state === "prepared" && (!review || (selection && review.quote.asset !== selection.method))) ||
      (state !== "prepared" && (data.review_id !== undefined || data.quote !== undefined))) {
    throw new Error("SHOP_PREPAYMENT_REVIEW_INVALID");
  }
  return { state, order_id, intent_id, payment, review };
}
