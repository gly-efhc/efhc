import { Address, beginCell, toNano } from "@ton/core";
import { JettonWallet, TonClient, type TupleItemSlice } from "@ton/ton";
import type { JettonTransferPlan, TonConnectTx } from "./tx";
import {
  GENESIS_WALLET_CHAIN,
  requireGenesisJsonRpcEndpoint,
} from "./testnet-guard";

const JETTON_TRANSFER_OPCODE = 0x0f8a7ea5;

export type ResolveSenderJettonWalletArgs = {
  endpoint: string;
  ownerAddress: string;
  jettonMasterAddress: string;
};

/**
 * A public TON RPC can fail in a browser because of provider rate limits or
 * network/CORS availability. The fallback reads the exact owner's jetton
 * wallet from TonAPI, and verifies that the indexed master matches the
 * configured EFHC/USDT master before offering anything for signing.
 *
 * This returns public chain metadata only; it does not sign or send tokens.
 */
async function resolveJettonWalletFromTonApi(
  args: ResolveSenderJettonWalletArgs,
): Promise<string> {
  const owner = Address.parse(args.ownerAddress);
  const master = Address.parse(args.jettonMasterAddress);
  const apiHost = GENESIS_WALLET_CHAIN === "-239"
    ? "https://tonapi.io"
    : "https://testnet.tonapi.io";
  const path = "/v" + "2/accounts/"
    + encodeURIComponent(owner.toRawString())
    + "/jettons/"
    + encodeURIComponent(master.toRawString());
  const response = await fetch(apiHost + path, {
    method: "GET",
    headers: { Accept: "application/json" },
    redirect: "error",
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? "JETTON_WALLET_OR_BALANCE_NOT_FOUND"
        : response.status === 429
          ? "JETTON_LOOKUP_RATE_LIMITED"
          : "JETTON_LOOKUP_PROVIDER_UNAVAILABLE",
    );
  }
  const body: unknown = await response.json();
  if (!body || typeof body !== "object") {
    throw new Error("JETTON_LOOKUP_RESPONSE_INVALID");
  }
  const record = body as Record<string, unknown>;
  const jetton = record.jetton as Record<string, unknown> | null;
  const walletAddress = record.wallet_address as Record<string, unknown> | null;
  if (
    typeof jetton?.address !== "string"
    || Address.parse(jetton.address).toRawString() !== master.toRawString()
  ) {
    throw new Error("JETTON_LOOKUP_MASTER_MISMATCH");
  }
  if (typeof walletAddress?.address !== "string") {
    throw new Error("JETTON_LOOKUP_WALLET_MISSING");
  }
  const wallet = Address.parse(walletAddress.address);
  if (
    wallet.toRawString() === owner.toRawString()
    || wallet.toRawString() === master.toRawString()
  ) {
    throw new Error("JETTON_LOOKUP_WALLET_INVALID");
  }
  return wallet.toString({ urlSafe: true, bounceable: true });
}

export async function resolveSenderJettonWallet(
  args: ResolveSenderJettonWalletArgs,
): Promise<string> {
  requireGenesisJsonRpcEndpoint(args.endpoint);
  const owner = Address.parse(args.ownerAddress);
  const master = Address.parse(args.jettonMasterAddress);
  const ownerCell = beginCell().storeAddress(owner).endCell();
  const stackItem: TupleItemSlice = {
    type: "slice",
    cell: ownerCell,
  };
  try {
    const client = new TonClient({ endpoint: args.endpoint });
    const data = await client.runMethod(
      master,
      "get_wallet_address",
      [stackItem],
    );
    const walletAddress = data.stack.readAddress();
    if (
      walletAddress.toRawString() === owner.toRawString()
      || walletAddress.toRawString() === master.toRawString()
    ) {
      throw new Error("JETTON_LOOKUP_WALLET_INVALID");
    }
    return walletAddress.toString({
      urlSafe: true,
      bounceable: true,
    });
  } catch {
    // TonAPI is the second independent public chain-data provider; neither
    // source can change the wallet address, jetton master, memo or amount.
    return await resolveJettonWalletFromTonApi(args);
  }
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
    network: GENESIS_WALLET_CHAIN,
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
