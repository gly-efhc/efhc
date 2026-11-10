import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
const read = name => readFileSync(fileURLToPath(new URL("../../src/"+name,import.meta.url)),"utf8");

test("Original Buy click starts owner-scoped server quote without changing Shop markup",()=>{
  const page = read("features/browser-shop/BrowserShopPage.tsx");
  assert.match(page,/void ensureExternalShopSelection\(chosen\)\.catch\(\(\) => undefined\)/);
  assert.match(page,/const selected = await ensureExternalShopSelection\(selection\)/);
  assert.match(page,/serverSelectionPromisesRef\.current\.get\(selection\.choiceKey\)/);
  assert.match(page,/selectShop\.mutateAsync\(/);
  assert.match(page,/client_nonce: selection\.choiceKey/);
  assert.match(page,/selected\.global_id !== linkedGlobalId/);
  assert.match(page,/Date\.parse\(selected\.expires_at\)/);
  assert.match(page,/shopSelectionWindowOpen\(selection\.selectedAtMs\)/);
  assert.match(page,/navigator\.onLine === false/);
  assert.doesNotMatch(page,/client_nonce: newIdempotencyKey\(\)/);
});

test("Server-confirmed quote is a prerequisite to creating signed PaymentIntent",()=>{
  const page = read("features/browser-shop/BrowserShopPage.tsx");
  const attempt=page.slice(page.indexOf("async function performExternalPayment("),page.indexOf("async function executePayment("));
  assert.match(attempt,/await ensureExternalShopSelection\(selection\)/);
  assert.ok(attempt.indexOf("await ensureExternalShopSelection(selection)")<attempt.indexOf("await createIntent.mutateAsync"),"selection must precede new payment");
  const service=read("services/browserShopSelection.service.ts");
  assert.match(service,/"\/shopfront\/select", "POST"/);
  assert.match(service,/selectionResponseSchema\.parse\(result\)/);
  assert.match(service,/SHOP_SELECTION_AUTH_REQUIRED/);
  assert.match(service,/parsed\.sku !== body\.sku \|\| parsed\.pay_method !== body\.pay_method/);
  const query=read("queries/useBrowserShop.ts");
  assert.match(query,/export function useBrowserShopSelect/);
});
