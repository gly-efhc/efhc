import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";
import ts from "typescript";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const get = (name) => readFileSync(resolve(root, name), "utf8");
const pkg = JSON.parse(get("package.json"));
const lock = JSON.parse(get("package-lock.json"));
const cfg = JSON.parse(get("tsconfig.json"));

test("official UI is installed directly, not shadowed by a vendor alias", () => {
  assert.equal(pkg.dependencies["@tonconnect/ui-react"], "5.0.1");
  assert.equal(pkg.dependencies["@tonconnect/sdk"], "5.0.0");
  assert.equal(lock.packages[""].dependencies["@tonconnect/ui-react"], "5.0.1");
  assert.equal(cfg.compilerOptions.paths?.["@tonconnect/ui-react"], undefined);
  assert.equal(
    existsSync(resolve(root, "src/lib/vendor/tonconnect-ui-react-compat.tsx")),
    false,
  );
});

test("one official client-only provider preserves EFHC protected shell during SSR", () => {
  const src = get("src/lib/wallet-provider/WalletProvider.tsx");
  assert.match(src, /import\("@tonconnect\/ui-react"\)/);
  assert.match(src, /ssr:\s*false/);
  assert.match(src, /DISCONNECTED_WALLET_CONTEXT/);
  assert.match(src, /OfficialTonConnectProvider/);
  assert.match(src, /useIsConnectionRestored/);
});

test("connect uses the official UI modal without the former custom chooser", () => {
  const layout = get("src/components/Layout.tsx");
  const adapter = get("src/lib/wallet-provider/adapters/TonConnectAdapter.ts");
  assert.equal(
    existsSync(resolve(root, "src/components/wallet/TonConnectWalletChooser.tsx")),
    false,
  );
  assert.doesNotMatch(layout, /TonConnectWalletChooser/);
  const browserShop = get("src/features/browser-shop/BrowserShopPage.tsx");
  assert.doesNotMatch(browserShop, /TonConnectWalletChooser/);
  assert.match(browserShop, /await connectWallet\(\)/);
  const primary = get("src/lib/wallet-provider/primaryWalletRouting.ts");
  assert.match(primary, /await args\.connectWallet\(\)/);
  assert.doesNotMatch(primary, /args\.connectWallet\(target\)/);
  assert.match(adapter, /await ui\.openModal\(\)/);
  assert.doesNotMatch(adapter, /ui\.connectWallet\(wallet\.walletKey\)/);
  assert.match(adapter, /ui\.setConnectionNetwork\(GENESIS_WALLET_CHAIN\)/);
});

