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
