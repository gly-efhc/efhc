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
