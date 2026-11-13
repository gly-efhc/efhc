import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const read = (name) => readFileSync(resolve(root, name), "utf8");
const css = read("src/styles/globals.css");
const catalog = JSON.parse(read("src/design-system/color-theme-registry.json")).themes;
const reference = JSON.parse(read("src/design-system/theme03-chroma.json")).roles;
const start = "/* Shared USER semantic material contract:";
const end = "/* End shared USER semantic material contract. */";
const segment = css.split(start)[1]?.split(end)[0];

test("all ten USER palettes map to the same Theme03 semantic role architecture", () => {
  assert.ok(segment, "Missing active shared material bridge");
  assert.equal(catalog.length, 10, "Ten canonical colors required");
  assert.equal(Object.keys(reference).length, 18, "Reference vector must contain 18 roles");

  for (const theme of catalog) {
    const selector = `[data-color-theme-id="${theme.id}"]`;
    const startAt = segment.indexOf(selector);
    assert.ok(startAt >= 0, `Missing ${theme.id} palette`);
    const block = segment.slice(segment.indexOf("{", startAt) + 1, segment.indexOf("}", startAt));
    assert.ok(block.includes(`--efhc-ct-accent:${theme.accent};`), `Wrong ${theme.id} accent`);
    const rgb = [1, 3, 5].map(i => parseInt(theme.accent.slice(i, i + 2), 16)).join(",");
    assert.ok(block.includes(`--efhc-ct-accent-rgb:${rgb};`), `Wrong ${theme.id} RGB`);
  }

  for (const name of Object.keys(reference)) {
    const property = "--efhc-color-" + name.replace(/[A-Z]/g, c => "-" + c.toLowerCase());
    assert.ok(segment.includes(property + ":"), `Missing common material role ${name}`);
  }
});

test("material base follows Theme03 and gold stays decorative rather than changing geometry", () => {
  assert.ok(segment.includes('--efhc-ct-accent:#E5BF58;'));
  for (const [name, target] of Object.entries({
    canvas: reference.canvas, page: reference.page, chrome: reference.chrome,
    hero: reference.hero, card: reference.card, inset: reference.inset,
    shadow: reference.shadow, text: reference.text, textMuted: reference.textMuted,
  })) {
    const prop = "--efhc-color-" + name.replace(/[A-Z]/g, c => "-" + c.toLowerCase());
    assert.ok(segment.includes(`${prop}:${target};`), `Theme03 material mismatch: ${name}`);
  }
  assert.ok(segment.includes("--efhc-route-surface:var(--efhc-color-page);"));
  assert.ok(segment.includes("--efhc-route-surface-raised:var(--efhc-color-hero);"));
  assert.ok(css.indexOf(start) > css.indexOf('[data-global-theme-id="05"]'),
    "Shared role bridge must take precedence over the old translucent gold surfaces");
  assert.doesNotMatch(segment, /!important|border-radius\s*:|(?:^|[;{}\n])\s*(?:padding|margin|width|height|display|position|font-size)\s*:/,
    "Color/theme role bridge must not own geometry or alter design variants");
});

