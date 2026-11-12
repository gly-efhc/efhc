import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../../src/lib/ton/testnet-guard.ts", import.meta.url),
  "utf8",
);

function loadGuard(walletNetwork, dataSource = "demo_backend") {
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const mod = { exports: {} };
  const fakeProcess = { env: {
    NEXT_PUBLIC_EFHC_DATA_SOURCE: dataSource,
    NEXT_PUBLIC_EFHC_WALLET_NETWORK: walletNetwork,
  } };
  new Function("module", "exports", "process", compiled)(mod, mod.exports, fakeProcess);
  return mod.exports;
}

test("default Genesis TEST retains original real testnet boundary", () => {
  const guard = loadGuard(undefined);
  assert.equal(guard.GENESIS_WALLET_CHAIN, "-3");
  guard.requireGenesisWalletNetwork("-3");
  guard.requireGenesisTransactionNetwork("-3", "-3");
  guard.requireGenesisJsonRpcEndpoint(guard.TON_TESTNET_JSON_RPC_ENDPOINT);
  assert.throws(() => guard.requireGenesisWalletNetwork("-239"));
  assert.throws(() => guard.requireGenesisTransactionNetwork("-239", "-3"));
  assert.throws(() => guard.requireGenesisJsonRpcEndpoint(guard.TON_MAINNET_JSON_RPC_ENDPOINT));
});

test("OWNER mainnet wallet signing and RPC require exact mainnet chain", () => {
  const guard = loadGuard("mainnet");
  assert.equal(guard.GENESIS_WALLET_CHAIN, "-239");
  guard.requireGenesisWalletNetwork("-239");
  guard.requireGenesisTransactionNetwork("-239", "-239");
  guard.requireGenesisJsonRpcEndpoint(guard.TON_MAINNET_JSON_RPC_ENDPOINT);
  assert.throws(() => guard.requireGenesisWalletNetwork("-3"));
  assert.throws(() => guard.requireGenesisWalletNetwork(undefined));
  assert.throws(() => guard.requireGenesisTransactionNetwork("-3", "-239"));
  assert.throws(() => guard.requireGenesisTransactionNetwork("-239", "-3"));
  assert.throws(() => guard.requireGenesisJsonRpcEndpoint(guard.TON_TESTNET_JSON_RPC_ENDPOINT));
  assert.throws(() => guard.requireGenesisJsonRpcEndpoint("https://toncenter.com.evil.example/api/v" + "2/jsonRPC"));
});

test("unrecognized override fails closed to testnet, no mixed signing", () => {
  const guard = loadGuard("random-mainnet-like");
  assert.equal(guard.GENESIS_WALLET_CHAIN, "-3");
  assert.throws(() => guard.requireGenesisWalletNetwork("-239"));
});

test("official adapter uses one selected chain without a second wallet protocol", () => {
  const code = readFileSync(
    new URL("../../src/lib/wallet-provider/adapters/TonConnectAdapter.ts", import.meta.url),
    "utf8",
  );
  assert.match(code, /ui\.setConnectionNetwork\(GENESIS_WALLET_CHAIN\)/);
  assert.match(code, /requireGenesisWalletNetwork\(args\.wallet\.account\.chain\)/);
  assert.match(code, /await ui\.openModal\(\)/);
  assert.doesNotMatch(code, /new TonConnect\(/);
});

test("mainnet Pages deployment is explicit rather than inferred from a wallet address", () => {
  const yaml = readFileSync(
    new URL("../../../../.github/workflows/efhc-pages.yml", import.meta.url),
    "utf8",
  );
  assert.match(yaml, /NEXT_PUBLIC_EFHC_WALLET_NETWORK: 'mainnet'/);
  assert.match(yaml, /NEXT_PUBLIC_EFHC_DATA_SOURCE: 'demo_backend'/);
});

test("disconnect requires SDK success and clears the previous one-time proof", () => {
  const layout = readFileSync(
    new URL("../../src/components/Layout.tsx", import.meta.url),
    "utf8",
  );
  const fn = layout.split("async function disconnectWalletSession() {")[1]
    ?.split("\n  function openDeposit()")[0];
  assert.ok(fn, "EFHC disconnect handler must exist");
  assert.match(fn, /try\s*\{\s*await disconnectWallet\(\)/);
  assert.match(fn, /catch\s*\{/);
  assert.match(fn, /setConnectionPhase\("error"\)/);
  assert.match(fn, /setProofState\(null\)/);
  assert.match(fn, /bindingAttemptRef\.current = ""/);
  assert.match(fn, /setConnectionPhase\("disconnected"\)/);
  assert.doesNotMatch(fn, /disconnectWallet\(\)\.catch/);
});
