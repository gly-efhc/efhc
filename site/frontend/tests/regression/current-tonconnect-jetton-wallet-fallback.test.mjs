import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../../src/lib/ton/jetton-transfer-builder.ts", import.meta.url), "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;

function load(overrides = {}) {
  const calls = [];
  const address = (value) => ({
    value,
    toRawString: () => value,
    equals: (other) => other?.value === value,
    toString: () => value,
  });
  const beginCell = () => ({
    storeAddress() { return this; },
    endCell() { return {}; },
  });
  const fakeRequire = (name) => {
    if (name === "@ton/core") return { Address: { parse: address }, beginCell };
    if (name === "@ton/ton") return {
      TonClient: class {
        async runMethod() {
          calls.push("jsonrpc");
          if (overrides.rpcFails) throw Error("HTTP 429");
          return { stack: { readAddress: () => address("sender-jetton-from-rpc") } };
        }
      },
    };
    if (name === "./testnet-guard") return {
      GENESIS_WALLET_CHAIN: overrides.chain || "-239",
      requireGenesisJsonRpcEndpoint(endpoint) {
        assert.equal(endpoint, "https://toncenter.com/api/v" + "2/jsonRPC");
      },
    };
    throw new Error("Unexpected dependency: " + name);
  };
  const fakeFetch = async (url, init) => {
    calls.push({ url, method: init.method });
    if (overrides.fetchFails) throw Error("network unreachable");
    return {
      status: overrides.status ?? 200,
      ok: overrides.status == null || overrides.status === 200,
      json: async () => ({
        jetton: { address: overrides.jetton || "master" },
        wallet_address: { address: overrides.wallet || "sender-jetton-from-tonapi" },
      }),
    };
  };
  const module = { exports: {} };
  new Function(
    "module", "exports", "require", "fetch", "AbortController",
    "setTimeout", "clearTimeout", compiled,
  )(
    module, module.exports, fakeRequire, fakeFetch, AbortController,
    setTimeout, clearTimeout,
  );
  return { fn: module.exports.resolveSenderJettonWallet, calls };
}

const args = {
  endpoint: "https://toncenter.com/api/v" + "2/jsonRPC",
  ownerAddress: "owner",
  jettonMasterAddress: "master",
};

test("successful canonical RPC derivation does not invoke backup or send a transaction", async () => {
  const { fn, calls } = load();
  assert.equal(await fn(args), "sender-jetton-from-rpc");
  assert.deepEqual(calls, ["jsonrpc"]);
});

test("mainnet RPC failure recovers from bounded TonAPI owner+master read only", async () => {
  const { fn, calls } = load({ rpcFails: true });
  assert.equal(await fn(args), "sender-jetton-from-tonapi");
  assert.equal(calls[0], "jsonrpc");
  assert.deepEqual(calls[1], {
    url: "https://tonapi.io/v" + "2/accounts/owner/jettons/master",
    method: "GET",
  });
});

test("fallback must reject a mismatched jetton master instead of trusting symbol", async () => {
  const { fn } = load({ rpcFails: true, jetton: "impostor" });
  await assert.rejects(fn(args), /EFHC_JETTON_MASTER_MISMATCH/);
});

test("missing EFHC balance produces a stable diagnostic, not an attempted transfer", async () => {
  const { fn } = load({ rpcFails: true, status: 404 });
  await assert.rejects(fn(args), /EFHC_JETTON_BALANCE_NOT_FOUND/);
});

test("if all public TON reads fail, fail closed with an actionable error code", async () => {
  const { fn } = load({ rpcFails: true, fetchFails: true });
  await assert.rejects(fn(args), /JETTON_WALLET_LOOKUP_UNAVAILABLE/);
});

test("testnet RPC failure must never fetch mainnet TonAPI as a fallback", async () => {
  const { fn, calls } = load({ rpcFails: true, chain: "-3" });
  await assert.rejects(fn(args), /JETTON_WALLET_LOOKUP_UNAVAILABLE/);
  assert.deepEqual(calls, ["jsonrpc"]);
});

test("deposit UI exposes only allowlisted failure codes without leaking RPC errors", () => {
  const ui = readFileSync(
    new URL("../../src/components/DepositModal.tsx", import.meta.url), "utf8",
  );
  assert.match(ui, /DIRECT_DEPOSIT_FAILURE_CODES = new Set/);
  assert.match(ui, /directDepositFailureCode/);
  assert.match(ui, /EFHC_JETTON_MASTER_MISMATCH/);
  assert.doesNotMatch(ui, /setError\(String\(caught\)\)/);
});

test("direct EFHC deposit prepares remotely before an explicit wallet-send click", () => {
  const ui = readFileSync(
    new URL("../../src/components/DepositModal.tsx", import.meta.url), "utf8",
  );
  const start = ui.indexOf("const prepareDirectEfhcDeposit = useCallback(");
  const end = ui.indexOf("const sendPreparedDirectDeposit = useCallback(", start);
  assert.ok(start >= 0 && end > start, "preparation belongs to the existing deposit modal");
  const preparation = ui.slice(start, end);
  assert.ok(preparation.includes("await openDeposit.mutateAsync()"));
  assert.ok(preparation.includes("await buildEfhcDirectDepositTx("));
  assert.equal(preparation.includes("sendTransaction("), false);

  const sendingEnd = ui.indexOf("async function sendDirectEfhcDeposit()", end);
  assert.ok(sendingEnd > end);
  const sending = ui.slice(end, sendingEnd);
  assert.ok(sending.includes("void sendTransaction(ready.tx).then("));
  assert.equal(sending.includes("await sendTransaction("), false);
  for (const safetyGuard of [
    "sendInProgress.current",
    "validUntil <= Math.floor(Date.now() / 1000) + 30",
    "sameTonAddress(ready.senderAddress, walletAddress)",
    "ready.ownerGlobalId !== String(globalId)",
    "ready.amount !== (creditAmount || amount)",
  ]) {
    assert.ok(sending.includes(safetyGuard), safetyGuard);
  }
  assert.ok(ui.includes("sendPreparedDirectDeposit(preparedDeposit);"));
  assert.ok(ui.includes('t("deposit.review_confirm")'));
  assert.ok(ui.includes("setPreparedDeposit(null)"));
});
