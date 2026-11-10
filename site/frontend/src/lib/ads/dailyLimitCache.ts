/** Owner-scoped UTC daily-limit display cache. No rewards or advertisement media. */
const PREFIX = "efhc.tasks.ad-limits";
const VALID_OWNER = /^\d{10}$/;
export function utcAdDay(nowMs = Date.now()): string {
  return new Date(nowMs).toISOString().slice(0, 10);
}
function storageKey(owner: string | null): string | null {
  return owner && VALID_OWNER.test(owner) && owner !== "0000000000" ? `${PREFIX}:${owner}` : null;
}
export function readAdDailyLimits(owner: string | null, nowMs = Date.now()): Set<string> {
  const key = storageKey(owner);
  if (!key || typeof window === "undefined") return new Set();
  try {
    const raw = JSON.parse(window.localStorage.getItem(key) || "null");
    if (raw?.utcDay === utcAdDay(nowMs) && Array.isArray(raw.codes)) {
      return new Set(raw.codes.filter((code: unknown): code is string =>
        typeof code === "string" && code.length > 0 && code.length <= 128));
    }
  } catch { /* Corrupt optional display data never grants a reward. */ }
  return new Set();
}
export function writeAdDailyLimits(owner: string | null, codes: ReadonlySet<string>, nowMs = Date.now()): void {
  const key = storageKey(owner);
  if (!key || typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify({
      utcDay: utcAdDay(nowMs),
      codes: [...codes].filter(code => code.length > 0 && code.length <= 128).slice(0, 200),
    }));
  } catch { /* Server remains authoritative for daily reward availability. */ }
}
