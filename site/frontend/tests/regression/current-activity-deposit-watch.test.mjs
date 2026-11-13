import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const file = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("existing Check button starts server-owned on-chain reconciliation, not another wallet transfer", () => {
  const modal = file("../../src/components/DepositModal.tsx");
  const service = file("../../src/services/directDeposit.service.ts");
  assert.match(modal, /data-direct-deposit-action="check-status"/);
  assert.match(modal, /onClick=\{\(\) => void checkDepositOnChain\(\)\}/);
  assert.match(modal, /await runSharedDepositCheck\(\)/);
  assert.match(modal, /setOpenedAt\(new Date\(Date\.now\(\) - 7 \* 24 \* 3600 \* 1000\)\.toISOString\(\)\)/);
  assert.match(service, /apiRequest<unknown>\("\/deposit\/direct-check", "POST"\)/);
  const checkHandler = modal.slice(modal.indexOf("async function checkDepositOnChain()"),
                                   modal.indexOf("async function sendDirectEfhcDeposit()"));
  assert.doesNotMatch(checkHandler, /sendTransaction|sendDirectEfhcDeposit|buildEfhcDirectDepositTx/);
});

test("shared watcher is driven by authenticated app activity, not a polling timer", () => {
  const layout = file("../../src/components/Layout.tsx");
  assert.match(layout, /authSession\.status !== "authenticated"/);
  assert.match(layout, /document\.visibilityState === "hidden"/);
  assert.match(layout, /document\.addEventListener\("visibilitychange", onActivity\)/);
  assert.match(layout, /void runSharedDepositCheck\(\)/);
  const activity = layout.slice(layout.indexOf("// One active authenticated visitor"),
                                layout.indexOf("const \[bottomNavViewportHeight"));
  assert.doesNotMatch(activity, /setInterval|setTimeout/);
});

test("GENESIS TEST exact deposit-check POST keeps guest CSRF and does not grant generic financial writes", () => {
  const transport = file("../../src/demo/transport.ts");
  assert.match(transport, /const guestActivityWrite/);
  assert.match(transport, /normalized\.split\("\?"\)\[0\] === "\/api\/deposit\/direct-check"/);
  assert.match(transport, /guestTonProofWrite \|\| guestActivityWrite/);
  assert.match(transport, /headers\["X-EFHC-Test-CSRF"\] = await sessionCsrf\(\)/);
});
