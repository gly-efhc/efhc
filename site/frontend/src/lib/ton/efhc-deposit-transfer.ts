import {
  buildJettonTransferTonConnectTx,
  resolveSenderJettonWallet,
} from "./jetton-transfer-builder";
import type { TonWalletRawTransaction } from "./tx";
import { parseEfhcJettonD8 } from "./units";

export async function buildEfhcDirectDepositTx(args: {
  endpoint: string;
  senderOwnerAddress: string;
  receiverOwnerAddress: string;
  jettonMasterAddress: string;
  amountEfhc: string;
  payloadText: string;
  feeMessageTonAmount: string;
  forwardTonAmount: string;
}): Promise<TonWalletRawTransaction> {
  const sender = String(args.senderOwnerAddress || "").trim();
  const receiver = String(args.receiverOwnerAddress || "").trim();
  const master = String(args.jettonMasterAddress || "").trim();
  const payload = String(args.payloadText || "").trim();
  if (!sender) throw new Error("SENDER_OWNER_ADDRESS_REQUIRED");
  if (!receiver) throw new Error("RECEIVER_OWNER_ADDRESS_REQUIRED");
  if (!master) throw new Error("EFHC_MASTER_ADDRESS_REQUIRED");
  if (!/^EFHC:GID:\d{10}$/.test(payload)) {
    throw new Error("INVALID_DIRECT_EFHC_MEMO");
  }
  const amountUnits = parseEfhcJettonD8(args.amountEfhc);
  if (amountUnits <= 0n) throw new Error("INVALID_EFHC_AMOUNT");
  const senderJettonWallet = await resolveSenderJettonWallet({
    endpoint: args.endpoint,
    ownerAddress: sender,
    jettonMasterAddress: master,
  });
  return buildJettonTransferTonConnectTx(
    {
      asset: "EFHC",
      decimals: 8,
      queryId: 0n,
      amountUnits,
      payloadText: payload,
      recipient: {
        strategy: "owner_derived_wallet",
        address: receiver,
      },
      feeMessageTonAmount: String(args.feeMessageTonAmount || ""),
      forwardTonAmount: String(args.forwardTonAmount || ""),
      senderOwnerAddress: sender,
      responseDestination: sender,
      jettonMasterAddress: master,
    },
    senderJettonWallet,
  );
}
