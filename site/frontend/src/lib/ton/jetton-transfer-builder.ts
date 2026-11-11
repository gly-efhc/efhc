import { Address, beginCell, toNano } from "@ton/core";
import { JettonWallet, TonClient, type TupleItemSlice } from "@ton/ton";
import type { JettonTransferPlan, TonConnectTx } from "./tx";
import {
  isGenesisTestRuntime,
  requireGenesisJsonRpcEndpoint,
} from "./testnet-guard";

const JETTON_TRANSFER_OPCODE = 0x0f8a7ea5;

export type ResolveSenderJettonWalletArgs = {
  endpoint: string;
  ownerAddress: string;
  jettonMasterAddress: string;
};

export async function resolveSenderJettonWallet(
  args: ResolveSenderJettonWalletArgs,
): Promise<string> {
  requireGenesisJsonRpcEndpoint(args.endpoint);
  const client = new TonClient({ endpoint: args.endpoint });
  const owner = Address.parse(args.ownerAddress);
  const ownerCell = beginCell().storeAddress(owner).endCell();
  const stackItem: TupleItemSlice = {
    type: "slice",
    cell: ownerCell,
  };
  const data = await client.runMethod(
    Address.parse(args.jettonMasterAddress),
    "get_wallet_address",
    [stackItem],
  );
  const walletAddress = data.stack.readAddress();
  return walletAddress.toString({
    urlSafe: true,
    bounceable: true,
  });
}

export function buildForwardPayloadCellBase64(
  payloadText: string,
): string {
  const cell = beginCell()
    .storeUint(0, 32)
    .storeStringTail(String(payloadText || ""))
    .endCell();
  return cell.toBoc().toString("base64");
}

export function buildJettonTransferBodyBase64(
  plan: JettonTransferPlan,
): string {
  const payloadText = String(plan.payloadText || "").trim();
  if (!payloadText) {
    throw new Error("FORWARD_PAYLOAD_TEXT_REQUIRED");
  }

  const forwardPayload = beginCell()
    .storeUint(0, 32)
    .storeStringTail(payloadText)
    .endCell();

  const body = beginCell()
    .storeUint(JETTON_TRANSFER_OPCODE, 32)
    .storeUint(plan.queryId, 64)
    .storeCoins(plan.amountUnits)
    .storeAddress(Address.parse(plan.recipient.address))
    .storeAddress(Address.parse(plan.responseDestination))
    .storeBit(0)
    .storeCoins(BigInt(plan.forwardTonAmount))
    .storeBit(1)
    .storeRef(forwardPayload)
    .endCell();

  return body.toBoc().toString("base64");
}

export function buildJettonTransferTonConnectTx(
  plan: JettonTransferPlan,
  senderJettonWallet: string,
): TonConnectTx {
  const feeAmount = String(plan.feeMessageTonAmount || "").trim();
  if (!/^\d+$/.test(feeAmount)) {
    throw new Error("INVALID_JETTON_FEE_AMOUNT");
  }
  const payload = buildJettonTransferBodyBase64(plan);
  return {
    validUntil: Math.floor(Date.now() / 1000) + 600,
    network: isGenesisTestRuntime() ? "-3" : "-239",
    messages: [
      {
        address: senderJettonWallet,
        amount: BigInt(feeAmount).toString(),
        payload,
      },
    ],
  };
}

export async function resolveSenderJettonBalance(
  args: ResolveSenderJettonWalletArgs,
): Promise<bigint> {
  requireGenesisJsonRpcEndpoint(args.endpoint);
  const client = new TonClient({ endpoint: args.endpoint });
  const walletAddress = await resolveSenderJettonWallet(args);
  const wallet = client.open(
    JettonWallet.create(Address.parse(walletAddress)),
  );
  return await wallet.getBalance();
}

export function tonToNanoString(value: string): string {
  return toNano(String(value || "0")).toString();
}
