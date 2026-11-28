export type PublicRuntimeKey =
  | "NEXT_PUBLIC_TWA_RETURN_URL"
  | "NEXT_PUBLIC_TON_RPC_ENDPOINT";

declare global {
  interface Window {
    __EFHC_PUBLIC_CONFIG__?: Readonly<Partial<Record<PublicRuntimeKey, string>>>;
  }
}

export function publicRuntimeValue(key: PublicRuntimeKey): string {
  if (typeof window !== "undefined") {
    const value = window.__EFHC_PUBLIC_CONFIG__?.[key];
    if (typeof value === "string") return value;
  }
  // Preserve direct npm/dev deployments and existing configured defaults.
  if (key === "NEXT_PUBLIC_TWA_RETURN_URL") {
    return process.env.NEXT_PUBLIC_TWA_RETURN_URL || "";
  }
  return process.env.NEXT_PUBLIC_TON_RPC_ENDPOINT || "";
}
