import type {
  BrowserShopIntentTransportMeta,
} from "./browser-shop-intent";
import { USDT_JETTON_MASTER_ADDRESS } from "./constants";

export type UsdtRuntimeReadiness = {
  ready: boolean;
  missing: string[];
};

export function getUsdtRuntimeReadiness(
  intent: BrowserShopIntentTransportMeta | null,
): UsdtRuntimeReadiness {
  if (!intent) {
    return {
      ready: false,
      missing: ["intent"],
    };
  }

  const missing: string[] = [];
  if (!(intent.jetton_master_address || USDT_JETTON_MASTER_ADDRESS)) {
    missing.push("jetton_master_address");
  }
  if (!intent.forward_payload_text && !intent.memo) {
    missing.push("forward_payload_text");
  }
  if (!intent.fee_message_ton_amount) {
    missing.push("fee_message_ton_amount");
  }
  if (!intent.forward_ton_amount) {
    missing.push("forward_ton_amount");
  }
  if (!intent.amount) {
    missing.push("amount");
  }

  return {
    ready: missing.length === 0,
    missing,
  };
}
