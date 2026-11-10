/** Per-selection client guard: a payment is initiated within the original 15 minutes. */
export const SHOP_SELECTION_WINDOW_MS = 15 * 60 * 1000;
export function shopSelectionWindowOpen(selectedAtMs: number, nowMs = Date.now()): boolean {
  return Number.isSafeInteger(selectedAtMs) && selectedAtMs > 0 &&
    Number.isSafeInteger(nowMs) && nowMs >= selectedAtMs &&
    nowMs - selectedAtMs < SHOP_SELECTION_WINDOW_MS;
}