test("late shell adapter has fully resolved, acyclic color and elevation inputs", () => {
  const shell = read("public/user-shell.css");
  const pairs = [
    ["--efhc-color-border:var(--efhc-ct-border);", "--efhc-ct-border:"],
    ["--efhc-color-border-strong:var(--efhc-ct-border-strong);", "--efhc-ct-border-strong:"],
    ["--efhc-color-accent-soft:var(--efhc-ct-accent-soft);", "--efhc-ct-accent-soft:"],
    ["--efhc-color-accent-strong:var(--efhc-ct-accent-strong);", "--efhc-ct-accent-strong:"],
    ["--efhc-color-focus:var(--efhc-ct-focus);", "--efhc-ct-focus:"],
    ["--efhc-color-shadow:var(--efhc-common-elevation-shadow);", "--efhc-common-elevation-shadow:"],
  ];
  for (const [adapter, source] of pairs) {
    assert.ok(shell.includes(adapter), "The source adapter unexpectedly changed: " + adapter);
    assert.ok(segment.includes(source), "Missing upstream source for " + adapter);
  }
  assert.doesNotMatch(segment, /--efhc-ct-(?:border|border-strong|accent-soft|accent-strong|focus):var\(--efhc-color-/,
    "A downstream role must not feed its own upstream alias");
});

test("common USER text metrics do not depend on legacy theme 01..03", () => {
  const selector = '[data-interface-app-mode="user"][data-color-theme-id] :is(.efhc-main,.efhc-shop-layout_main)';
  assert.ok(css.includes(selector), "All ten themes must share USER text sizing");
  const offset = css.indexOf(selector);
  const block = css.slice(css.indexOf("{", offset) + 1, css.indexOf("}", offset));
  assert.match(block, /font-size:\s*1rem\s*;/);
  assert.match(block, /line-height:\s*1\.5\s*;/);
  assert.doesNotMatch(css, /\[data-global-theme-id="03"\] \.efhc-main,\s*\[data-global-theme-id="01"\] \.efhc-shop-layout_main/);
});

test("the Theme03 reference is exact and Admin remains outside the USER color bridge", () => {
  for (const name of ["active", "accentSoft", "accentStrong", "glow", "focus"]) {
    const prop = "--efhc-color-" + name.replace(/[A-Z]/g, c => "-" + c.toLowerCase());
    assert.ok(segment.includes(`${prop}:${reference[name]};`),
      `Theme03 exact qualified role changed: ${name}`);
  }
  assert.match(segment, /\[data-interface-app-mode="user"\]\[data-color-theme-id\]/);
  assert.doesNotMatch(segment, /\[data-interface-app-mode="admin"\]|\.efhc-admin-/);
  const app = read("src/components/interface-settings/InterfaceCustomizationProvider.tsx");
  assert.match(app, /const nextVariants = nextColorThemeId === currentColorId \? sourceVariants/);
  assert.match(app, /PB: COLOR_THEME_PROGRESS_STARTER/);
  assert.match(app, /RP: COLOR_THEME_PROGRESS_STARTER/);
});


test("achievement heading and withdrawal history keep CT styling without repainting Theme03 exchange buttons", () => {
  assert.equal(catalog.length, 10);
  const section = css.split("/* USER achievement caption transparency and active CT history materials. */")[1];
  assert.ok(css.includes("@layer efhc-ct-route-accents {"));
  assert.ok(section, "Missing limited USER accent contract");
  assert.match(section, /\[data-referrals-achievements="visible"\]/);
  assert.match(section, /background-color:\s*transparent\s*!important/);
  assert.doesNotMatch(section, /#efhc-main-content \.efhc-exchange-shell/,
    "Exchange buttons must retain their accepted Theme03 appearance, not arbitrary CT overrides");
  assert.match(section, /\[data-withdraw-history-balance-type-label="semantic"\]\.efhc-withdraw-history-row/);
  assert.match(section, /background-color:\s*rgba\(var\(--efhc-ct-accent-rgb\),\.09\)/);
  assert.doesNotMatch(section, /(?:width|height|padding|margin|border-radius|font-size|display|position|grid-template-columns)\s*:/,
    "Only colors and achievement heading overlays may be changed");
  const exchange = read("src/components/ExchangePanel.tsx");
  const exchangeRoute = read("src/pages/exchange.tsx");
  const withdraw = read("src/pages/withdraw.tsx");
  // Exact spacing is now owned by the existing Exchange action-surface layout.
  assert.match(exchange, /className="w-full efhc-theme03-cta"/);
  assert.match(css, /\.efhc-exchange-action-surface \[data-exchange-submit-action="true"\] \{\s*margin-top: 0\.65rem;/);
  assert.match(exchange, /data-exchange-submit-action="true"/);
  assert.doesNotMatch(exchangeRoute, /data-exchange-history-link|openProfile\("history"\)|exchange\.open_history/);
  assert.doesNotMatch(exchangeRoute, /history_profile_note|efhc-exchange-history-boundary|<GameNotice|TelegramEmptyState/);
  assert.doesNotMatch(exchange, /\{normalizedAmount\} EFHCm/);
  assert.match(exchangeRoute, /className="w-full efhc-exchange-withdraw-button efhc-theme03-cta"/);
  assert.match(withdraw, /data-withdraw-history-balance-type-label="semantic"/);
});



test("nine CT Exchange actions reuse the exact Theme03 material without touching protected Theme03", () => {
  const source = read("src/styles/theme03-panels-exchange-chroma.css");
  const canonical = /\.efhc-independent-shell\[data-interface-app-mode="user"\]\[data-global-theme-id="03"\] \.efhc-theme03-cta \{([\s\S]*?)\n\}/.exec(source);
  const mirrored = /\.efhc-independent-shell\[data-interface-app-mode="user"\]\[data-color-theme-id\]:not\(\[data-color-theme-id="CT-03"\]\) \.efhc-exchange-shell \.efhc-theme03-cta:not\(:disabled\) \{([\s\S]*?)\n\}/.exec(css);
  assert.ok(canonical && mirrored, "Missing one of the two canonical CTA material rules");
  assert.equal(mirrored[1], canonical[1], "Material differs from original Theme03");
  assert.doesNotMatch(mirrored[1], /!important|(?:width|height|padding|margin|border-radius|font-size|display|position)\s*:/,
    "Do not override independent Exchange geometry or force CSS precedence");
});


test("Panels activation display numbering resolves to the original ordered physical styles", () => {
  const registry = read("src/lib/interfaceVariantRegistry.ts");
  const panels = read("src/pages/panels.tsx");
  assert.match(registry, /PA:\s*numbered\("PA",\s*6\)/);
  assert.match(registry, /"PA":\{"PA-03":"PA-04","PA-04":"PA-10","PA-05":"PA-11","PA-06":"PA-12"\}/);
  assert.match(registry, /return INTERFACE_VARIANT_STYLE_BINDINGS\[group\]\[canonical\] \|\| canonical/);
  assert.match(panels, /useInterfaceVariantSurface<HTMLDivElement>\("PA"\)/);
  assert.match(panels, /data-pa=\{activationSurface\.variant\}/);
  const authoredFrame = /\.efhc-panels-activation-card\[data-pa="PA-04"\] > \.grid > \.grid \{([^}]+)\}/.exec(css);
  assert.ok(authoredFrame, "The third displayed template must retain its existing physical frame");
  assert.match(authoredFrame[1], /border:\s*1px solid rgba\(var\(--efhc-ct-accent-rgb\),\s*\.15\)/);
  const legacyOverride = /\[data-global-theme-id="04"\] \.efhc-panels-activation-card\[data-pa="PA-04"\]>.grid>.grid\{([^}]+)\}/.exec(css);
  assert.ok(legacyOverride, "Legacy Theme04 must not override the selected color");
  assert.match(legacyOverride[1], /border-color:rgba\(var\(--efhc-ct-accent-rgb\),\.15\)!important/);
});

