import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const readSource = (name) => readFileSync(new URL(`../../src/${name}`, import.meta.url), "utf8");

test("bound Wallet cards use the frame and fill of My Panels without giving the section access to portfolio styles", () => {
  const section = readSource("components/profile/ProfileWalletSection.tsx");
  assert.match(section, /standalone-wallet-list \$\{styles\.boundCards\}/);
  const wallet = readSource("components/profile/wallet-cards.module.css");
  const panels = readSource("styles/panels-layout.css");
  const card = wallet.split(".boundCards :global(.efhc-wallet-entry) {")[1].split("}")[0];
  const material = panels.split("#panelsPortfolioPage .efhc-panel-tile {").at(-1).split("}")[0];
  for (const name of ["border-color", "background-color", "background-image"]) {
    const prop = new RegExp(`${name}\\s*:\\s*([^;]+);`, "u");
    assert.equal(card.match(prop)?.[1].replace(/\s/g, ""), material.match(prop)?.[1].replace(/\s/g, ""), name);
  }
  assert.match(card, /padding:\s*\.74rem;/);
  assert.match(card, /border-radius:\s*\.86rem;/);
  assert.match(wallet, /\.boundCards :global\(\.efhc-wallet-primary-status\)/);
  assert.doesNotMatch(wallet, /@layer|#panelsPortfolioPage|\.efhc-panel-tile/);
});

test("linked Wallet action buttons adopt the Shop Buy treatment without styling the connect action or status badge", () => {
  const wallet = readSource("components/profile/wallet-cards.module.css");
  const shop = readSource("features/browser-shop/BrowserShopPage.tsx");
  const action = wallet.split(".boundCards :global(.standalone-wallet-actions .source-button) {")[1].split("}")[0];
  const buy = shop.split(".efhc-shop-product-buy-action {")[1].split("}")[0];
  for (const name of ["border-radius", "background", "padding", "font-size", "font-weight", "line-height"]) {
    const prop = new RegExp(`^\\s*${name}\\s*:\\s*([^;]+);`, "mu");
    assert.ok(buy.match(prop), name);
    assert.equal(action.match(prop)?.[1], buy.match(prop)?.[1], name);
  }
  assert.match(action, /min-height:\s*36px;/);
  assert.match(wallet, /--wallet-card-frame:\s*rgba\(var\(--efhc-ct-accent-rgb\),\.22\);/);
  assert.match(wallet, /border-color:\s*var\(--wallet-card-frame\)\s*!important;/);
  assert.match(wallet, /:focus-visible\).*\{\s*outline:\s*2px solid var\(--efhc-ct-accent\)/);
  assert.match(action, /color:\s*var\(--tg-text\);/);
  const chroma = readSource("styles/referrals-social-brand-contract.css");
  for (let n = 1; n <= 10; n++) {
    const id = `CT-${String(n).padStart(2, "0")}`;
    const tone = chroma.split(`[data-color-theme-id="${id}"]{`)[1].split("}")[0];
    assert.match(tone, /--efhc-ct-accent-rgb:\d+,\d+,\d+;/, id);
  }
  assert.doesNotMatch(wallet, /efhc-wallet-connect-cta|data-shop-theme/);
});
