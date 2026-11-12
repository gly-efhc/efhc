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


test("Jetton send uses the exact wallet network, independent of Genesis TEST data source", () => {
  const builderSource = readFileSync(
    new URL("../../src/lib/ton/jetton-transfer-builder.ts", import.meta.url),
    "utf8",
  );
  // Mainnet Pages intentionally retains demo_backend for its internal economy:
  // that data source must never force a real wallet transaction onto testnet.
  assert.match(builderSource, /network:\s*GENESIS_WALLET_CHAIN/);
  assert.doesNotMatch(builderSource, /network:\s*isGenesisTestRuntime\(\)/);

  const compiled = ts.transpileModule(builderSource, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const cell = () => ({
    storeUint() { return this; },
    storeStringTail() { return this; },
    storeCoins() { return this; },
    storeAddress() { return this; },
    storeBit() { return this; },
    storeRef() { return this; },
    endCell() { return { toBoc: () => Buffer.from("jetton-transfer-test") }; },
  });
  const transactionPlan = {
    amountUnits: 100000000n,
    queryId: 0n,
    payloadText: "EFHC:GID:0000003101",
    recipient: { strategy: "owner_derived_wallet", address: "recipient" },
    responseDestination: "sender",
    forwardTonAmount: "0",
    feeMessageTonAmount: "50000000",
  };
  for (const [walletNetwork, expectedNetwork] of [
    [undefined, "-3"],
    ["mainnet", "-239"],
  ]) {
    const networkPolicy = loadGuard(walletNetwork, "demo_backend");
    const fakeRequire = (name) => {
      if (name === "./testnet-guard") return networkPolicy;
      if (name === "@ton/core") return { beginCell: cell, Address: { parse: (x) => x } };
      if (name === "@ton/ton") return {};
      throw new Error(`Unexpected dependency: ${name}`);
    };
    const mod = { exports: {} };
    new Function("module", "exports", "require", compiled)(mod, mod.exports, fakeRequire);
    const tx = mod.exports.buildJettonTransferTonConnectTx(transactionPlan, "sender-jetton-wallet");
    assert.equal(tx.network, expectedNetwork);
    assert.equal(tx.messages.length, 1);
    assert.equal(tx.messages[0].amount, "50000000");
    assert.ok(tx.messages[0].payload);
    networkPolicy.requireGenesisTransactionNetwork(tx.network, expectedNetwork);
  }
});


test("direct EFHC deposit reads transfer metadata without monetary POST", () => {
  const source = readFileSync(
    new URL("../../src/services/directDeposit.service.ts", import.meta.url),
    "utf8",
  );
  assert.match(source, /apiRequest<unknown>\("\/deposit\/direct-open", "GET"\)/);
  assert.doesNotMatch(source, /apiRequest<unknown>\("\/deposit\/direct-open", "POST"\)/);
});


function makeJettonResolutionFixture(walletNetwork = "mainnet") {
  const source = readFileSync(
    new URL("../../src/lib/ton/jetton-transfer-builder.ts", import.meta.url),
    "utf8",
  );
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const mainnet = walletNetwork === "mainnet";
  const policy = loadGuard(walletNetwork, "demo_backend");
  const owner = "0:" + "1".repeat(64);
  const master = "0:" + "2".repeat(64);
  const jettonWallet = "0:" + "3".repeat(64);
  let rpcError = null;
  let fetchResponse = null;
  const calls = [];
  const mockAddress = (value) => ({
    toRawString: () => value,
    toString: () => value,
  });
  const fakeRequire = (name) => {
    if (name === "./testnet-guard") return policy;
    if (name === "@ton/core") return {
      Address: { parse: mockAddress },
      beginCell: () => ({
        storeAddress() { return this; },
        endCell() { return {}; },
      }),
      toNano: () => 0n,
    };
    if (name === "@ton/ton") return {
      TonClient: class {
        async runMethod() {
          if (rpcError) throw rpcError;
          return { stack: { readAddress: () => mockAddress(jettonWallet) } };
        }
      },
    };
    throw new Error(`Unexpected mock dependency: ${name}`);
  };
  const mockFetch = async (url, options) => {
    calls.push({ url, options });
    if (fetchResponse) return fetchResponse;
    return {
      ok: true, status: 200,
      async json() {
        return {
          balance: "100000000",
          jetton: { address: master },
          wallet_address: { address: jettonWallet },
        };
      },
    };
  };
  const mod = { exports: {} };
  new Function(
    "module", "exports", "require", "fetch", "AbortSignal",
    compiled,
  )(mod, mod.exports, fakeRequire, mockFetch, {
    timeout: () => ({ signal: true }),
  });
  return {
    ...mod.exports,
    owner, master, jettonWallet,
    endpoint: mainnet ? policy.TON_MAINNET_JSON_RPC_ENDPOINT : policy.TON_TESTNET_JSON_RPC_ENDPOINT,
    calls,
    failRpc(error) { rpcError = error; },
    setFetchResponse(response) { fetchResponse = response; },
  };
}

test("direct EFHC send resolves via TON API only after canonical RPC failure", async () => {
  const f = makeJettonResolutionFixture();
  f.failRpc(new Error("429 Too Many Requests"));
  const resolved = await f.resolveSenderJettonWallet({
    endpoint: f.endpoint,
    ownerAddress: f.owner,
    jettonMasterAddress: f.master,
  });
  assert.equal(resolved, f.jettonWallet);
  assert.equal(f.calls.length, 1);
  assert.match(f.calls[0].url, /^https:\/\/tonapi\.io\/v2\/accounts\//);
  assert.equal(f.calls[0].options.method, "GET");
  assert.equal(f.calls[0].options.redirect, "error");
});

test("direct EFHC send refuses different jetton master from TON API", async () => {
  const f = makeJettonResolutionFixture();
  f.failRpc(new Error("RPC down"));
  f.setFetchResponse({
    ok: true, status: 200,
    async json() {
      return {
        jetton: { address: "0:" + "4".repeat(64) },
        wallet_address: { address: f.jettonWallet },
      };
    },
  });
  await assert.rejects(
    () => f.resolveSenderJettonWallet({
      endpoint: f.endpoint,
      ownerAddress: f.owner,
      jettonMasterAddress: f.master,
    }),
    /JETTON_LOOKUP_MASTER_MISMATCH/,
  );
});

test("mainnet default cannot silently route TON RPC to testnet", async () => {
  const f = makeJettonResolutionFixture();
  await assert.rejects(
    () => f.resolveSenderJettonWallet({
      endpoint: loadGuard("mainnet").TON_TESTNET_JSON_RPC_ENDPOINT,
      ownerAddress: f.owner,
      jettonMasterAddress: f.master,
    }),
    /TON_MAINNET_RPC_REQUIRED/,
  );
  assert.equal(f.calls.length, 0);
});

test("successful canonical RPC resolution does not invoke second provider", async () => {
  const f = makeJettonResolutionFixture();
  const address = await f.resolveSenderJettonWallet({
    endpoint: f.endpoint,
    ownerAddress: f.owner,
    jettonMasterAddress: f.master,
  });
  assert.equal(address, f.jettonWallet);
  assert.equal(f.calls.length, 0);
});

test("testnet fallback remains isolated to testnet TON API", async () => {
  const f = makeJettonResolutionFixture("testnet");
  f.failRpc(new Error("RPC unavailable"));
  await f.resolveSenderJettonWallet({
    endpoint: f.endpoint,
    ownerAddress: f.owner,
    jettonMasterAddress: f.master,
  });
  assert.match(f.calls[0].url, /^https:\/\/testnet\.tonapi\.io\/v2\/accounts\//);
});

test("direct EFHC modal uses canonical wallet-chain RPC and safe stage diagnostics", () => {
  const modal = readFileSync(
    new URL("../../src/components/DepositModal.tsx", import.meta.url),
    "utf8",
  );
  assert.match(modal, /endpoint: GENESIS_JSON_RPC_ENDPOINT/);
  assert.doesNotMatch(modal, /publicRuntimeValue\("NEXT_PUBLIC_TON_RPC_ENDPOINT"\)/);
  assert.match(modal, /describeDirectDepositFailure\(caught, stage\)/);
  assert.match(modal, /depositInFlightRef\.current/);
  assert.match(modal, /setTransactionPhase\("signing"\);\s*await sendTransaction\(tx\)/);
});

test("wallet failure labels are stage-specific and cannot leak raw transport messages", () => {
  const source = readFileSync(
    new URL("../../src/lib/ton/direct-deposit-errors.ts", import.meta.url),
    "utf8",
  );
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const mod = { exports: {} };
  new Function("module", "exports", compiled)(mod, mod.exports);
  const diagnose = mod.exports.describeDirectDepositFailure;
  assert.equal(
    diagnose(new Error("JETTON_LOOKUP_MASTER_MISMATCH"), "jetton_wallet"),
    "jetton_wallet:JETTON_LOOKUP_MASTER_MISMATCH",
  );
  assert.equal(
    diagnose(new Error("Failed to fetch https://secret.example/path?token=1234"), "jetton_wallet"),
    "jetton_wallet:TON_NETWORK_OR_RPC_UNAVAILABLE",
  );
  assert.equal(
    diagnose(new Error("Account 0:privateaddress does not have enough balance"), "wallet_send"),
    "wallet_send:WALLET_BALANCE_OR_FEE_INSUFFICIENT",
  );
});
