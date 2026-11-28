export type UsdtCheckoutRuntimeMode =
  | "disabled"
  | "preview"
  | "staged"
  | "live";

export type UsdtFeatureGateState = {
  runtimeMode: UsdtCheckoutRuntimeMode;
  enabled: boolean;
  reason: string;
};

function normalizeRuntimeMode(
  value: string | null | undefined,
): UsdtCheckoutRuntimeMode | null {
  const raw = String(value || "").trim().toLowerCase();
  if (raw === "disabled") return "disabled";
  if (raw === "preview") return "preview";
  if (raw === "staged") return "staged";
  if (raw === "live") return "live";
  return null;
}

export function getUsdtFeatureGateState(
  serverMode?: string | null,
): UsdtFeatureGateState {
  const runtimeMode = normalizeRuntimeMode(serverMode) || "disabled";
  if (runtimeMode === "live" || runtimeMode === "staged") {
    return {
      runtimeMode,
      enabled: true,
      reason: "USDT path разрешён серверным gate режимом.",
    };
  }
  if (runtimeMode === "preview") {
    return {
      runtimeMode,
      enabled: false,
      reason: "USDT path разрешён только для preview до runtime-proof.",
    };
  }
  return {
    runtimeMode: "disabled",
    enabled: false,
    reason: "USDT live path остаётся отключённым до runtime-proof.",
  };
}
