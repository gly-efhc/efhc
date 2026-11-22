import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const dialog = read("../../src/components/profile/ProfileSettingsDialog.tsx");
const modal = read("../../src/components/ui/Modal.tsx");

test("settings keeps the two maintenance buttons visible without a heading or technical paragraphs", () => {
  assert.match(dialog, /<div[^>]*data-profile-settings-maintenance/);
  assert.doesNotMatch(dialog, /<details\b|<summary\b|pwa\.clear_public_scope|pwa\.native_cache_managed|pwa\.maintenance_title/);
  assert.match(dialog, /onClick=\{\(\) => void checkApplication\(\)\}/);
  assert.match(dialog, /onClick=\{\(\) => void clearPublicCache\(\)\}/);
  assert.match(dialog, /await registration\.update\(\)/);
  assert.match(dialog, /EFHC_PWA_CLEAR_PUBLIC_CACHE/);
  assert.doesNotMatch(dialog, /localStorage|sessionStorage|caches\.delete/);
});

test("settings portal centers and uses the same CT accent token at every setting", () => {
  assert.match(dialog, /\[data-modal-reference-layout="settings"\]\s*\{[^}]*align-items:\s*center/);
  assert.match(dialog, /\.standalone-setting-toggle\[data-active="true"\][^}]*var\(--efhc-ct-accent-rgb\)/);
  assert.match(dialog, /portalColorThemeId=\{colorThemeId\}/);
  assert.match(dialog, /aria-pressed=\{active\}/);
});

test("Settings keeps an accessible close icon without the source-row title plate", () => {
  assert.match(modal, /props\.referenceLayout === "settings"\s*\? "efhc-settings-header"/);
  assert.match(dialog, /\.efhc-settings-header\s*\{[^}]*border:\s*0;[^}]*background:\s*transparent/);
  assert.match(modal, /props\.referenceLayout === "deposit" \? "efhc-modal-header source-row" : "efhc-modal-header"/);
  assert.match(modal, /aria-label=\{t\("common\.close"\)\}[\s\S]*?>\s*×\s*<\/button>/);
  assert.match(dialog, /\.efhc-reference-settings-dialog \.efhc-modal-close\s*\{[^}]*width:\s*2\.3rem/);
});

test("only the Settings close control has a circular 2.3 rem footprint", () => {
  assert.match(dialog, /\[data-modal-reference-layout="settings"\]\s*\.efhc-reference-settings-dialog \.efhc-modal-close\s*\{[^}]*width:\s*2\.3rem;[^}]*height:\s*2\.3rem;[^}]*border-radius:\s*50%/);
});
