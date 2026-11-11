import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

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
  assert.match(adapter, /ui\.setConnectionNetwork\(TON_TESTNET_CHAIN\)/);
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
