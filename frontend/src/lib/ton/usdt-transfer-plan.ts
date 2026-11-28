import {
  USDT_JETTON_DECIMALS,
} from "./constants";
import {
  buildEfhcIntentPayload,
  isCanonicalEfhcIntentPayload,
  type EfhcIntentPurpose,
} from "./payload";
import {
  assertUsdtFeePolicy,
  type UsdtFeePolicy,
  type UsdtRecipientPolicy,
} from "./policy";
import { resolveRecipientTarget } from "./recipient";
import type { JettonTransferPlan } from "./tx";
import { parseUsdtD6 } from "./units";
import type { DbId } from "../../types/db-id";

export type BuildUsdtTransferPlanArgs = {
  usdtMasterAddress: string;
  senderOwnerAddress: string;
  responseDestination?: string | null;
  recipientPolicy: UsdtRecipientPolicy;
  feePolicy: UsdtFeePolicy;
  amountUsdt: string;
  queryId?: bigint;
} & (
  | {
      payloadText: string;
      purpose?: never;
      intentId?: never;
      tg_id?: never;
    }
  | {
      payloadText?: never;
      purpose: EfhcIntentPurpose;
      intentId: DbId;
      tg_id: number;
    }
);

export function buildUsdtTransferPlan(
  args: BuildUsdtTransferPlanArgs,
): JettonTransferPlan {
  const master = String(args.usdtMasterAddress || "").trim();
  const sender = String(args.senderOwnerAddress || "").trim();
  if (!master) {
    throw new Error("USDT_MASTER_ADDRESS_REQUIRED");
  }
  if (!sender) {
    throw new Error("SENDER_OWNER_ADDRESS_REQUIRED");
  }

  const recipient = resolveRecipientTarget(args.recipientPolicy);
  const feePolicy = assertUsdtFeePolicy(args.feePolicy);
  let payloadText = "";
  if ("payloadText" in args && args.payloadText) {
    payloadText = String(args.payloadText).trim();
  } else {
    const generated = args as Extract<
      BuildUsdtTransferPlanArgs,
      { purpose: EfhcIntentPurpose }
    >;
    payloadText = buildEfhcIntentPayload(
      generated.purpose,
      generated.intentId,
      generated.tg_id,
    );
  }
  if (!isCanonicalEfhcIntentPayload(payloadText)) {
    throw new Error("INVALID_EFHC_INTENT_PAYLOAD");
  }

  const amountUnits = parseUsdtD6(args.amountUsdt);
  if (amountUnits <= 0n) {
    throw new Error("INVALID_USDT_AMOUNT");
  }

  return {
    asset: "USDT",
    decimals: USDT_JETTON_DECIMALS,
    queryId: args.queryId ?? 0n,
    amountUnits,
    payloadText,
    recipient,
    feeMessageTonAmount: feePolicy.messageTonAmount,
    forwardTonAmount: feePolicy.forwardTonAmount,
    senderOwnerAddress: sender,
    responseDestination: String(
      args.responseDestination || sender,
    ).trim(),
    jettonMasterAddress: master,
  };
}
