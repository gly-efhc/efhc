import type {
  BrowserShopIntentTransportMeta,
} from "./browser-shop-intent";
import {
  getUsdtFeatureGateState,
  type UsdtFeatureGateState,
} from "./feature-gates";
import {
  getUsdtRuntimeReadiness,
  type UsdtRuntimeReadiness,
} from "./usdt-readiness";
import { normalizeTonConnectTx } from "./tonconnect-normalize";
import type { TonWalletRawTransaction } from "./tx";

export type BrowserShopUsdtRuntimeState = {
  featureGate: UsdtFeatureGateState;
  readiness: UsdtRuntimeReadiness;
  normalizedTonTx: TonWalletRawTransaction | null;
  canBuildPreview: boolean;
  canRunCheckout: boolean;
  statusLabel: string;
  blockingReasons: string[];
};

export function getBrowserShopUsdtRuntimeState(
  intent: BrowserShopIntentTransportMeta | null,
  tonconnectTxRaw: unknown,
): BrowserShopUsdtRuntimeState {
  const featureGate = getUsdtFeatureGateState(
    intent?.usdt_checkout_mode || null,
  );
  const readiness = getUsdtRuntimeReadiness(intent);
  const normalizedTonTx = normalizeTonConnectTx(tonconnectTxRaw);

  const blockingReasons: string[] = [];
  if (!featureGate.enabled) {
    blockingReasons.push(featureGate.reason);
  }
  blockingReasons.push(...readiness.missing.map((x) => `missing:${x}`));
  if (!normalizedTonTx) {
    blockingReasons.push("missing:tonconnect_tx");
  }

  const canBuildPreview = readiness.ready;
  const canRunCheckout = featureGate.enabled
    && readiness.ready
    && normalizedTonTx !== null;

  let statusLabel = "USDT runtime unavailable";
  if (featureGate.runtimeMode === "disabled") {
    statusLabel = "USDT runtime disabled";
  } else if (canRunCheckout) {
    statusLabel = "USDT runtime ready";
  } else if (canBuildPreview) {
    statusLabel = "USDT runtime ready for preview only";
  }

  return {
    featureGate,
    readiness,
    normalizedTonTx,
    canBuildPreview,
    canRunCheckout,
    statusLabel,
    blockingReasons,
  };
}
