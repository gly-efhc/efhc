import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import test from 'node:test';
const root = new URL('../../../frontend/', import.meta.url);
const read = p => readFileSync(new URL(p, root), 'utf8');
const app = read('src/pages/_app.tsx');
const proof = read('src/proof/AdminVisualProofRouter.tsx');
const profile = read('src/features/profile/WebProfilePage.tsx');
const providers = read('src/features/profile/AccountProviders.tsx');
// OWNER Q0956–0959: actual Telegram/TON account surface, not synthetic six-provider DEMO.
// The identity mapping contract may support additional provider subjects; this test
// does not prohibit later OWNER-approved integrations.
test('visual Admin proof is separately gated and not the real TEST session', () => {
  assert.match(app, /const pagesAdminPreview =\s*process\.env\.NEXT_PUBLIC_EFHC_PAGES_PREVIEW === "1" &&\s*process\.env\.NEXT_PUBLIC_EFHC_ADMIN_VISUAL_PROOF === "1" &&\s*process\.env\.NEXT_PUBLIC_EFHC_DATA_SOURCE !== "demo_backend"/);
  assert.match(app, /pagesAdminPreview && visualRoutes\.has\(router\.pathname\)/);
  assert.match(app, /adminRouteBlocked/);
  assert.match(proof, /data-efhc-admin-readonly-demo/);
  assert.match(app, /if \(!active\) return;\s*const confirmed = access\?\.global_id === globalId/);
});
test('Profile Account reads verified session and wallet proof without fake connections', () => {
  assert.match(profile, /data-provider-entry="profile-footer"[\s\S]*?setTab\("providers"\)/);
  assert.match(profile, /activeTab === "providers"[\s\S]*?<AccountProviders/);
  assert.match(profile, /hasVerifiedWallet=\{wallets\.some\(\(wallet\) => wallet\.is_active && wallet\.proof_verified === true\)\}/);
  assert.match(providers, /data-provider-state-source="server-session"/);
  assert.match(providers, /auth\.status === "authenticated" \? auth\.context : null/);
  assert.match(providers, /telegramVerified = isLinked && context\?\.provider === "telegram"/);
  assert.match(providers, /auth\.loginTelegram\(\)/);
  assert.match(providers, /data-provider-open-wallet="official-ton-connect"/);
  assert.match(providers, /props\.hasVerifiedWallet \? props\.onOpenWallet : props\.onConnectWallet/);
  assert.doesNotMatch(providers, /setConnected\(|localStorage|sessionStorage|\bfetch\(|loginDemo/);
  assert.equal(existsSync(new URL('src/features/profile/AccountProvidersDemo.tsx', root)), false);
});
