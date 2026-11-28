import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
const read = p => readFileSync(new URL('../../../frontend/' + p, import.meta.url), 'utf8');
const app = read('src/pages/_app.tsx');
const header = read('src/components/GlobalHeader.tsx');
const layout = read('src/components/Layout.tsx');
const profile = read('src/features/profile/WebProfilePage.tsx');
const providers = read('src/features/profile/AccountProviders.tsx');
const proof = read('src/proof/AdminVisualProofRouter.tsx');
const admin = read('src/pages/admin/index.tsx');
// Q0956–0959, TEST/RELEASE identity boundary; Q0927 removes visual code freeze,
// not role checks or the separately preserved original visual reference.
test('four Header actions and the actual authorized Profile Admin entry', () => {
  assert.deepEqual([...header.matchAll(/data-action="(FAQ|Wallet|Deposit|HUB)"/g)].map(m=>m[1]), ['FAQ','Wallet','Deposit','HUB']);
  assert.match(header, /data-action-count="4"/);
  assert.doesNotMatch(header, /showAdminDemoEntry|ADMIN DEMO|onModeSwitch/);
  assert.match(profile, /\{ctx\.canRenderAdminPage \|\| ctx\.isAdmin \? \([\s\S]*?router\.push\("\/admin"\)[\s\S]*?\) : null\}/);
  assert.match(layout, /isDemoBackendMode\(\) && authSession\.status === "authenticated" &&\s*authSession\.context\?\.roles\.includes\("test_visual"\) === true/);
  assert.match(app, /fetchAdminAccess\(\)/);
  assert.match(app, /access\?\.global_id === globalId/);
  assert.match(app, /adminRouteBlocked \|\| adminRouteChecking/);
  assert.match(layout, /isAdminRoute && !canRenderAdminPage/);
});
test('Account navigation and real authorization callbacks are preserved', () => {
  assert.match(profile, /data-provider-entry="profile-footer"/);
  assert.match(profile, /setTab\("providers"\)/);
  assert.match(profile, /ctx\.openWalletConnect\("binding"\)/);
  assert.match(providers, /data-provider-row="telegram"/);
  assert.match(providers, /data-provider-row="ton-connect"/);
  assert.match(providers, /if \(providersPending \|\| isLinked\) return/);
  assert.match(providers, /getTelegramInitData\(\)/);
  assert.match(providers, /openTelegramApp\(\)/);
  assert.match(providers, /\{connectLabel\}/);
  assert.match(providers, /disabled=\{providersPending \|\| props\.walletActionPending\}/);
  assert.doesNotMatch(providers, /setConnected\(|localStorage|sessionStorage|\bfetch\(/);
});
test('Admin proof keeps its routes, while real Admin uses linked transport', () => {
  assert.match(proof, /"\/admin\/api-workbench"/);
  assert.match(proof, /"\/admin\/emergency"/);
  assert.match(app, /effectiveAdminVisualProofPath/);
  assert.match(admin, /const adminApiRequest = useAdminLinkedTransport\(\)/);
  assert.match(admin, /adminApiRequest<Overview>\(ADMIN_REPORTS_OVERVIEW_PATH, "GET"\)/);
  assert.doesNotMatch(admin, /DEMO_ADMIN_OVERVIEW|IS_PUBLIC_PAGES_DEMO/);
});
