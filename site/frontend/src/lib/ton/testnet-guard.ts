/** Explicit browser wallet-chain boundary for EFHC Genesis integrations.
 *
 * Normal Genesis remains TON testnet. A release build may opt into mainnet
 * only after the OWNER authorizes real on-chain wallet testing.
 * This does not change the internal TEST ledger, create signing keys,
 * transfer assets automatically, or weaken TON Proof verification.
 */
export const TON_TESTNET_CHAIN = "-3" as const;
export const TON_MAINNET_CHAIN = "-239" as const;
export const TON_TESTNET_JSON_RPC_ENDPOINT = "https://testnet.toncenter.com/api/v" + "2/jsonRPC";
export const TON_MAINNET_JSON_RPC_ENDPOINT = "https://toncenter.com/api/v" + "2/jsonRPC";

export const GENESIS_WALLET_CHAIN =
  process.env.NEXT_PUBLIC_EFHC_WALLET_NETWORK === "mainnet"
    ? TON_MAINNET_CHAIN
    : TON_TESTNET_CHAIN;

export function isGenesisTestRuntime(): boolean {
  return process.env.NEXT_PUBLIC_EFHC_DATA_SOURCE === "demo_backend";
}

export function requireGenesisWalletNetwork(chain: unknown): void {
  if (!isGenesisTestRuntime()) return;
  if (chain !== GENESIS_WALLET_CHAIN) {
    throw new Error(
      GENESIS_WALLET_CHAIN === TON_MAINNET_CHAIN
        ? "TON_MAINNET_WALLET_REQUIRED"
        : "TON_TESTNET_WALLET_REQUIRED",
    );
  }
}

export function requireGenesisTransactionNetwork(
  transactionNetwork: unknown,
  walletNetwork: unknown,
): void {
  if (!isGenesisTestRuntime()) return;
  requireGenesisWalletNetwork(walletNetwork);
  if (transactionNetwork !== GENESIS_WALLET_CHAIN) {
    throw new Error(
      GENESIS_WALLET_CHAIN === TON_MAINNET_CHAIN
        ? "TON_MAINNET_TRANSACTION_REQUIRED"
        : "TON_TESTNET_TRANSACTION_REQUIRED",
    );
  }
}

export function requireGenesisJsonRpcEndpoint(endpoint: string): void {
  if (!isGenesisTestRuntime()) return;
  // Derive the sender Jetton wallet using the same actual chain.
  // Reject arbitrary endpoints and credential-bearing redirect URLs.
  const expected = GENESIS_WALLET_CHAIN === TON_MAINNET_CHAIN
    ? TON_MAINNET_JSON_RPC_ENDPOINT
    : TON_TESTNET_JSON_RPC_ENDPOINT;
  if (endpoint !== expected) {
    throw new Error(
      GENESIS_WALLET_CHAIN === TON_MAINNET_CHAIN
        ? "TON_MAINNET_RPC_REQUIRED"
        : "TON_TESTNET_RPC_REQUIRED",
    );
  }
}
