import type { DirectDepositOpen } from "../../services/directDeposit.service";
import type { TonConnectTx } from "./tx";

const NANOTON_UNIT = 1_000_000_000n;

/** Format on-chain nanoTON exactly, without floating point or fee estimation. */
export function formatNanoTon(value: string): string {
  if (!/^\d+$/.test(value)) throw new Error("INVALID_TON_ATTACHMENT");
  const nano = BigInt(value);
  const whole = (nano / NANOTON_UNIT).toString();
  const decimals = (nano % NANOTON_UNIT)
    .toString().padStart(9, "0").replace(/0+$/, "");
  return decimals ? whole + "." + decimals : whole;
}

export type DirectDepositReview = Readonly<{
  amountEfhc: string;
  walletAddress: string;
  receiverAddress: string;
  executionContractAddress: string;
  jettonMasterAddress: string;
  memo: string;
  attachedTon: string;
  forwardedTon: string;
  network: string;
  expiresAt: number;
}>;

/**
 * The app reviews exactly the signed-request metadata. This is not a gas
 * estimate, network receipt or permission to send without wallet approval.
 */
export function createDirectDepositReview(args: {
  tx: TonConnectTx;
  metadata: DirectDepositOpen;
  walletAddress: string;
  amountEfhc: string;
}): DirectDepositReview {
  const message = args.tx.messages[0];
  if (args.tx.messages.length !== 1 || !message?.address
    || message.amount !== args.metadata.fee_message_ton_amount
    || !args.walletAddress || !args.metadata.receiver_owner_address
    || !args.metadata.jetton_master_address
    || !/^EFHC:GID:\d{10}$/.test(args.metadata.forward_payload_text)
    || !Number.isSafeInteger(args.tx.validUntil)
    || (args.tx.network !== "-239" && args.tx.network !== "-3")) {
    throw new Error("DIRECT_DEPOSIT_REVIEW_INVALID");
  }
  const attachedTon = formatNanoTon(message.amount);
  const forwardedTon = formatNanoTon(args.metadata.forward_ton_amount);
  if (BigInt(args.metadata.forward_ton_amount) > BigInt(message.amount)) {
    throw new Error("DIRECT_DEPOSIT_REVIEW_INVALID");
  }
  return {
    amountEfhc: args.amountEfhc,
    walletAddress: args.walletAddress,
    receiverAddress: args.metadata.receiver_owner_address,
    executionContractAddress: message.address,
    jettonMasterAddress: args.metadata.jetton_master_address,
    memo: args.metadata.forward_payload_text,
    attachedTon,
    forwardedTon,
    network: args.tx.network === "-239" ? "TON Mainnet" : "TON Testnet",
    expiresAt: args.tx.validUntil,
  };
}
