import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
const source = readFileSync(resolve(sourceDir, "../features/browser-shop/BrowserShopPage.tsx"), "utf8");

test("package and VIP price DOM must not duplicate the payment method label", () => {
  // Each product price already renders the method in <small>.
  // The inner <b> must contain only the numeric amount, not priceLabel() which includes the method.
  const priceRows = [...source.matchAll(/<span className="efhc-shop-product-price"><small>\{methodLabel\(globalMethod\)\}<\/small><b>\{([^}]+)\}/g)];
  assert.equal(priceRows.length, 3, "one package-list and two VIP price renderers");
  for (const row of priceRows) {
    assert.doesNotMatch(row[1], /priceLabel\(/, "method label would be printed twice");
    assert.match(row[1], /priceAmountOnly\(/, "display-only amount helper required");
  }
  assert.match(source, /function priceAmountOnly\(/);
  assert.match(source, /function checkoutPriceLabel\(/, "checkout formatting must remain unchanged");
});
