import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const readSource = (name) => readFileSync(new URL(`../../src/${name}`, import.meta.url), "utf8");

test("bound Wallet cards inherit the Wallet page surface without a hard-coded fill", () => {
  const section = readSource("components/profile/ProfileWalletSection.tsx");
  assert.match(section, /standalone-wallet-list \$\{styles\.boundCards\}/);
  const wallet = readSource("components/profile/wallet-cards.module.css");
  const card = wallet.split(".boundCards :global(.efhc-wallet-entry) {")[1].split("}")[0];
  assert.match(card, /background-color:\s*transparent\s*!important;/);
  assert.match(card, /background-image:\s*none\s*!important;/);
  assert.match(card, /padding:\s*\.74rem;/);
  assert.match(card, /border-radius:\s*\.86rem;/);
  assert.doesNotMatch(wallet, /@layer|#panelsPortfolioPage|\.efhc-panel-tile/);
});

test("remove and the noninteractive primary indicator share one compact row and sizing control", () => {
  const card = readSource("components/profile/wallet/WalletPrimaryCard.tsx");
  assert.match(card, /standalone-wallet-actions[\s\S]*?sizeLabel=\{t\("wallet.primary_badge"\)\}[\s\S]*?status="wallet-primary-badge"/);
  const action = readSource("components/profile/wallet/WalletCardAction.tsx");
  assert.match(action, /status[\s\S]*?<span data-status=\{status\} className=\{styles.actionButton\}>/);
  const css = readSource("components/profile/wallet-cards.module.css");
  const row = css.split(".boundCards :global(.standalone-wallet-actions) {")[1].split("}")[0];
  assert.match(row, /display:\s*flex;/);
  assert.match(row, /align-items:\s*center;/);
  assert.match(row, /justify-content:\s*flex-end;/);
});

test("linked wallet actions measure the existing badge but paint like the active Wallet tab", () => {
  const css = readSource("components/profile/wallet-cards.module.css");
  const button = readSource("components/profile/wallet/WalletCardAction.tsx");
  const tabs = readSource("features/profile/profile-navigation.module.css");
  assert.match(button, /aria-hidden="true"[\s\S]*?<TelegramStatusBadge label=\{sizeLabel\} tone="primary"/);
  for (const name of ["WalletPrimaryCard", "WalletListItem"]) {
    const card = readSource(`components/profile/wallet/${name}.tsx`);
    assert.match(card, /<WalletCardAction[\s\S]*?sizeLabel=\{t\("wallet.primary_badge"\)\}/);
  }
  const frame = css.split(".actionButton {")[1].split("}")[0];
  const tab = tabs.split(".primaryTab[data-profile-tab] {")[1].split("}")[0];
  const selected = tabs.split('.primaryTab[data-profile-tab][data-active="true"] {')[1].split("}")[0];
  for (const prop of ["border-radius", "background", "color", "box-shadow"]) {
    const value = new RegExp(`^\\s*${prop}:\\s*([^;]+);`, "mu");
    assert.ok(tab.match(value), prop);
    assert.equal(frame.match(value)?.[1], tab.match(value)?.[1], prop);
  }
  assert.match(frame, /border: 1px solid;/);
  assert.match(frame, /position: absolute;\s*inset: 0;/);
  assert.match(css, /\.actionMeasure \{\s*visibility: hidden;/);
  assert.ok(css.includes(selected.trim()));
  assert.doesNotMatch(css, /efhc-wallet-connect-cta|data-shop-theme/);
});
