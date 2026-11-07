import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const read=p=>readFileSync(resolve(root,p),'utf8');
const header=read('src/components/GlobalHeader.tsx');
const profileModal=read('src/components/ProfileModal.tsx');
const profilePage=read('src/features/profile/WebProfilePage.tsx');
const home=read('src/pages/index.tsx');
const css=read('src/styles/energy-header-layout.css');
const app=read('src/pages/_app.tsx');
const owner=read('../docs/SSOT/ADMIN_ENTRY_GLOBAL_ID_CANON_v885.md');
test('OWNER: exactly four Header actions and NO admin mode switch in any role',()=>{
 assert.deepEqual([...header.matchAll(/data-action="(FAQ|Wallet|Deposit|HUB)"/g)].map(v=>v[1]),['FAQ','Wallet','Deposit','HUB']);
 assert.match(header,/data-action-count="4"/);
 assert.match(header,/data-admin-entry-owner="profile-only"/);
 assert.doesNotMatch(header,/onModeSwitch|showAdminEntry|showAdminDemoEntry|kind="admin"|kind="user"|\/admin/);
});
test('OWNER: Profile Admin remains available in both modal and public DEMO',()=>{
 assert.match(profileModal,/props\.isAdmin\s*\?/);
 assert.match(profileModal,/props\.onOpenAdmin/);
 assert.match(profileModal,/data-admin-entry-owner="profile-only"/);
 assert.match(profilePage,/data-admin-demo-entry="true"/);
 assert.match(app,/NEXT_PUBLIC_EFHC_PAGES_PREVIEW === "1"/);
});
test('OWNER: production role-gate documented as future backend confirmed Global ID',()=>{
 assert.match(owner,/Global ID/);
 assert.match(owner,/Admin.*SuperAdmin/);
 assert.match(owner,/server-side RBAC/);
 assert.match(owner,/DEMO/);
});
test('Header fix targets approved 53px high profile/balance and four controls',()=>{
 assert.match(css,/3\.315rem!important/);
 assert.match(css,/repeat\(4,minmax\(0,1fr\)\)!important/);
 assert.match(css,/data-canon-header="true"/);
 assert.doesNotMatch(css,/data-interface-app-mode="admin"/);
});
test('Energy value uses canonical responsive CSS instead of render-calculated font px',()=>{
 assert.match(home,/data-canon-energy="true"/);
 assert.match(home,/data-canon-energy-type="css-source-v866"/);
 assert.doesNotMatch(home,/heroFontPx|fontSize: `\$\{heroFontPx\}px`/);
 assert.match(css,/clamp\(1\.55rem,7\.4vw,2\.18rem\)/);
 assert.match(css,/@media\(max-width:350px\)/);
});
test('Energy generation and progress preserve exact atomic arithmetic and +50 boost',()=>{
 assert.match(home,/BigInt\(Math\.floor\(dtMs\)\)/);
 assert.match(home,/const progressPct = useMemo/);
 assert.match(home,/Math\.min\(100, basePct \+ 50\)/);
 assert.match(home,/formatFixedDown\(props\.gen_per_sec_effective, 8\)/);
 assert.match(home,/formatFixedDown\(props\.available_kwh, 8\)/);
});
test('EG EI PB variants and theme material untouched by cycle CSS',()=>{
 assert.match(home,/data-eg=\{energyFrameSurface\.variant\}/);
 assert.match(home,/data-pb=\{progressSurface\.variant\}/);
 assert.match(home,/data-ei=\{iconSurface\.variant\}/);
 assert.doesNotMatch(css,/data-color-theme-id=|data-global-theme-id=|background:linear-gradient|background-color:/);
});
test('new stylesheet follows earlier source corrections',()=>{
 assert.ok(app.indexOf('energy-header-layout.css')>app.indexOf('header-layout.css'));
});
