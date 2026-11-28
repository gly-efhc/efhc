import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
const frontend = fileURLToPath(new URL('../../../frontend/', import.meta.url));
const read = (p) => fs.readFileSync(new URL('../../../frontend/' + p, import.meta.url), "utf8");
const pkg = JSON.parse(read("package.json"));
const lock = JSON.parse(read("package-lock.json"));
test("public Pages: official TON Connect dependencies agree with lockfile", () => {
  for (const name of ["@tonconnect/sdk", "@tonconnect/ui-react"]) {
    assert.ok(pkg.dependencies[name]);
    assert.equal(lock.packages[""].dependencies[name], pkg.dependencies[name]);
    assert.ok(lock.packages["node_modules/" + name].version);
  }
});
test("public Pages: official provider and adapter; no shadow compatibility module or custom chooser", () => {
  const provider = read("src/lib/wallet-provider/WalletProvider.tsx");
  const adapter = read("src/lib/wallet-provider/adapters/TonConnectAdapter.ts");
  const cfg = JSON.parse(read("tsconfig.json"));
  assert.equal(cfg.compilerOptions.paths?.["@tonconnect/ui-react"], undefined);
  assert.equal(fs.existsSync(frontend + "src/lib/vendor/tonconnect-ui-react-compat.tsx"), false);
  assert.equal(fs.existsSync(frontend + "src/components/wallet/TonConnectWalletChooser.tsx"), false);
  assert.match(provider, /import\("@tonconnect\/ui-react"\)/);
  assert.match(provider, /useIsConnectionRestored/);
  assert.match(adapter, /await ui\.openModal\(\)/);
  assert.match(adapter, /bindVerifiedTonConnectWallet/);
  assert.match(adapter, /ui\.setConnectionNetwork\(GENESIS_WALLET_CHAIN\)/);
});
