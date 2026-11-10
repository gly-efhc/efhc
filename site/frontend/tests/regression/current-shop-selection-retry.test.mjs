import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { sourceRuntime } from "../helpers/source-runtime.mjs";

const read = (path) => readFileSync(fileURLToPath(new URL("../../src/" + path, import.meta.url)), "utf8");

test("Shop selection guard anchors one 15-minute window at the original Buy click", () => {
  const { shopSelectionWindowOpen, SHOP_SELECTION_WINDOW_MS } =
    sourceRuntime().load("features/browser-shop/shopSelection.ts");
  assert.equal(SHOP_SELECTION_WINDOW_MS, 900_000);
  const start = 1_700_000_000_000;
  assert.equal(shopSelectionWindowOpen(start, start), true);
  assert.equal(shopSelectionWindowOpen(start, start + 899_999), true);
  assert.equal(shopSelectionWindowOpen(start, start + 900_000), false);
  assert.equal(shopSelectionWindowOpen(start, start - 1), false);
  for (const invalid of [0,-1,NaN,Infinity]) assert.equal(shopSelectionWindowOpen(invalid,start), false);
});
test("Independent Buy uses a fresh key; post-link continuation alone can reuse it", () => {
  const { canResumeShopChoice } = sourceRuntime().load("features/browser-shop/shopSelection.ts");
  const previous = {sku:"EFHC_PACKAGE_10",method:"TON",choiceOwner:"0000000042",resumeAfterLink:false};
  const same = {sku:"EFHC_PACKAGE_10",method:"TON"};
  assert.equal(canResumeShopChoice(previous,same,"0000000042"),false);
  assert.equal(canResumeShopChoice({...previous,resumeAfterLink:true},same,"0000000042"),true);
  assert.equal(canResumeShopChoice({...previous,resumeAfterLink:true},same,"0000000099"),false);
  assert.equal(canResumeShopChoice({...previous,resumeAfterLink:true},{...same,method:"USDT"},"0000000042"),false);
  assert.equal(canResumeShopChoice({...previous,resumeAfterLink:true},{...same,sku:"EFHC_PACKAGE_50"},"0000000042"),false);
  assert.equal(canResumeShopChoice(null,same,"0000000042"),false);
});

test("Shop one selection keeps the same nonce on repeated external and EFHC attempts", () => {
  const code = read("features/browser-shop/BrowserShopPage.tsx");
  assert.match(code, /choiceKey: reuse && previous/);
  assert.match(code, /selectedAtMs: reuse && previous/);
  assert.match(code, /rememberShopChoice\(chosen\)/);
  assert.match(code, /rememberShopChoice\(selection, true\)/);
  assert.match(code, /canResumeShopChoice\(previous,/);
  assert.match(code, /clearShopChoice\(\)/);
  assert.match(code, /client_nonce: selection\.choiceKey/);
  assert.match(code, /idempotencyKey: selection\.choiceKey/);
  assert.doesNotMatch(code, /client_nonce: globalThis\.crypto\?\.randomUUID/);
  assert.doesNotMatch(code, /idempotencyKey: newIdempotencyKey\(\)/);
  assert.match(code, /intentCreated && isUserRejected\(caught\) && shopSelectionWindowOpen\(selection\.selectedAtMs\)/);
  assert.match(code, /selection\.choiceOwner !== linkedGlobalId/);
  assert.match(code, /SHOP_SELECTION_WINDOW_MS - \(Date\.now\(\) - checkout\.selectedAtMs\)/);
  assert.match(code, /navigator\.onLine === false/);
});
