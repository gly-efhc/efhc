import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {sourceRuntime} from "../helpers/source-runtime.mjs";
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

test("Confirmed quote guards exact D2 cents and rejects malformed representations",()=>{
  const price = sourceRuntime().load("features/browser-shop/shopSelection.ts").sameShopPriceD2;
  for (const [a,b,expected] of [
    ["2","2.00",true],["0.01","0.010",false],["2.01","2.02",false],
    ["9007199254740993.99","9007199254740993.99",true],
    ["9007199254740993.99","9007199254740993.98",false],
    ["-1","-1",false],["NaN","NaN",false],["2e0","2.00",false],
  ]) assert.equal(price(a,b),expected,a+" != "+b);
});

test("External selection transport requires a signed owner-bound request",async()=>{
  const calls=[];
  const runtime=sourceRuntime({overrides:{
    "../lib/api":{apiRequest:async (...args)=>{
      calls.push(args);
      return {global_id:"0000000042",order_id:"123",sku:"EFHC_PACKAGE_10",
        pay_method:"TON",external_amount_display:"2.00",
        external_amount_atomic:"2000000000",expires_at:"2026-11-10T19:00:00+00:00"};
    }},
  }});
  const {selectBrowserShop}=runtime.load("services/browserShopSelection.service.ts");
  const base={sku:"EFHC_PACKAGE_10",quantity:1,pay_method:"TON",client_nonce:"original-key"};
  await assert.rejects(selectBrowserShop(base),/SHOP_SELECTION_AUTH_REQUIRED/);
  assert.equal(calls.length,0,"anonymous choice never creates server order");
  const result=await selectBrowserShop({...base,token:"signed-shop-link"});
  assert.equal(result.global_id,"0000000042");
  assert.equal(String(result.order_id),"123");
  assert.equal(calls.length,1);
  assert.equal(calls[0][0],"/shopfront/select");
  assert.equal(calls[0][1],"POST");
  assert.equal(calls[0][2].body.client_nonce,"original-key");
  await assert.rejects(selectBrowserShop({...base,token:"signed-shop-link",pay_method:"USDT"}),/SHOP_SELECTION_SERVER_MISMATCH/);
});
