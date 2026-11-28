import {
  buildUsdtTransferPlan,
  type BuildUsdtTransferPlanArgs,
} from "./usdt-transfer-plan";
import { USDT_JETTON_MASTER_ADDRESS } from "./constants";
import type { JettonTransferPlan } from "./tx";
import type { DbId } from "../../types/db-id";

export type BrowserShopIntentTransportMeta = {
  intent_id: DbId;
  pay_method: string;
  memo: string;
  to_wallet: string;
  amount: string;
  tonconnect_transport_kind?: string | null;
  jetton_master_address?: string | null;
  jetton_decimals?: number | null;
  forward_payload_text?: string | null;
  fee_message_ton_amount?: string | null;
  forward_ton_amount?: string | null;
  recipient_strategy?: string | null;
  usdt_checkout_mode?: string | null;
};

export function isJettonTransferIntent(
  intent: BrowserShopIntentTransportMeta,
): boolean {
  return (
    String(intent.tonconnect_transport_kind || "")
      .trim()
      .toLowerCase() === "jetton_transfer"
  );
}

export function buildUsdtTransferPlanFromBrowserShopIntent(
  intent: BrowserShopIntentTransportMeta,
  args: {
    senderOwnerAddress: string;
    responseDestination?: string | null;
    recipientPolicy: BuildUsdtTransferPlanArgs["recipientPolicy"];
    queryId?: bigint;
  },
): JettonTransferPlan {
  const master = String(
    intent.jetton_master_address || USDT_JETTON_MASTER_ADDRESS || "",
  ).trim();
  const payloadText = String(
    intent.forward_payload_text || intent.memo || "",
  ).trim();
  const feeMessageTonAmount = String(
    intent.fee_message_ton_amount || "",
  ).trim();
  const forwardTonAmount = String(
    intent.forward_ton_amount || "",
  ).trim();

  if (!master) {
    throw new Error("JETTON_MASTER_ADDRESS_NOT_READY");
  }
  if (!feeMessageTonAmount) {
    throw new Error("FEE_MESSAGE_TON_AMOUNT_NOT_READY");
  }
  if (!forwardTonAmount) {
    throw new Error("FORWARD_TON_AMOUNT_NOT_READY");
  }

  return buildUsdtTransferPlan({
    ...args,
    usdtMasterAddress: master,
    amountUsdt: String(intent.amount || "").trim(),
    payloadText,
    feePolicy: {
      messageTonAmount: feeMessageTonAmount,
      forwardTonAmount,
    },
  });
}
