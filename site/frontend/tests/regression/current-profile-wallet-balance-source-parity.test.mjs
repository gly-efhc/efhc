import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const file = (name) => readFileSync(new URL(name, import.meta.url), "utf8");

test("profile navigation retains reference account surfaces without duplicate FAQ action", () => {
  const profile = file("../../src/features/profile/WebProfilePage.tsx");
  assert.match(profile, /data-profile-content="profile"/);
  assert.match(profile, /data-profile-content="wallet"/);
  assert.match(profile, /data-profile-content="history"/);
  assert.match(profile, /className="source-stats two"/);
  assert.match(profile, /className="source-stat-label">\{t\("profile\.total_generated"\)\}/);
  assert.match(profile, /className="source-card source-profile-settings-card efhc-profile-action-card"/);
  assert.match(profile, /className="efhc-profile-topbar source-profile-topbar"/);
  assert.match(profile, /className="efhc-profile-hero source-profile-hero"/);
  assert.match(profile, /t\("profile\.interface_account_note"\)/);
  assert.doesNotMatch(profile, /data-profile-faq-entry="button-1304"/);
  assert.doesNotMatch(profile, /efhc-profile-action-card--wallet-layout/);
  assert.doesNotMatch(profile, /efhc-history-card p-3/);
});

test("profile topbar and hero follow the reference mobile geometry for every color theme", () => {
  const profile = file("../../src/features/profile/WebProfilePage.tsx");
  const css = file("../../src/styles/globals.css");
  assert.match(profile, /className="source-button secondary" data-app-navigation="back"/);
  assert.match(profile, /className="efhc-profile-topbar_actions source-row"/);
  assert.match(profile, /className="efhc-profile-identity source-profile-identity"/);
  assert.match(profile, /className="source-stats two"/);
  assert.match(profile, /source-profile-compact-controls/);
  assert.match(css, /grid-template-columns: max-content minmax\(0, 1fr\) max-content !important/);
  assert.match(css, /#profilePage \.efhc-profile-hero\.source-profile-hero/);
  assert.match(css, /#profilePage \.source-stats \.source-stat/);
  assert.match(css, /rgba\(var\(--efhc-ct-accent-rgb\), \.30\)/);
});

test("three reference header controls keep their explicit source order on mobile", () => {
  const profile = file("../../src/features/profile/WebProfilePage.tsx");
  const css = file("../../src/styles/globals.css");
  assert.match(profile, /data-app-navigation="back"/);
  assert.match(profile, /className="efhc-profile-topbar_actions source-row"/);
  assert.match(css, /#profilePage \.source-profile-topbar > button\[data-app-navigation="back"\] \{\s*grid-column: 1 !important;/);
  assert.match(css, /#profilePage \.source-profile-topbar > strong \{\s*grid-column: 2 !important;/);
  assert.match(css, /#profilePage \.source-profile-topbar > \.efhc-profile-topbar_actions \{\s*grid-column: 3 !important;/);
  assert.match(css, /#profilePage \.source-profile-hero \.source-profile-identity \{\s*justify-items: stretch !important;/);
  assert.match(css, /#profilePage \.source-profile-hero \.source-profile-name \{\s*justify-self: start !important;/);
});

test("account identity action is at the bottom, guests never look verified, and four tabs remain", () => {
  const page = file("../../src/features/profile/WebProfilePage.tsx");
  const providers = file("../../src/features/profile/AccountProviders.tsx");
  assert.match(page, /data-profile-primary-navigation="profile-wallet-history-faq"/);
  assert.doesNotMatch(page, /label="Аккаунты"/);
  assert.match(page, /data-provider-entry="profile-footer"/);
  assert.match(page, /isDemoGuestSession\(\)/);
  assert.match(page, /profile\.linked_accounts_action/);
  assert.match(page, /profile\.sign_in_action/);
  assert.match(page, /data-provider-route="account-providers"/);
  assert.match(providers, /data-provider-auth-state=/);
  assert.match(providers, /data-provider-open-wallet="official-ton-connect"/);
});

test("gear opens only source four toggles and avatar retains advanced services", () => {
  const page = file("../../src/features/profile/WebProfilePage.tsx");
  const dialog = file("../../src/components/profile/ProfileSettingsDialog.tsx");
  const shared = file("../../src/components/ui/Modal.tsx");
  assert.match(page, /<ProfileSettingsDialog/);
  assert.match(page, /open=\{extendedProfileOpen\}/);
  assert.match(page, /setExtendedProfileOpen\(true\)/);
  assert.match(dialog, /data-profile-settings-compact="four"/);
  assert.match(dialog, /referenceLayout="settings"/);
  const settings = file("../../src/lib/settings.ts");
  assert.match(settings, /music_enabled: false,/);
  assert.match(settings, /sfx_enabled: true,/);
  assert.match(settings, /haptics_enabled: true,/);
  assert.match(settings, /reduce_motion: false,/);
  for (const setting of ["reduce_motion", "sfx_enabled", "haptics_enabled", "music_enabled"]) {
    assert.ok(dialog.includes('key: "' + setting + '"'));
  }
  assert.match(shared, /data-modal-reference-layout=\{props\.referenceLayout\}/);
});

test("all locale dictionaries have guest and verified account action labels", () => {
  const langs = ["da", "de", "en", "es", "fr", "hi", "id", "it", "ja", "ko", "pl", "pt", "ru", "sw", "tr", "uk"];
  for (const lang of langs) {
    const dict = JSON.parse(file("../../public/locale/" + lang + ".json"));
    assert.ok(dict["profile.sign_in_action"] && dict["profile.linked_accounts_action"], lang);
  }
});

test("provider and both compact dialogs use the same ten CT tokens", () => {
  const css = file("../../src/styles/globals.css");
  const registry = file("../../src/lib/colorThemeRegistry.ts");
  for (let index = 1; index <= 10; index++) {
    const theme = "CT-" + String(index).padStart(2, "0");
    assert.ok(registry.includes('id: "' + theme + '"'), theme);
    assert.ok(css.includes('.efhc-user-direct-deposit-portal[data-color-theme-id="' + theme + '"]'), theme);
  }
  assert.match(css, /efhc-profile-provider-page/);
  assert.match(css, /efhc-profile-provider-entry/);
  assert.match(css, /data-modal-reference-layout="settings"/);
  assert.match(css, /data-modal-reference-layout="deposit"/);
  assert.match(css, /var\(--efhc-ct-accent-rgb\)/);
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
