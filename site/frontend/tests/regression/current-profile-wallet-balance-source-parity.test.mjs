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

test("profile and withdraw CSV/XLSX exports use the same server stream with distinct category scope", () => {
  const service = file("../../src/services/profile.service.ts");
  const query = file("../../src/queries/useProfile.ts");
  const profile = file("../../src/features/profile/WebProfilePage.tsx");
  const withdraw = file("../../src/pages/withdraw.tsx");
  const history = file("../../src/components/profile/ProfileHistorySection.tsx");

  assert.match(service, /new URLSearchParams\(\{ category \}\)/);
  assert.match(service, /transportRawRequest\(`\/profile\/history\/export\.\$\{format\}\?\$\{query\.toString\(\)\}`/);
  assert.match(query, /downloadProfileHistoryExport\(format, category\)/);
  assert.match(profile, /mutateAsync\(\{ format, category: historyFilter \}\)/);
  assert.match(profile, /useState<HistoryFilter>\("all"\)/);
  assert.match(withdraw, /mutateAsync\(\{ format, category: "withdraw" \}\)/);
  assert.equal((withdraw.match(/data-history-export="(?:csv|xlsx)-server-side"/g) || []).length, 2);
  assert.doesNotMatch(withdraw, /withdraw\.latest_operations/);
  assert.doesNotMatch(withdraw, /useWalletBalanceHistory/);
  for (const category of ["all", "purchases", "exchange", "withdraw", "bonuses", "panels"]) {
    assert.ok(history.includes('"' + category + '"'), category);
    assert.ok(service.includes('"' + category + '"'), category);
  }
});

test("withdraw owner-approved form and user activity contracts remain independent of export", () => {
  const withdraw = file("../../src/pages/withdraw.tsx");
  const queries = file("../../src/queries/useWithdrawals.ts");
  const modal = file("../../src/components/ui/Modal.tsx");
  const layout = file("../../src/components/Layout.tsx");
  const css = file("../../src/styles/globals.css");
  assert.match(withdraw, /useWithdrawalsPage\(\{ statusFilter: "all" \}\)/);
  assert.match(withdraw, /\.filter\(\(item\) => statusFilter === "all" \|\| item\.status === statusFilter\)/);
  assert.match(withdraw, /document\.addEventListener\("pointerdown", refreshOnActivity/);
  assert.match(withdraw, /document\.addEventListener\("visibilitychange", refreshOnActivity/);
  assert.match(withdraw, /data-withdraw-action="load-more"/);
  assert.match(withdraw, /\[data-withdraw-action="load-more"\]/);
  assert.match(withdraw, /lastRefreshAtRef\.current, request\.dataUpdatedAt\) < 10_000/);
  assert.doesNotMatch(withdraw, /refreshWithdrawSurface|withdraw\.refresh_history/);
  assert.doesNotMatch(withdraw, /efhc-withdraw-primary-summary/);
  assert.match(withdraw, /!primaryWallet \? \(/);
  assert.match(withdraw, /t\("withdraw\.create_request"\)/);
  assert.match(withdraw, /t\("withdraw\.amount_exceeds_balance"\)/);
  assert.match(withdraw, /data-amount-state=\{amountTouched && amountIssue/);
  assert.match(withdraw, /surface="withdraw-ad"/);
  assert.match(withdraw, /setWithdrawAdOpen\(phase !== "viewing" && phase !== "verifying"\)/);
  assert.match(queries, /refetchType: "none"/);
  assert.match(queries, /reflectConfirmedRequest/);
  assert.match(queries, /staleTime: 10_000/);
  assert.match(queries, /refetchOnWindowFocus: false/);
  assert.match(modal, /data-modal-surface=\{props\.surface\}/);
  assert.match(layout, /efhc-user-toast-stack/);
  assert.match(layout, /isAdminRoute/);
  assert.match(css, /efhc-withdraw-create-card \[data-withdraw-action="create"\]/);
  assert.match(css, /efhc-modal-overlay\[data-modal-surface="withdraw-ad"\]/);
  assert.match(css, /efhc-user-toast\[data-toast-kind="error"\]/);
});

test("all ten CTs and only accepted XH/WD design bindings stay available", () => {
  const registry = file("../../src/lib/interfaceVariantRegistry.ts");
  const css = file("../../src/styles/globals.css");
  const baseTheme = file("../../src/styles/user-interface-material.css");
  const wdThemes = file("../../src/styles/faq-withdraw-themes.css");
  assert.match(registry, /XH: numbered\("XH", 6\)/);
  assert.match(registry, /WD: numbered\("WD", 5\)/);
  assert.match(registry, /XS: numbered\("XS", 1\)/);
  assert.match(registry, /XC: numbered\("XC", 1\)/);
  assert.match(registry, /XA: numbered\("XA", 1\)/);
  for (const design of ["XH-01", "XH-02", "XH-04", "XH-07", "XH-10", "XH-12"]) {
    assert.ok(css.includes('data-xh="' + design + '"'), design);
  }
  for (const design of ["WD-01", "WD-02", "WD-06", "WD-10"]) {
    assert.ok(css.includes('data-wd="' + design + '"'), design);
  }
  assert.ok(wdThemes.includes('data-wd="WD-13"'));
  for (let n = 1; n <= 10; n++) {
    assert.ok(baseTheme.includes('data-color-theme-id="CT-' + String(n).padStart(2, "0") + '"'));
  }
});

test("all supported languages include distinct withdrawal over-balance feedback", () => {
  for (const lang of ["da","de","en","es","fr","hi","id","it","ja","ko","pl","pt","ru","sw","tr","uk"]) {
    const dict = JSON.parse(file("../../public/locale/" + lang + ".json"));
    assert.ok(dict["withdraw.amount_exceeds_balance"]?.trim(), lang);
    assert.ok(dict["withdraw.min_hint"]?.trim(), lang);
    assert.ok(dict["withdraw.export_success"]?.trim(), lang);
    assert.ok(dict["withdraw.export_error"]?.trim(), lang);
  }
});
