import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const layout = readFileSync(
  fileURLToPath(new URL("../../src/components/Layout.tsx", import.meta.url)),
  "utf8",
);
const adminPage = readFileSync(
  fileURLToPath(new URL("../../src/components/admin/AdminPage.tsx", import.meta.url)),
  "utf8",
);

test("public Pages preview flag never unlocks administrative page", () => {
  assert.doesNotMatch(
    layout,
    /canRenderAdminPage\s*:\s*[^,]*NEXT_PUBLIC_EFHC_PAGES_PREVIEW/,
  );
  assert.match(layout, /authSession\.status\s*===\s*"authenticated"/);
  assert.match(layout, /authSession\.context\?\.roles\.includes\("test_visual"\)/);
});

test("deny any unauthorized Admin child even if its own page lacks a guard", () => {
  assert.match(layout, /isAdminRoute\s*&&\s*!canRenderAdminPage/);
  assert.match(layout, /data-admin-access="denied"/);
  assert.match(layout, /:\s*props\.children/);
  assert.match(adminPage, /!ctx\.canRenderAdminPage/);
});

test("temporary key remains server-side, never in public JS", () => {
  assert.doesNotMatch(layout, /EFHC_TEST_ADMIN_ACCESS_KEY/);
  assert.doesNotMatch(layout, /efhc-test-[a-zA-Z0-9_-]{20,}/);
});
