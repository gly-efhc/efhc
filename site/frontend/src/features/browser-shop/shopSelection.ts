/** Per-selection client guard: a payment is initiated within the original 15 minutes. */
export const SHOP_SELECTION_WINDOW_MS = 15 * 60 * 1000;
export function shopSelectionWindowOpen(selectedAtMs: number, nowMs = Date.now()): boolean {
  return Number.isSafeInteger(selectedAtMs) && selectedAtMs > 0 &&
    Number.isSafeInteger(nowMs) && nowMs >= selectedAtMs &&
    nowMs - selectedAtMs < SHOP_SELECTION_WINDOW_MS;
}

/** Compare financial D2 prices exactly, without floating-point arithmetic. */
export function sameShopPriceD2(clientDisplay: string, serverDisplay: string): boolean {
  const cents = (raw: string): bigint | null => {
    const match = /^\d+(?:\.\d{1,2})?$/.exec(raw);
    if (!match) return null;
    const [whole, fraction = ""] = raw.split(".");
    return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  };
  const client = cents(clientDisplay);
  return client !== null && client === cents(serverDisplay);
}
