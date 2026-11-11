/** TON network boundary for browser-only Genesis TEST wallet interactions.
 * Real key custody and TonProof verification remain with the user's wallet
 * and the backend. This guard blocks signing or sending mainnet transactions
 * from a demo runtime; it never tries to convert a mainnet address to testnet.
 */
export const TON_TESTNET_CHAIN = "-3" as const;
export const TON_TESTNET_JSON_RPC_ENDPOINT = "https://testnet.toncenter.com/api/v" + "2/jsonRPC";

export function isGenesisTestRuntime(): boolean {
  return process.env.NEXT_PUBLIC_EFHC_DATA_SOURCE === "demo_backend";
}

export function requireGenesisWalletNetwork(chain: unknown): void {
  if (!isGenesisTestRuntime()) return;
  if (chain !== TON_TESTNET_CHAIN) {
    throw new Error("TON_TESTNET_WALLET_REQUIRED");
  }
}

export function requireGenesisTransactionNetwork(
  transactionNetwork: unknown,
  walletNetwork: unknown,
): void {
  if (!isGenesisTestRuntime()) return;
  requireGenesisWalletNetwork(walletNetwork);
  if (transactionNetwork !== TON_TESTNET_CHAIN) {
    throw new Error("TON_TESTNET_TRANSACTION_REQUIRED");
  }
}

export function requireGenesisJsonRpcEndpoint(endpoint: string): void {
  if (!isGenesisTestRuntime()) return;
  // The TonClient used for jetton wallet derivation needs JSON-RPC.
  // Refuse any mainnet endpoint, redirects or userinfo-based spoofing.
  if (endpoint !== TON_TESTNET_JSON_RPC_ENDPOINT) {
    throw new Error("TON_TESTNET_RPC_REQUIRED");
  }
}
