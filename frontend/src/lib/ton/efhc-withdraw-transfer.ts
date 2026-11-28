import { Address, beginCell } from "@ton/core";
import {
  resolveSenderJettonWallet,
} from "./jetton-transfer-builder";
import {
  EFHC_JETTON_DECIMALS,
  EFHC_JETTON_MASTER_ADDRESS,
} from "./constants";
import { parseEfhcJettonD8 } from "./units";
import type { TonWalletRawTransaction, TonWalletStructuredTransaction } from "./tx";

function buildBodyBase64(args: {
  amountUnits: bigint;
  recipientOwnerAddress: string;
  responseDestination: string;
}): string {
  const body = beginCell()
    .storeUint(0x0f8a7ea5, 32)
    .storeUint(0n, 64)
    .storeCoins(args.amountUnits)
    .storeAddress(Address.parse(args.recipientOwnerAddress))
    .storeAddress(Address.parse(args.responseDestination))
    .storeBit(0)
    .storeCoins(0n)
    .storeBit(0)
    .endCell();
  return body.toBoc().toString("base64");
}


export function buildEfhcWithdrawStructuredJettonTx(args: {
  senderOwnerAddress: string;
  recipientOwnerAddress: string;
  amountEfhc: string;
  feeMessageTonAmount?: string | null;
  backendJettonMasterAddress?: string | null;
  backendJettonDecimals?: number | null;
}): TonWalletStructuredTransaction {
  const backendMaster = String(args.backendJettonMasterAddress || "").trim();
  if (backendMaster && !Address.parse(backendMaster).equals(Address.parse(EFHC_JETTON_MASTER_ADDRESS))) {
    throw new Error("EFHC_WITHDRAW_JETTON_MASTER_MISMATCH");
  }
  if (
    args.backendJettonDecimals !== null
    && args.backendJettonDecimals !== undefined
    && args.backendJettonDecimals !== EFHC_JETTON_DECIMALS
  ) {
    throw new Error("EFHC_WITHDRAW_JETTON_DECIMALS_MISMATCH");
  }
  const amountUnits = parseEfhcJettonD8(args.amountEfhc);
  if (amountUnits <= 0n) {
    throw new Error("INVALID_EFHC_WITHDRAW_AMOUNT");
  }
  const sender = Address.parse(args.senderOwnerAddress).toString({
    urlSafe: true,
    bounceable: false,
  });
  const recipient = Address.parse(args.recipientOwnerAddress).toString({
    urlSafe: true,
    bounceable: false,
  });
  const fee = String(args.feeMessageTonAmount || "").trim();
  if (fee && !/^\d+$/.test(fee)) {
    throw new Error("INVALID_EFHC_WITHDRAW_FEE_AMOUNT");
  }
  return {
    validUntil: Math.floor(Date.now() / 1000) + 600,
    network: "-239",
    items: [
      {
        type: "jetton",
        master: EFHC_JETTON_MASTER_ADDRESS,
        destination: recipient,
        amount: amountUnits.toString(),
        ...(fee ? { attachAmount: fee } : {}),
        responseDestination: sender,
      },
    ],
  };
}

export function tonConnectWalletSupportsJettonItems(rawWallet: unknown): boolean {
  const features = (rawWallet as {
    device?: { features?: unknown[] };
  } | null)?.device?.features;
  if (!Array.isArray(features)) return false;
  return features.some((feature) => {
    if (!feature || typeof feature !== "object") return false;
    const record = feature as { name?: unknown; itemTypes?: unknown };
    return record.name === "SendTransaction"
      && Array.isArray(record.itemTypes)
      && record.itemTypes.includes("jetton");
  });
}

export async function buildEfhcWithdrawTonConnectTx(args: {
  endpoint: string;
  senderOwnerAddress: string;
  recipientOwnerAddress: string;
  amountEfhc: string;
  feeMessageTonAmount: string;
}): Promise<TonWalletRawTransaction> {
  const feeAmount = String(args.feeMessageTonAmount || "0").trim();
  if (!/^\d+$/.test(feeAmount)) {
    throw new Error("INVALID_EFHC_WITHDRAW_FEE_AMOUNT");
  }
  const amountUnits = parseEfhcJettonD8(args.amountEfhc);
  if (amountUnits <= 0n) {
    throw new Error("INVALID_EFHC_WITHDRAW_AMOUNT");
  }
  const senderJettonWallet = await resolveSenderJettonWallet({
    endpoint: args.endpoint,
    ownerAddress: args.senderOwnerAddress,
    jettonMasterAddress: EFHC_JETTON_MASTER_ADDRESS,
  });
  const payload = buildBodyBase64({
    amountUnits,
    recipientOwnerAddress: args.recipientOwnerAddress,
    responseDestination: args.senderOwnerAddress,
  });
  return {
    validUntil: Math.floor(Date.now() / 1000) + 600,
    network: "-239",
    messages: [
      {
        address: senderJettonWallet,
        amount: feeAmount,
        payload,
      },
    ],
  };
}

export const EFHC_WITHDRAW_DECIMALS = EFHC_JETTON_DECIMALS;
