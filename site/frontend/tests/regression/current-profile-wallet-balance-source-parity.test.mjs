import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const file = (name) => readFileSync(new URL(name, import.meta.url), "utf8");

test("profile navigation retains reference account surfaces without duplicate FAQ action", () => {
  const profile = file("../../src/features/profile/WebProfilePage.tsx");
  assert.match(profile, /data-profile-content="profile"/);
  assert.match(profile, /data-profile-content="wallet"/);
  assert.match(profile, /data-profile-content="history"/);
  assert.match(profile, /label=\{t\("profile\.total_generated"\)\}/);
  assert.match(profile, /t\("profile\.interface_account_note"\)/);
  assert.doesNotMatch(profile, /data-profile-faq-entry="button-1304"/);
  assert.doesNotMatch(profile, /efhc-profile-action-card--wallet-layout/);
  assert.doesNotMatch(profile, /efhc-history-card p-3/);
});

test("wallet surface exposes one official connect action with verified bound addresses", () => {
  const wallet = file("../../src/components/profile/ProfileWalletSection.tsx");
  const walletItem = file("../../src/components/profile/wallet/WalletListItem.tsx");
  const address = file("../../src/components/profile/wallet/WalletAddressVerification.tsx");
  assert.match(wallet, /standalone-wallet-layout/);
  assert.match(wallet, /standalone-wallet-list/);
  assert.match(wallet, /source-card-title efhc-wallet-section-heading/);
  assert.equal((wallet.match(/<Button/g) || []).length, 1);
  assert.match(wallet, /wallet\.is_active && wallet\.proof_verified === true/);
  assert.doesNotMatch(wallet, /WalletConnectBanner/);
  assert.match(walletItem, /standalone-wallet-actions/);
  assert.match(address, /standalone-wallet-address/);
  assert.match(address, /standalone-wallet-copy-feedback/);
});

test("balance sheet preserves three separate amounts and real unified history", () => {
  const history = file("../../src/components/profile/ProfileHistorySection.tsx");
  for (const asset of ["EFHC", "EFHCm", "EFHCb"]) {
    assert.ok(history.includes('asset="' + asset + '"'));
  }
  for (const filter of ["all", "purchases", "exchange", "withdraw", "bonuses", "panels"]) {
    assert.ok(history.includes('"' + filter + '"'));
  }
  assert.match(history, /ProfileHistoryItem/);
  assert.match(history, /onExportCsv/);
  assert.match(history, /onExportXlsx/);
  assert.match(history, /data-history-online-page-size=\{50\}/);
});

test("deposit stays compact and external wallet owns transaction approval", () => {
  const deposit = file("../../src/components/DepositModal.tsx");
  assert.match(deposit, /data-direct-deposit-summary="exchange-like"/);
  assert.match(deposit, /t\("deposit\.amount_label"\)/);
  assert.match(deposit, /t\("deposit\.direct_send_efhc"\)/);
  assert.doesNotMatch(deposit, /data-direct-deposit-review="ready"/);
  assert.match(deposit, /wallet\.proof_verified === true/);
  assert.match(deposit, /void sendTransaction\(ready\.tx\)\.then\(/);
  assert.doesNotMatch(deposit, /routePrimaryWalletExecution/);
});
