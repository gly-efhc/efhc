export type RecipientStrategy =
  | "owner_derived_wallet"
  | "fixed_recipient_wallet";

export type UsdtFeePolicy = {
  messageTonAmount: string;
  forwardTonAmount: string;
};

export type UsdtRecipientPolicy = {
  strategy: RecipientStrategy;
  ownerAddress?: string | null;
  recipientJettonWallet?: string | null;
};

export function assertRecipientPolicy(
  policy: UsdtRecipientPolicy,
): UsdtRecipientPolicy {
  if (policy.strategy === "owner_derived_wallet") {
    if (!String(policy.ownerAddress || "").trim()) {
      throw new Error("OWNER_ADDRESS_REQUIRED");
    }
    return policy;
  }
  if (!String(policy.recipientJettonWallet || "").trim()) {
    throw new Error("RECIPIENT_JETTON_WALLET_REQUIRED");
  }
  return policy;
}

export function assertUsdtFeePolicy(
  policy: UsdtFeePolicy,
): UsdtFeePolicy {
  if (!String(policy.messageTonAmount || "").trim()) {
    throw new Error("MESSAGE_TON_AMOUNT_REQUIRED");
  }
  if (!String(policy.forwardTonAmount || "").trim()) {
    throw new Error("FORWARD_TON_AMOUNT_REQUIRED");
  }
  return policy;
}
