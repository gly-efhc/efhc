import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

function loadTs(path, dependencies) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const mod = { exports: {} };
  const dependency = (name) => {
    if (!Object.hasOwn(dependencies, name)) {
      throw new Error("Unmocked runtime dependency: " + name);
    }
    return dependencies[name];
  };
  new Function("module", "exports", "require", compiled)(
    mod, mod.exports, dependency,
  );
  return mod.exports;
}

const request = Object.freeze({
  validUntil: 1_800_000_000,
  network: "-239",
  messages: [{ address: "test-sender-jetton-wallet", amount: "50000000", payload: "test-boc" }],
});
const wallet = Object.freeze({ account: { address: "test-owner", chain: "-239" } });

function loadSend(networkGuard = (requested, connected) => {
  if (requested !== "-239" || connected !== "-239") {
    throw new Error("TON_MAINNET_TRANSACTION_REQUIRED");
  }
}) {
  return loadTs("../../src/lib/tonconnect.ts", {
    "./ton/ton-proof-challenge": {},
    "./ton/testnet-guard": {
      requireGenesisTransactionNetwork: networkGuard,
      requireGenesisWalletNetwork: () => undefined,
    },
    "../services/tonConnect.service": {},
  });
}

test("official sendTransaction is invoked synchronously in the click stack, before wallet response", async () => {
  const { sendTonConnectTransaction } = loadSend();
  const calls = [];
  let respond;
  const pendingWalletResponse = new Promise((resolve) => { respond = resolve; });
  const ui = {
    sendTransaction(value) {
      calls.push(value);
      return pendingWalletResponse;
    },
  };
  const result = sendTonConnectTransaction(ui, request, wallet);
  assert.deepEqual(calls, [request], "SDK call must not await any RPC or microtask");
  respond({ boc: "base64-signed-boc" });
  assert.deepEqual(await result, {
    boc: "base64-signed-boc",
    traceId: null,
  });
});

test("mismatched wallet network fails closed before any SDK send", async () => {
  const { sendTonConnectTransaction } = loadSend();
  let sendCalls = 0;
  const ui = { sendTransaction() { sendCalls++; return Promise.resolve({ boc: "invalid" }); } };
  const result = sendTonConnectTransaction(ui, request, {
    account: { chain: "-3" },
  });
  assert.equal(sendCalls, 0);
  await assert.rejects(result, /TON_MAINNET_TRANSACTION_REQUIRED/);
});

test("wallet rejection stays distinguishable from an unsigned response", async () => {
  const { sendTonConnectTransaction, TonConnectUserRejectedError } = loadSend();
  const ui = {
    sendTransaction() {
      return Promise.reject(Object.assign(new Error("User rejected"), {
        name: "UserRejectsError",
      }));
    },
  };
  await assert.rejects(
    sendTonConnectTransaction(ui, request, wallet),
    TonConnectUserRejectedError,
  );
});

test("wallet opening alone and a fulfilled result without signed BOC are not success", async () => {
  const { sendTonConnectTransaction } = loadSend();
  for (const value of [undefined, {}, { boc: "" }, { boc: null }]) {
    const ui = { sendTransaction: () => Promise.resolve(value) };
    await assert.rejects(
      sendTonConnectTransaction(ui, request, wallet),
      /TONCONNECT_TRANSACTION_RESPONSE_INVALID/,
    );
  }
});

test("official adapter forwards the same transaction synchronously and never substitutes a fake signer", async () => {
  const { sendTonConnectTransaction, isTonConnectUserRejected, TonConnectUserRejectedError } =
    loadSend();
  const { createTonConnectAdapter } = loadTs(
    "../../src/lib/wallet-provider/adapters/TonConnectAdapter.ts",
    {
      "../../tonconnect": {
        sendTonConnectTransaction,
        isTonConnectUserRejected,
        TonConnectUserRejectedError,
      },
      "../../ton/testnet-guard": {
        GENESIS_WALLET_CHAIN: "-239",
        isGenesisTestRuntime: () => false,
        requireGenesisWalletNetwork: () => undefined,
      },
      "../types": {
        WalletAdapterUnavailableError: class extends Error {},
        WalletUserRejectedError: class extends Error {},
      },
    },
  );
  const calls = [];
  const api = { sendTransaction(value) {
    calls.push(value);
    return Promise.resolve({ boc: "signed-result", traceId: "trace" });
  } };
  const adapter = createTonConnectAdapter({
    tonConnectUI: api,
    wallet,
    address: "test-owner",
    restoreSettled: true,
    modalOpened: false,
  });
  const promise = adapter.sendTransaction(request);
  assert.deepEqual(calls, [request], "adapter must not defer the official SDK action");
  assert.deepEqual(await promise, {
    boc: "signed-result",
    traceId: "trace",
    provider: "tonconnect",
  });
});

test("deposit button uses the ready payload without pre-send await and no unattended retry", () => {
  const component = readFileSync(
    new URL("../../src/components/DepositModal.tsx", import.meta.url),
    "utf8",
  );
  const from = component.indexOf("const sendPreparedDirectDeposit = useCallback(");
  const to = component.indexOf("async function sendDirectEfhcDeposit()", from);
  assert.ok(from >= 0 && to > from);
  const handler = component.slice(from, to);
  assert.match(handler, /void sendTransaction\(ready\.tx\)\.then\(/);
  assert.doesNotMatch(handler, /await\s+(?:openDeposit|buildEfhcDirectDepositTx|sendTransaction)/);
  assert.match(handler, /if \(sendInProgress\.current\) return;/);
  assert.match(handler, /validUntil <= Math\.floor\(Date\.now\(\) \/ 1000\) \+ 30/);
  assert.match(handler, /setTransactionPhase\("signing"\)/);
  assert.match(handler, /setTransactionPhase\("signed"\)/);
});
