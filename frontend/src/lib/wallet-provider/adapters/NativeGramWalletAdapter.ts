import {
  createBridgeWalletAdapter,
  type EfhcWalletAdapterBridgeV1,
} from "./bridgeAdapter";

function resolveNativeGramWalletBridge():
  EfhcWalletAdapterBridgeV1 | null {
  if (typeof window === "undefined") return null;
  const runtime = window as typeof window & {
    __EFHC_NATIVE_GRAM_WALLET_ADAPTER__?: EfhcWalletAdapterBridgeV1;
    Telegram?: {
      WebApp?: {
        __EFHCNativeGramWalletAdapter__?: EfhcWalletAdapterBridgeV1;
      };
    };
  };
  return runtime.__EFHC_NATIVE_GRAM_WALLET_ADAPTER__
    || runtime.Telegram?.WebApp?.__EFHCNativeGramWalletAdapter__
    || null;
}


export function installNativeGramWalletBridge(
  bridge: EfhcWalletAdapterBridgeV1,
): void {
  if (typeof window === "undefined") return;
  const runtime = window as typeof window & {
    __EFHC_NATIVE_GRAM_WALLET_ADAPTER__?: EfhcWalletAdapterBridgeV1;
  };
  runtime.__EFHC_NATIVE_GRAM_WALLET_ADAPTER__ = bridge;
  window.dispatchEvent(
    new Event("efhc:wallet-adapter:native_gram_wallet"),
  );
}

/**
 * Native GRAM wallet boundary. The application consumes only the
 * WalletAdapter contract; a native runtime bridge is attached here.
 */
export function createNativeGramWalletAdapter() {
  return createBridgeWalletAdapter({
    id: "native_gram_wallet",
    label: "Native Gram Wallet",
    resolveBridge: resolveNativeGramWalletBridge,
  });
}
