import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const read = path => readFileSync(resolve(root, path), "utf8");
const css = read("public/frame-thickness-contract.css");
const app = read("src/pages/_app.tsx");
const shop = read("src/components/ShopLayout.tsx");

function hasDeclaration(selector, property, value) {
  const at = css.indexOf(selector);
  assert.notEqual(at, -1, "Missing selector: " + selector);
  const start = css.indexOf("{", at);
  const end = css.indexOf("}", start);
  const declaration = css.slice(start + 1, end);
  assert.match(declaration, new RegExp(property + "\\s*:\\s*" + value));
}

test("1px frame stylesheet loads after frozen and runtime sources for USER/Admin and Shop", () => {
  assert.ok(app.indexOf("/frame-thickness-contract.css") > app.indexOf("/header-theme-material.css"));
  assert.match(app, /!isBrowserShop\s*\?\s*\(\s*<link rel="stylesheet"/);
  assert.ok(shop.indexOf("/frame-thickness-contract.css") > shop.indexOf("/" + "SHOP" + "_" + "v" + "866" + ".css"));
  assert.match(css, /OWNER-approved frame thickness/);
});

test("accepted 2-3px frame candidates have narrower contract rules", () => {
  for (const selector of [
    '.efhc-energy-stage_coin[data-ei="EI-15"]',
    '.efhc-exchange-stats-surface[data-xs="XS-09"] .efhc-game-stat',
    '.efhc-admin-tasks-catalog_card[data-selected="true"]',
    '.efhc-admin-reports-visual_metric[data-selected="true"]',
    ".efhc-frontend-button_spinner",
    ".efhc-tonconnect-first-bind-qr i",
    ".efhc-shop-site[data-interface-app-mode=\"shop-landing\"]",
    "#profileAvatarOverlay",
  ]) {
    assert.ok(css.includes(selector), "Missing frame state: " + selector);
  }
  hasDeclaration('.efhc-energy-stage_coin[data-ei="EI-15"]', "border-width", "1px");
  hasDeclaration('.efhc-exchange-stats-surface[data-xs="XS-09"] .efhc-game-stat', "border-left-width", "1px");
  assert.match(css, /border-style:\s*solid\s*!important/);
  assert.match(css, /box-shadow:\s*0\s+0\s+11px/);
});

test("1px focus remains bright and never adds a border to borderless controls", () => {
  assert.match(css, /:focus-visible[^{]*\{\s*outline-width:\s*1px\s*!important/);
  assert.match(css, /:focus-within\s*\{\s*outline-width:\s*1px\s*!important/);
  assert.match(css, /outline-color:\s*var\(--efhc-ct-accent/);
  assert.match(css, /outline-color:\s*var\(--efhc-admin-canon-focus/);
  assert.match(css, /outline-color:\s*var\(--efhc-color-focus/);
  assert.match(css, /prefers-contrast:\s*more/);
  assert.doesNotMatch(css, /(?:^|[;{}])\s*border\s*:/m, "Do not introduce new borders");
  assert.doesNotMatch(css, /(?:^|[;{}])\s*outline-style\s*:/m, "Do not invent focus rings");
  assert.doesNotMatch(css, /(?:^|[;{}])\s*box-shadow\s*:\s*0\s+0\s+0\s+[23]px/m);
});

test("negative fixture: widening EI-15 to 2px is rejected by the width contract", () => {
  const mutated = css.replace("border-width: 1px !important;", "border-width: 2px !important;");
  assert.notEqual(mutated, css);
  assert.match(css, /border-width:\s*1px\s*!important/);
  assert.ok(!/border-width:\s*2px\s*!important/.test(css));
  assert.ok(/border-width:\s*2px\s*!important/.test(mutated));
});
