import {
  assertRecipientPolicy,
  type UsdtRecipientPolicy,
} from "./policy";

export type RecipientTarget = {
  strategy: UsdtRecipientPolicy["strategy"];
  address: string;
};

export function resolveRecipientTarget(
  policy: UsdtRecipientPolicy,
): RecipientTarget {
  const checked = assertRecipientPolicy(policy);
  if (checked.strategy === "owner_derived_wallet") {
    return {
      strategy: checked.strategy,
      address: String(checked.ownerAddress || "").trim(),
    };
  }
  return {
    strategy: checked.strategy,
    address: String(
      checked.recipientJettonWallet || "",
    ).trim(),
  };
}
