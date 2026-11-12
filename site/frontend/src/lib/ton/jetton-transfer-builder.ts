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
  const master = Address.parse(args.jettonMasterAddress);
  try {
    const data = await client.runMethod(
      master,
      "get_wallet_address",
      [stackItem],
    );
    return data.stack.readAddress().toString({
      urlSafe: true,
      bounceable: true,
    });
  } catch {
    // Public TON Center RPC is rate-limited without an API key. Recover
    // Mainnet *read-only* jetton wallet discovery from a second independent
    // provider without changing the signed TON transaction or trusting
    // arbitrary jettons by symbol/name. Never fall back across networks.
    if (GENESIS_WALLET_CHAIN !== "-239") {
      throw new Error("JETTON_WALLET_LOOKUP_UNAVAILABLE");
    }
    const url = "https://tonapi.io/v2/accounts/"
      + encodeURIComponent(owner.toRawString())
      + "/jettons/"
      + encodeURIComponent(master.toRawString());
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    let response: Response;
    try {
      response = await fetch(url, {
        method: "GET",
        headers: { accept: "application/json" },
        signal: controller.signal,
      });
    } catch {
      throw new Error("JETTON_WALLET_LOOKUP_UNAVAILABLE");
    } finally {
      clearTimeout(timeout);
    }
    if (response.status === 404) {
      throw new Error("EFHC_JETTON_BALANCE_NOT_FOUND");
    }
    if (!response.ok) {
      throw new Error("JETTON_WALLET_LOOKUP_UNAVAILABLE");
    }
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new Error("JETTON_WALLET_LOOKUP_UNAVAILABLE");
    }
    if (!payload || typeof payload !== "object") {
      throw new Error("JETTON_WALLET_LOOKUP_UNAVAILABLE");
    }
    const body = payload as {
      wallet_address?: { address?: unknown };
      jetton?: { address?: unknown };
    };
    if (typeof body.jetton?.address !== "string") {
      throw new Error("EFHC_JETTON_MASTER_UNVERIFIED");
    }
    try {
      if (!Address.parse(body.jetton.address).equals(master)) {
        throw new Error("EFHC_JETTON_MASTER_MISMATCH");
      }
    } catch (cause) {
      if (cause instanceof Error
          && cause.message === "EFHC_JETTON_MASTER_MISMATCH") throw cause;
      throw new Error("EFHC_JETTON_MASTER_UNVERIFIED");
    }
    if (typeof body.wallet_address?.address !== "string") {
      throw new Error("EFHC_JETTON_WALLET_INVALID");
    }
    try {
      return Address.parse(body.wallet_address.address).toString({
        urlSafe: true,
        bounceable: true,
      });
    } catch {
      throw new Error("EFHC_JETTON_WALLET_INVALID");
    }
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
