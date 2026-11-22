import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const dialog = read("../../src/components/profile/ProfileSettingsDialog.tsx");

test("settings keeps the two maintenance buttons visible without technical paragraphs", () => {
  assert.match(dialog, /<section[^>]*data-profile-settings-maintenance/);
  assert.doesNotMatch(dialog, /<details\b|<summary\b|pwa\.clear_public_scope|pwa\.native_cache_managed/);
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
