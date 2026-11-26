import assert from "node:assert/strict";
import test from "node:test";
import {matchesExternalShopReview as matches,readShopReview as review} from "../../src/features/browser-shop/shopCheckoutReview.ts";
const id = "f".repeat(64);
const snapshot = (asset,amount) => review({review_id:id,quote:{asset,amount}});
const payment = (pay_method,amount,external_amount_atomic,external_decimals) => ({pay_method,amount,external_amount_atomic,external_decimals});
test("accept exact TON/USDT amounts and insignificant trailing zeros using integer arithmetic", () => {
  assert.ok(matches(snapshot("TON","9007199254740993.001"), payment("TON","9007199254740993.0010","9007199254740993001000000",9)));
  assert.ok(matches(snapshot("USDT","1.25"), payment("USDT","1.250000","1250000",6)));
});
test("block wallet handoff for changed decimal, wrong asset, number coercion, scale or atomics", () => {
  const quoted=snapshot("USDT","1.25");
  for (const p of [
    payment("USDT","1.26","1250000",6), payment("USDT",1.25,"1250000",6),
    payment("USDT","1.25",1250000,6), payment("USDT","1.25","1250001",6),
    payment("USDT","1.25","1250000",9), payment("TON","1.25","1250000",6),
  ]) assert.equal(matches(quoted,p),false);
});
test("reject malformed review and treat EFHC review as nonsignable", () => {
  for (const bad of ["","0","-1","1e2","1,2","01","1.1234567"]) assert.equal(snapshot("USDT",bad),null);
  assert.equal(review({review_id:"abc",quote:{asset:"TON",amount:"1.00"}}),null);
  assert.equal(matches(snapshot("EFHC","10.00000000"),payment("EFHC","10","1000000000",8)),false);
});
