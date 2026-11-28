import {
  createBridgeWalletAdapter,
  type EfhcWalletAdapterBridgeV1,
} from "./bridgeAdapter";

function resolveTelegramWalletBridge():
  EfhcWalletAdapterBridgeV1 | null {
  if (typeof window === "undefined") return null;
  const runtime = window as typeof window & {
    __EFHC_TELEGRAM_WALLET_ADAPTER__?: EfhcWalletAdapterBridgeV1;
    Telegram?: {
      WebApp?: {
        __EFHCWalletAdapter__?: EfhcWalletAdapterBridgeV1;
      };
    };
  };
  return runtime.__EFHC_TELEGRAM_WALLET_ADAPTER__
    || runtime.Telegram?.WebApp?.__EFHCWalletAdapter__
    || null;
}


export function installTelegramWalletBridge(
  bridge: EfhcWalletAdapterBridgeV1,
): void {
  if (typeof window === "undefined") return;
  const runtime = window as typeof window & {
    __EFHC_TELEGRAM_WALLET_ADAPTER__?: EfhcWalletAdapterBridgeV1;
  };
  runtime.__EFHC_TELEGRAM_WALLET_ADAPTER__ = bridge;
  window.dispatchEvent(
    new Event("efhc:wallet-adapter:telegram_wallet"),
  );
}

/**
 * Future official Telegram Wallet API integration boundary.
 * Only this adapter changes when Telegram publishes its final API.
 */
export function createTelegramWalletAdapter() {
  return createBridgeWalletAdapter({
    id: "telegram_wallet",
    label: "Wallet in Telegram",
    resolveBridge: resolveTelegramWalletBridge,
  });
}