test("Exchange removes duplicate history entry while retaining withdrawal and conversion", () => {
  const exchangeRoute = read("src/pages/exchange.tsx");
  assert.doesNotMatch(exchangeRoute, /data-exchange-history-link|openProfile\("history"\)|exchange\.open_history/);
  assert.match(exchangeRoute, /<ExchangePanel/);
  assert.match(exchangeRoute, /exchangeMutation\.mutateAsync/);
  assert.match(exchangeRoute, /data-exchange-withdraw-entrypoint="restored-canonical"/);
});

test("Exchange geometry reset stays on Exchange; Withdraw retains source grid", () => {
  const exchangeRoute = read("src/pages/exchange.tsx");
  const withdrawRoute = read("src/pages/withdraw.tsx");
  assert.match(css, /\.efhc-exchange-panel \{\s*display:\s*grid;\s*gap:\s*0\.65rem;/);
  assert.match(css, /\.efhc-exchange-shell \.efhc-exchange-panel \{\s*display:\s*contents;/);
  assert.match(exchangeRoute, /className="efhc-exchange-shell"/);
  assert.match(withdrawRoute, /className="efhc-exchange-panel efhc-withdraw-create-card_body"/);
  assert.match(withdrawRoute, /data-withdraw-action="create"/);
  assert.match(exchangeRoute, /exchangeMutation\.mutateAsync/);
});
