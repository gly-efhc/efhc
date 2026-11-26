import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
const load = (path) => fs.readFileSync(new URL("../../src/" + path,import.meta.url),"utf8");
const page = load("features/browser-shop/BrowserShopPage.tsx");
const hook = load("features/browser-shop/useShopPrepayment.ts");
const service = load("services/browserShopPrepayment.service.ts");

test("feature gate keeps existing Pay available and prepayment reuses signed owner contract", () => {
  assert.match(page,/process.env.NEXT_PUBLIC_EFHC_SHOP_PREPAYMENT === "1"/);
  assert.match(page,/issue\?\.payment \?\? await createIntent\.mutateAsync/);
  assert.match(page,/: await purchaseEfhc\.mutateAsync/);
  assert.match(service,/headers: \{ "X-EFHC-Handoff": token \}/);
  assert.match(service,/action === "status" \? \{ key \} : \{\s*key, \.\.\.selection, \.\.\.\(action === "pay"/);
});
test("fence is persisted before transport and reconnect never pays in new lane", () => {
  assert.ok(hook.indexOf("write(ownerSlot.key,JSON.stringify") < hook.indexOf("await callShopPrepayment(action,token"));
  assert.match(hook,/if \(marker\.finalAction && action !== "status"\) return null/);
  assert.match(page,/if \(SHOP_PREPAYMENT_ENABLED\) setCheckout\(queued\);[^\n]*\n\s*else void executePayment\(queued\)/);
  assert.match(page,/if \(SHOP_PREPAYMENT_ENABLED && !issue\?\.payment\) \{/);
  assert.match(service,/String\(payment\.order_id\) !== order_id/);
  assert.match(service,/String\(payment\.intent_id\) !== intent_id/);
  assert.match(page,/String\(parsed\.global_id\) !== scopedShopOwner/);
});
test("Cancel is separate from presentation and unknown state is status-only", () => {
  assert.equal((page.match(/prepayment\.run\("cancel"/g)||[]).length,1);
  assert.match(page,/!checkout \|\| !prepared \|\| prepaymentPending \|\| prepaymentFenced\) return/);
  assert.match(page,/\(!prepared \|\| prepaymentFenced\) && !prepaymentFinished/);
  assert.match(page,/onMouseDown=\{\(event\) => \{ if \(event.target === event.currentTarget && !busy\) setCheckout\(null\)/);
});

test("only matching authoritative review controls rendered amount and final Pay", () => {
  assert.match(page,/useShopPrepayment\(SHOP_PREPAYMENT_ENABLED, scopedShopOwner, token, Boolean\(checkout\), checkout \? prepareSelection\(checkout\) : null\)/);
  assert.match(page,/authoritativeAmountLabel \?\? checkoutPriceLabel\(checkout\)/);
  assert.match(hook,/scope === marker.scope/);
  assert.match(hook,/state.review\?\.review_id !== review.review_id/);
  assert.match(service,/!matchesExternalShopReview\(reviewed, payment\)/);
  assert.match(service,/action === "pay" \? \{ review_id: reviewed\?\.review_id \}/);
});
