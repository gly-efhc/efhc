import { useCallback } from "react";
import {
  useQueryClient,
} from "@tanstack/react-query";

import {
  useWalletProvider,
  type PreparedWalletProof,
} from "../lib/wallet-provider";

/**
 * Compatibility query keys retained for cache invalidation only.
 * Runtime wallet transport is owned by WalletProvider.
 */
export const tonConnectKeys = {
  all: ["wallet-provider"] as const,
  wallets: ["wallet-provider", "wallets"] as const,
};

/**
 * @deprecated Prefer useWalletProvider() directly. This facade has no
 * TonConnect SDK dependency and forwards legacy call shapes to the
 * active WalletAdapter.
 */
export function useTonConnectLinkage() {
  const queryClient = useQueryClient();
  const provider = useWalletProvider();

  const prepareTonProof = useCallback(
    (_legacyTonConnectUi?: unknown) => provider.prepareProof(),
    [provider],
  );
  const bindVerifiedTonConnectWallet = useCallback(
    (
      _legacyWallet: unknown,
      proofState: PreparedWalletProof | null,
    ) => (
      provider.bindWallet(proofState)
    ),
    [provider],
  );
  const fetchTonConnectWallets = useCallback(
    (_legacyTonConnectUi?: unknown) => queryClient.fetchQuery({
      queryKey: tonConnectKeys.wallets,
      queryFn: () => provider.listWallets(),
      staleTime: 5_000,
    }),
    [provider, queryClient],
  );
  const disconnectTonConnect = useCallback(
    async (_legacyTonConnectUi?: unknown) => {
      await provider.disconnect();
      await queryClient.invalidateQueries({
        queryKey: tonConnectKeys.all,
      });
    },
    [provider, queryClient],
  );

  return {
    prepareTonProof,
    bindVerifiedTonConnectWallet,
    fetchTonConnectWallets,
    disconnectTonConnect,
  };
}
