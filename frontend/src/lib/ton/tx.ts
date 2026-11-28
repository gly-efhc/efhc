import type { RecipientTarget } from "./recipient";

/** Canonical EFHC request for a TON-compatible wallet transport. */
export type TonWalletMessage = {
  address: string;
  amount: string;
  payload?: string;
  stateInit?: string;
};

export type TonWalletRawTransaction = {
  validUntil: number;
  network?: string;
  messages: TonWalletMessage[];
  items?: undefined;
};

export type TonWalletJettonItem = {
  type: "jetton";
  master: string;
  destination: string;
  amount: string;
  attachAmount?: string;
  responseDestination?: string;
  customPayload?: string;
  forwardAmount?: string;
  forwardPayload?: string;
  queryId?: string;
};

export type TonWalletStructuredTransaction = {
  validUntil: number;
  network?: string;
  items: TonWalletJettonItem[];
  messages?: undefined;
};

export type TonWalletTransaction =
  | TonWalletRawTransaction
  | TonWalletStructuredTransaction;

export type JettonTransferPlan = {
  asset: "USDT" | "EFHC";
  decimals: number;
  queryId: bigint;
  amountUnits: bigint;
  payloadText: string;
  recipient: RecipientTarget;
  feeMessageTonAmount: string;
  forwardTonAmount: string;
  senderOwnerAddress: string;
  responseDestination: string;
  jettonMasterAddress: string;
};
