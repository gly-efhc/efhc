import type { TonWalletRawTransaction } from "./tx";
import {
  resolveSenderJettonWallet,
  buildJettonTransferTonConnectTx,
  resolveSenderJettonBalance,
} from "./jetton-transfer-builder";
import {
  buildUsdtTransferPlan,
  type BuildUsdtTransferPlanArgs,
} from "./usdt-transfer-plan";

export type BuildUsdtTransferArgs =
  BuildUsdtTransferPlanArgs & {
    endpoint: string;
  };

export type BuiltUsdtTransfer = {
  senderJettonWallet: string;
  tonconnectTx: TonWalletRawTransaction;
  amountUnits: string;
  payloadText: string;
  senderJettonBalance: string | null;
};

export async function buildUsdtTransfer(
  args: BuildUsdtTransferArgs,
): Promise<BuiltUsdtTransfer> {
  const plan = buildUsdtTransferPlan(args);
  const senderJettonWallet = await resolveSenderJettonWallet({
    endpoint: args.endpoint,
    ownerAddress: plan.senderOwnerAddress,
    jettonMasterAddress: plan.jettonMasterAddress,
  });

  let senderJettonBalance: string | null = null;
  try {
    senderJettonBalance = (
      await resolveSenderJettonBalance({
        endpoint: args.endpoint,
        ownerAddress: plan.senderOwnerAddress,
        jettonMasterAddress: plan.jettonMasterAddress,
      })
    ).toString();
  } catch {
    senderJettonBalance = null;
  }

  return {
    senderJettonWallet,
    tonconnectTx: buildJettonTransferTonConnectTx(
      plan,
      senderJettonWallet,
    ),
    amountUnits: plan.amountUnits.toString(),
    payloadText: plan.payloadText,
    senderJettonBalance,
  };
}
