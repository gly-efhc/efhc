import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const readSource = (name) => readFileSync(new URL(
  "../../src/features/profile/" + name, import.meta.url,
), "utf8");
const page = readSource("WebProfilePage.tsx");
const providers = readSource("AccountProviders.tsx");

test("the existing Account footer opens a section within the persistent profile shell", () => {
  assert.match(page, /data-provider-entry="profile-footer"[\s\S]*?onClick=\{\(\) => setTab\("providers"\)\}/);
  assert.doesNotMatch(page, /if\s*\(activeTab === "providers"\)\s*\{\s*return/);
  assert.match(page, /id="profilePage"[\s\S]*?data-profile-primary-navigation="profile-wallet-history-faq"[\s\S]*?activeTab === "providers"[\s\S]*?data-profile-content="providers"/);
  assert.match(page, /active=\{activeTab === "profile" \|\| activeTab === "providers"\}/);
  assert.match(page, /navigateBackWithinApp/);
  assert.match(page, /router.push\("\/faq"\)/);
});

test("Account exposes Telegram and official TON proof without adding auth paths", () => {
  assert.match(providers, /data-provider="telegram"/);
  assert.match(providers, /data-provider="ton-connect"/);
  assert.match(providers, /auth.loginTelegram\(\)/);
  assert.match(providers, /getTelegramInitData\(\)/);
  assert.match(providers, /hasVerifiedWallet/);
  assert.doesNotMatch(providers, /wallet\.connect_button|browser_login\.telegram_cta/);
  assert.match(providers, /\{connectLabel\}/);
  assert.match(providers, /props.hasVerifiedWallet \? t\("wallet.title"\) : connectLabel/);
  assert.match(providers, /openTelegramApp\(\)/);
  assert.doesNotMatch(providers, /window\.open|NEXT_PUBLIC_TWA_RETURN_URL/);
  assert.doesNotMatch(providers, /loginDemo|error\.message|localStorage|\bfetch\(/);
  assert.match(page, /wallet.is_active && wallet.proof_verified === true/);
  assert.match(page, /ctx.openWalletConnect\("binding"\)/);
});

test("only the four primary Profile navigation buttons receive compact reference geometry", () => {
  const css = readSource("profile-navigation.module.css");
  assert.match(page, /styles\.primaryTabs/);
  assert.match(page, /styles\.primaryTab/);
  assert.match(css, /grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/);
  assert.match(css, /gap: 0?\.28rem/);
  assert.match(css, /min-height: 2\.15rem/);
  assert.doesNotMatch(css, /footer|settings|header/i);
});

test("Profile tabs have separate identical one-pixel frames and a border-only selected state", () => {
  const css = readSource("profile-navigation.module.css");
  const strip = css.match(/\.primaryTabs\[data-profile-primary-navigation\] \{([^}]+)\}/)?.[1] ?? "";
  const frame = css.match(/\.primaryTab\[data-profile-tab\] \{([^}]+)\}/)?.[1] ?? "";
  const selected = css.match(/\.primaryTab\[data-profile-tab\]\[data-active="true"\] \{([^}]+)\}/)?.[1] ?? "";
  assert.match(strip, /border: 0 !important/);
  assert.match(strip, /background: none !important/);
  assert.match(strip, /box-shadow: none !important/);
  assert.match(frame, /border: 1px solid[^;]+!important/);
  assert.match(frame, /box-shadow: none !important/);
  assert.match(frame, /background: transparent !important/);
  assert.match(frame, /color: var\(--tg-text,/);
  assert.match(selected, /^\s*border-color: [^;]+!important;\s*$/);
  assert.doesNotMatch(css, /outline\s*:\s*(none|0)/);
  assert.match(css, /:global\(#profilePage\)/);
});

test("React Profile tabs are independent of the old reference strip paint", () => {
  assert.doesNotMatch(page, /efhc-profile-tabs source-profile-tabs/);
});

test("provider connection copy uses one localized word in every supported language", () => {
  const labels = readSource("account-provider-labels.ts");
  const expected = ["ru", "en", "uk", "de", "fr", "es", "it", "tr", "pl", "da", "hi", "id", "sw", "pt", "ko", "ja"];
  const pairs = [...labels.matchAll(/^\s*(\w+): "([^"]+)",$/gm)].map(match => [match[1], match[2]]);
  assert.deepEqual(pairs.map(([lang]) => lang).sort(), expected.sort());
  assert.equal(Object.fromEntries(pairs).ru, "Подключить");
  for (const [, label] of pairs) assert.doesNotMatch(label.trim(), /\s/);
  assert.match(providers, /"profile\.provider_connect_action"/);
  assert.match(providers, /useContext\(LayoutContext\)/);
});

test("provider rows and text are flat without changing the provider card frames", () => {
  const css = readSource("account-providers.module.css");
  assert.match(providers, /styles\.panelTitle/);
  assert.equal((providers.match(/className=\{styles\.providerRow\}/g) || []).length, 2);
  assert.match(providers, /data-provider-row="telegram"/);
  assert.match(providers, /data-provider-row="ton-connect"/);
  assert.equal((providers.match(/className="efhc-profile-action-card efhc-account-provider-card p-3"/g) || []).length, 2);
  assert.doesNotMatch(providers, /className="source-row"/, "Provider rows must not inherit the broad inset material");
  assert.match(css, /\.providerRow\s*\{[^}]*display:\s*flex;[^}]*justify-content:\s*space-between/);
  assert.equal((providers.match(/styles\.providerCopy/g) || []).length, 2);
  assert.match(css, /background: none !important/);
  assert.match(css, /box-shadow: none !important/);
  assert.doesNotMatch(css, /border:|efhc-account-provider-card/);
});
