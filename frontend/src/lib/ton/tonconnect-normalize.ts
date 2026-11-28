import { Address } from "@ton/core/dist/address/Address";
import { beginCell } from "@ton/core/dist/boc/Builder";
import type { TonWalletMessage, TonWalletRawTransaction } from "./tx";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function normalizeTonConnectMessage(
  raw: unknown,
): TonWalletMessage | null {
  if (!isRecord(raw)) return null;
  const rawAddress = String(raw.address || "").trim();
  const amount = String(raw.amount || "").trim();
  const rawPayload = raw.payload == null
    ? undefined
    : typeof raw.payload === "string" ? raw.payload.trim() : null;
  const stateInit = raw.stateInit == null
    ? undefined
    : typeof raw.stateInit === "string" ? raw.stateInit.trim() : null;
  if (
    !rawAddress || !/^\d+$/.test(amount)
    || (typeof raw.amount === "number" && !Number.isSafeInteger(raw.amount))
    || rawPayload === null || stateInit === null
  ) return null;
  let address = rawAddress;
  try {
    const parsed = Address.parse(rawAddress);
    if (Address.isRaw(rawAddress)) {
      address = parsed.toString({ urlSafe: true, bounceable: true });
    }
  } catch {
    return null;
  }
  // API intent memos are text; TonConnect requires a serialized comment cell.
  // Already encoded payloads retain their exact bytes.
  const payload = rawPayload && /^(?:EFHC2|EFHC):/.test(rawPayload)
    ? beginCell().storeUint(0, 32).storeStringTail(rawPayload).endCell().toBoc().toString("base64")
    : rawPayload;
  return { address, amount, payload, ...(stateInit ? { stateInit } : {}) };
}

export function normalizeTonConnectTx(
  raw: unknown,
): TonWalletRawTransaction | null {
  if (!isRecord(raw)) return null;
  const validUntil = Number(raw.validUntil || 0);
  const messagesRaw = Array.isArray(raw.messages)
    ? raw.messages
    : [];
  const messages: TonWalletMessage[] = [];
  for (const messageRaw of messagesRaw) {
    const message = normalizeTonConnectMessage(messageRaw);
    // A wallet signs the complete requested batch; dropping one recipient
    // changes the transaction rather than normalizing its transport.
    if (!message) return null;
    messages.push(message);
  }
  if (!Number.isSafeInteger(validUntil) || validUntil <= 0) {
    return null;
  }
  if (!messages.length) {
    return null;
  }
  if (raw.network != null && raw.network !== "-239" && raw.network !== "-3") {
    return null;
  }
  return { validUntil, messages, ...(raw.network ? { network: raw.network } : {}) };
}
