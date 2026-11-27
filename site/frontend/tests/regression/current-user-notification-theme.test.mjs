import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const contents = (path) => readFileSync(new URL(`../../src/${path}`, import.meta.url), "utf8");
const globals = contents("styles/globals.css");

test("shared USER toasts use the ten-theme accent even for errors and retain alert kind", () => {
  assert.match(globals, /--efhc-toast-color:\s*var\(--efhc-ct-accent, var\(--tg-button\)\)/);
  assert.doesNotMatch(globals, /efhc-user-toast\[data-toast-kind="error"\][^{]*\{[^}]*--efhc-toast-color:\s*#/);
  assert.match(globals, /\.efhc-user-toast-close:focus-visible\s*\{[^}]*var\(--efhc-ct-focus,/);
  const layout = contents("components/Layout.tsx");
  assert.match(layout, /role=\{item.kind === "error" \? "alert" : "status"\}/);
  assert.match(layout, /item.kind === "success" \? "✓" : item.kind === "error" \? "!" : "i"/);
});

test("visible inline notifications and empty placeholders share USER CT materials without styling arbitrary ARIA statuses", () => {
  assert.match(contents("components/ui/EmptyState.tsx"), /data-user-feedback-kind=\{props.intent \?\? "neutral"\}/);
  assert.match(contents("components/ui/telegram/TelegramInfoBlock.tsx"), /efhc-user-info-block /);
  assert.match(contents("components/ui/telegram/TelegramEmptyState.tsx"), /efhc-user-empty-block /);
  const blocks = globals.split("/* USER notification chroma:")[1].split("/* End USER notification chroma. */")[0];
  assert.match(blocks, /\[data-interface-app-mode="user"\]\[data-color-theme-id\]/);
  assert.doesNotMatch(blocks, /\[role="(?:alert|status)"\]\s*[{,]/);
  for (const marker of [
    "data-user-feedback-kind", 'data-history-state="read-error"', "efhc-history-bank-source-warning",
    "efhc-user-info-block", "efhc-user-empty-block", "efhc-network-status",
    "efhc-tonconnect-phase", "efhc-tonconnect-transaction", "efhc-direct-deposit_status",
    "efhc-withdraw-ad-status-icon", "efhc-withdraw-inline-alert",
  ]) assert.ok(blocks.includes(marker), `Missing USER notice ${marker}`);
});

test("portal-owned deposit and withdraw notices receive each of the ten USER palettes", () => {
  const palette = contents("styles/referrals-social-brand-contract.css");
  for (let n = 1; n <= 10; n++) {
    const id = `CT-${String(n).padStart(2, "0")}`;
    const selector = `:is(.efhc-independent-shell,.efhc-user-direct-deposit-portal,.efhc-withdraw-ad-overlay)[data-interface-app-mode="user"][data-color-theme-id="${id}"]`;
    assert.match(palette.split(selector)[1]?.split("}")[0] ?? "", /--efhc-ct-accent-rgb:\d+,\d+,\d+;/, id);
  }
  assert.match(contents("pages/withdraw.tsx"), /surface="withdraw-ad"\s+portalColorThemeId=\{settings.color_theme_id\}/);
  assert.match(contents("components/DepositModal.tsx"), /portalColorThemeId=\{colorThemeId\}/);
  assert.match(contents("components/ui/Modal.tsx"), /data-color-theme-id=\{props.portalColorThemeId\}/);
});

test("all USER toasts retain bottom placement and a uniform theme border", () => {
  const rule = globals.split(".efhc-user-toast {")[1].split("}")[0];
  assert.ok(rule.includes("border: 1px solid color-mix(in srgb, var(--efhc-toast-color) 42%, var(--tg-hint))"));
  assert.doesNotMatch(rule, /border-left/);
  assert.ok(globals.includes("bottom: calc(var(--efhc-safe-bottom) + 5.9rem)"));
  assert.ok(contents("pages/panels.tsx").includes('toast(t("panels.activate_ok"), "success")'));
});
