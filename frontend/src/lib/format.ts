import { formatUnits, parseUnits } from "./ton/units";

export function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

// Exact EFHC D8: no loss of precision.
export function format8(v: string | number | null | undefined): string {
  return fromScaledBigint(parseUnits(normalizeDecimalStr(v), 8), 8);
}

function normalizeDecimalStr(
  v: string | number | null | undefined,
): string {
  if (v === null || v === undefined) return "0";
  const s = typeof v === "number" ? String(v) : String(v);
  // Avoid scientific notation.
  if (s.includes("e") || s.includes("E")) {
    throw new Error("Scientific notation forbidden");
  }
  return s.trim();
}

export function formatFixedDown(
  v: string | number | null | undefined,
  decimals: number,
): string {
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 8) {
    throw new Error("INVALID_DECIMALS");
  }
  // D8 is an atomic financial boundary: never silently truncate a ninth digit.
  if (decimals === 8) return format8(v);
  const s = normalizeDecimalStr(v);
  if (!/^[+-]?\d+(?:\.\d+)?$/.test(s)) {
    throw new Error("INVALID_DECIMAL_STRING");
  }
  const neg = s.startsWith("-");
  const raw = /^[+-]/.test(s) ? s.slice(1) : s;
  const [integer, fraction = ""] = raw.split(".");
  const intPart = integer.replace(/^0+(?=\d)/, "");
  const truncated = fraction.padEnd(decimals, "0").slice(0, decimals);
  const res = decimals > 0 ? `${intPart}.${truncated}` : intPart;
  return neg && !/^0(?:\.0+)?$/.test(res) ? `-${res}` : res;
}

export function toScaledBigintDown(
  v: string | number | null | undefined,
  scale: number,
): bigint {
  const s = fromScaledBigint(parseUnits(normalizeDecimalStr(v), scale), scale);
  const neg = s.startsWith("-");
  const raw = neg ? s.slice(1) : s;
  const parts = raw.split(".");
  const intPart = parts[0] || "0";
  const frac = (parts[1] || "").padEnd(scale, "0");
  const digits = `${intPart}${frac}`.replace(/^0+(?=\d)/, "");
  const bi = BigInt(digits || "0");
  return neg ? -bi : bi;
}

export function fromScaledBigint(
  v: bigint,
  scale: number,
): string {
  const neg = v < 0n;
  const raw = (neg ? -v : v).toString();
  const padded = raw.padStart(scale + 1, "0");
  const intPart = padded.slice(0, -scale);
  const frac = padded.slice(-scale);
  const out = `${intPart}.${frac}`;
  return neg ? `-${out}` : out;
}

export function sumScaledDown(
  a: string,
  b: string,
  scale: number,
): string {
  const sa = toScaledBigintDown(a, scale);
  const sb = toScaledBigintDown(b, scale);
  const sum = sa + sb;
  return fromScaledBigint(sum, scale);
}

export function cmpFixedDown(
  a: string | number | null | undefined,
  b: string | number | null | undefined,
  decimals: number,
): number {
  const sa = toScaledBigintDown(a, decimals);
  const sb = toScaledBigintDown(b, decimals);
  if (sa === sb) return 0;
  return sa > sb ? 1 : -1;
}

// Exact D8 comparison: excess scale is rejected, without scientific notation.
export function cmp8(
  a: string | number | null | undefined,
  b: string | number | null | undefined,
): number {
  return cmpFixedDown(a, b, 8);
}


// EFHC balances/history preserve every atomic unit; Shop price has its own D2 boundary.
export function formatD8ToHuman(
  v: string | number | null | undefined,
  decimals = 8,
): string {
  const atomic = parseUnits(normalizeDecimalStr(v), 8);
  if (decimals === 8) return fromScaledBigint(atomic, 8);
  return formatUnits(atomic, 8);
}
