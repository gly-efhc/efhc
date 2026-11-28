import { dbIdToApi, type DbId } from "../../types/db-id";
export type EfhcIntentPurpose =
  | "deposit_efhc"
  | "shop_external";

export function buildEfhcIntentPayload(
  purpose: EfhcIntentPurpose,
  intentId: DbId,
  tg_id: number,
): string {
  const intent = dbIdToApi(intentId);
  const user = Number(tg_id);
  if (!Number.isInteger(user) || user <= 0) {
    throw new Error("INVALID_TG_ID");
  }
  return `EFHC:${purpose}:${intent}:${user}`;
}

export function isCanonicalEfhcIntentPayload(
  value: string,
): boolean {
  const payload = String(value || "").trim();
  // Mirror the backend parser: current intents carry the immutable atomic
  // snapshot; persisted EFHC v1 intents remain readable for compatibility.
  return /^EFHC2:(deposit_efhc|shop_external):\d{1,20}:(?:G\d{10}|\d{1,20}):(TON|USDT):\d+$/.test(payload)
    || /^EFHC:(deposit_efhc|shop_external):\d{1,20}:(?:G\d{10}|\d{1,20})$/.test(payload);
}
