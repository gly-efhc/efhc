import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = (name) => readFileSync(new URL(name, import.meta.url), "utf8");
const loadTs = (code, mockRequire = () => {
  throw new Error("Unexpected runtime import in isolated TON Proof test");
}) => {
  const js = ts.transpileModule(code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const mod = { exports: {} };
  new Function("module", "exports", "require", js)(mod, mod.exports, mockRequire);
  return mod.exports;
};

const canonical = loadTs(source("../../src/lib/ton/ton-proof-challenge.ts"));
const pending = loadTs(
  source("../../src/lib/ton/ton-proof-handoff.ts"),
  (id) => {
    assert.equal(id, "./ton-proof-challenge");
    return canonical;
  },
);
const storage = () => {
  const data = new Map();
  return {
    getItem(key) { return data.get(key) ?? null; },
    setItem(key, value) { data.set(key, String(value)); },
    removeItem(key) { data.delete(key); },
    get size() { return data.size; },
  };
};
const owner = "0000003288";
const host = "gly-efhc.github.io";
const good = () => ({
  adapterId: "tonconnect",
  value: {
    domain: host,
    expires_at: new Date(Date.now() + 600_000).toISOString(),
    ton_proof_payload: "issued-by-backend",
    payload_token: "server-bound-proof-token",
  },
});

test("Android wallet handoff can reuse a valid server-issued proof only in its original tab and owner", () => {
  const tab = storage();
  const initial = good();
  pending.savePendingTonProof(tab, owner, host, initial);
  assert.deepEqual(pending.loadPendingTonProof(tab, owner, host), initial);
  assert.equal(pending.loadPendingTonProof(storage(), owner, host), null);
  pending.clearPendingTonProof(tab);
  assert.equal(tab.size, 0);
});

test("handoff never crosses a Global ID or hostname and drops malformed/expired challenges", () => {
  const tab = storage();
  pending.savePendingTonProof(tab, owner, host, good());
  assert.equal(pending.loadPendingTonProof(tab, "0000003289", host), null);
  assert.equal(tab.size, 0);
  pending.savePendingTonProof(tab, owner, host, good());
  assert.equal(pending.loadPendingTonProof(tab, owner, "other.example"), null);
  assert.equal(tab.size, 0);
  pending.savePendingTonProof(tab, owner, host, {
    ...good(), value: { ...good().value, expires_at: new Date(Date.now() + 1_000).toISOString() },
  });
  assert.equal(tab.size, 0, "nearly-expired proofs must not be persisted");
  pending.savePendingTonProof(tab, "invalid", host, good());
  assert.equal(tab.size, 0);
});

test("handoff accepts unavailable sessionStorage without a blocked wallet connect", () => {
  pending.savePendingTonProof(null, owner, host, good());
  assert.equal(pending.loadPendingTonProof(null, owner, host), null);
  pending.clearPendingTonProof(null);
});

test("React only restores pending proof for a live SDK session and backend still verifies", () => {
  const layout = source("../../src/components/Layout.tsx");
  const ton = source("../../src/lib/tonconnect.ts");
  const helper = source("../../src/lib/ton/ton-proof-handoff.ts");
  assert.match(layout, /loadPendingTonProof\(/);
  assert.match(layout, /savePendingTonProof\(/);
  assert.match(layout, /if \(!globalId \|\| !restoreSettled \|\| !walletSession \|\| hasBoundWallet/);
  assert.match(layout, /walletSession\.raw[\s\S]*?connectItems\?\.tonProof\?\.proof/);
  assert.match(layout, /bindWallet\(proofState\)/);
  assert.match(ton, /bindVerifiedTonConnectWallet/);
  assert.match(ton, /requireGenesisWalletNetwork/);
  assert.doesNotMatch(helper, /localStorage|walletStateInit|signature:|privateKey/);
  assert.match(helper, /window\.sessionStorage/);
});

test("Profile Wallet click cannot pass React event as a non-binding TonConnect mode", () => {
  const wallet = source("../../src/components/profile/ProfileWalletSection.tsx");
  const layout = source("../../src/components/Layout.tsx");
  const profile = source("../../src/features/profile/WebProfilePage.tsx");
  assert.match(wallet, /onClick=\{\(\) => props\.onConnect\(\)\}/);
  assert.doesNotMatch(wallet, /onClick=\{props\.onConnect\}/);
  assert.match(profile, /onConnect=\{ctx\.openWalletConnect\}/);
  assert.match(layout, /const bindingMode = mode !== "execution_fallback";/);
  const connectStart = layout.indexOf("async function openWalletConnect(");
  const connectEnd = layout.indexOf("async function disconnectWalletSession()", connectStart);
  const connect = layout.slice(connectStart, connectEnd);
  assert.match(connect, /bindingMode\s*\? await prepareProof\(\)/);
  assert.match(connect, /if \(bindingMode && !prepared\)/);
  assert.doesNotMatch(connect, /mode === "binding"/);
});