test("additional verified wallet connection replaces only the active transport session", () => {
  const profile = get("src/components/profile/ProfileWalletSection.tsx");
  const layout = get("src/components/Layout.tsx");
  const webProfile = get("src/features/profile/WebProfilePage.tsx");
  assert.match(profile, /data-wallet-provider-action="connect"/);
  assert.doesNotMatch(profile, /WalletConnectBanner/);
  assert.match(profile, /wallet\.is_active && wallet\.proof_verified === true/);
  assert.equal((profile.match(/<Button/g) || []).length, 1, "v866 wallet view has one connect action");
  assert.match(profile, /\{t\("wallet\.connect_button"\)\}/);
  assert.match(layout, /if \(walletSession && mode === "binding"\) \{/);
  assert.match(layout, /await disconnectWallet\(\)/);
  assert.match(layout, /setProofState\(null\)/);
  assert.match(layout, /const prepared = mode === "binding"\s*\? await prepareProof\(\)/);
  assert.match(webProfile, /label=\{t\("wallet\.title"\)\}/);
  assert.doesNotMatch(profile, /<input[^>]*wallet.address/i);
});

test("real wallet Proof, chain and financial-send gates remain separate", () => {
  const adapter = get("src/lib/wallet-provider/adapters/TonConnectAdapter.ts");
  const proof = get("src/lib/tonconnect.ts");
  const testnet = get("src/lib/ton/testnet-guard.ts");
  assert.match(adapter, /bindVerifiedTonConnectWallet/);
  assert.match(proof, /checkTonProofEnvelope/);
  assert.match(proof, /requireGenesisWalletNetwork/);
  assert.match(proof, /requireGenesisTransactionNetwork/);
  assert.match(testnet, /TON_TESTNET_CHAIN\s*=\s*"-3"/);
  assert.match(proof, /TONCONNECT_TRANSACTION_RESPONSE_INVALID/);
});

test("TON Proof is prepared once on explicit connection, never rotated by session effects", () => {
  const src = get("src/components/Layout.tsx");
  assert.equal([...src.matchAll(/\bprepareProof\s*\(/g)].length, 1);
  assert.match(src, /mode === "binding"\s*\? await prepareProof\(\)/);
  assert.match(src, /setProofState\(prepared\)/);
});

test("official TON hydration never replaces the already-mounted application tree", () => {
  const src = get("src/lib/wallet-provider/WalletProvider.tsx");
  assert.match(src, /<WalletProviderRuntime runtime=\{tonRuntime\}>/);
  assert.match(src, /\{props\.children\}\s*\{hydrated\s*\?\s*\(/);
  assert.match(src, /<OfficialTonConnectProvider[\s\S]*?<TonConnectRuntimeBridge/);
  assert.match(src, /function TonConnectRuntimeBridge\(/);
  assert.match(src, /function WalletProviderRuntime\(/);
  assert.match(src, /value=\{props\.runtime \? value : DISCONNECTED_WALLET_CONTEXT\}/);
  assert.doesNotMatch(src, /if \(!hydrated\)\s*\{[\s\S]*?return \(\s*<WalletProviderContext/);
});

test("EFHC owns Android Back and binding requires a matching server challenge", () => {
  const provider = get("src/lib/wallet-provider/WalletProvider.tsx");
  const layout = get("src/components/Layout.tsx");
  const proof = get("src/lib/tonconnect.ts");
  assert.match(provider, /enableAndroidBackHandler=\{false\}/);
  assert.match(layout, /if \(mode === "binding" && !prepared\) \{/);
  assert.match(layout, /setProofState\(prepared\)/);
  assert.match(proof, /String\(proof\.payload \?\? ""\) !== proofState\.ton_proof_payload/);
  assert.match(proof, /return await connectVerifiedTonWallet/);
});

test("public Pages manifest identifies its actual hosted app, not a different domain", () => {
  const manifest = JSON.parse(get("public/tonconnect-manifest.json"));
  const origin = "https://gly-efhc.github.io/efhc";
  assert.deepEqual(Object.keys(manifest).sort(), [
    "iconUrl", "name", "privacyPolicyUrl", "termsOfUseUrl", "url",
  ]);
  assert.equal(manifest.url, origin);
  assert.equal(manifest.iconUrl, origin + "/icon.png");
  assert.equal(manifest.termsOfUseUrl, origin + "/web-profile?legal=terms");
  assert.equal(manifest.privacyPolicyUrl, origin + "/web-profile?legal=privacy");
});

test("live challenge preflight rejects wrong domain, stale payloads and expiry", () => {
  // Run the actual TypeScript helper, not a duplicate JS interpretation.
  const source = get("src/lib/ton/ton-proof-challenge.ts");
  const js = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  const exports = {};
  vm.runInNewContext(js, { exports }, { timeout: 1000 });
  const preflight = exports.assertFreshTonProofChallenge;
  assert.equal(typeof preflight, "function");

  const now = Date.parse("2026-11-12T00:00:00.000Z");
  const challenge = {
    ton_proof_payload: "server-issued-challenge",
    payload_token: "server-signed-token",
    domain: "gly-efhc.github.io",
    expires_at: new Date(now + 600_000).toISOString(),
  };
  assert.doesNotThrow(() => preflight(challenge, "gly-efhc.github.io", now));
  assert.doesNotThrow(() => preflight(challenge, "GLY-EFHC.GITHUB.IO.", now));
  assert.throws(() => preflight({ ...challenge, domain: "efhc.app" }, "gly-efhc.github.io", now), /TON_PROOF_DOMAIN_MISMATCH/);
  assert.throws(() => preflight(challenge, "efhc.app", now), /TON_PROOF_DOMAIN_MISMATCH/);
  assert.throws(() => preflight({ ...challenge, expires_at: "invalid-date" }, "gly-efhc.github.io", now), /TON_PROOF_CHALLENGE_EXPIRED/);
  assert.throws(() => preflight({ ...challenge, expires_at: new Date(now + 29_000).toISOString() }, "gly-efhc.github.io", now), /TON_PROOF_CHALLENGE_EXPIRED/);
  assert.throws(() => preflight({ ...challenge, payload_token: "" }, "gly-efhc.github.io", now), /TON_PROOF_CHALLENGE_INVALID/);
  assert.throws(() => preflight({ ...challenge, ton_proof_payload: "" }, "gly-efhc.github.io", now), /TON_PROOF_CHALLENGE_INVALID/);
  assert.match(get("src/lib/tonconnect.ts"), /assertFreshTonProofChallenge\(out, window\.location\.hostname\)/);
});

test("Browser Shop does not open a wallet modal when a new binding lacks a proof", () => {
  const src = get("src/features/browser-shop/BrowserShopPage.tsx");
  const from = src.indexOf('if (requireProof && !proof) {');
  const until = src.indexOf('await connectWallet();', from);
  assert.ok(from >= 0 && until > from);
  const gate = src.slice(from, until);
  assert.match(gate, /setTonConnectBindingRequested\(false\)/);
  assert.match(gate, /setPendingPrimaryPayment\(null\)/);
  assert.match(gate, /return;/);
  assert.match(src, /isGenesisTestRuntime\(\)[\s\S]*?\? GENESIS_JSON_RPC_ENDPOINT/);
  const networkPolicy = get("src/lib/ton/testnet-guard.ts");
  assert.match(networkPolicy, /export const TON_TESTNET_JSON_RPC_ENDPOINT/);
  assert.match(networkPolicy, /endpoint !== expected/);
  assert.match(networkPolicy, /export const GENESIS_JSON_RPC_ENDPOINT/);
  assert.match(networkPolicy, /TON_MAINNET_JSON_RPC_ENDPOINT/);
});
