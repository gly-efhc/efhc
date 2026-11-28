export function parseUnits(
  value: string,
  decimals: number,
): bigint {
  const safe = String(value || "0").trim();
  if (!/^[-+]?\d+(?:\.\d+)?$/.test(safe)) {
    throw new Error("INVALID_DECIMAL_STRING");
  }
  if (!Number.isInteger(decimals) || decimals < 0) {
    throw new Error("INVALID_DECIMALS");
  }

  let [integer, fraction = ""] = safe.split(".");
  const negative = integer.startsWith("-");
  if (integer.startsWith("+") || integer.startsWith("-")) {
    integer = integer.slice(1);
  }
  integer = integer.replace(/^0+(?=\d)/, "");
  fraction = fraction.replace(/[^0-9]/g, "");

  if (fraction.length > decimals) {
    if (decimals === 8 || /[1-9]/.test(fraction.substring(decimals))) {
      throw new Error("AMOUNT_PRECISION_INVALID");
    }
    // Native rails may normalize redundant zeros without changing value.
    fraction = fraction.substring(0, decimals);
  } else {
    fraction = fraction.padEnd(decimals, "0");
  }

  const raw = `${negative ? "-" : ""}${integer || "0"}${fraction}`;
  return BigInt(raw || "0");
}

export function formatUnits(
  value: bigint | string,
  decimals: number,
): string {
  if (!Number.isInteger(decimals) || decimals < 0) {
    throw new Error("INVALID_DECIMALS");
  }
  let display = String(value);
  const negative = display.startsWith("-");
  if (negative) display = display.slice(1);
  display = display.replace(/^0+(?=\d)/, "");
  display = display.padStart(decimals + 1, "0");
  const cut = display.length - decimals;
  const integer = display.slice(0, cut) || "0";
  const fraction = display.slice(cut).replace(/0+$/, "");
  const out = fraction ? `${integer}.${fraction}` : integer;
  return negative ? `-${out}` : out;
}

export function parseUsdtD6(value: string): bigint {
  return parseUnits(value, 6);
}

export function formatUsdtD6(value: bigint | string): string {
  return formatUnits(value, 6);
}

export function parseEfhcJettonD8(value: string): bigint {
  return parseUnits(value, 8);
}

export function formatEfhcJettonD8(
  value: bigint | string,
): string {
  return formatUnits(value, 8);
}
