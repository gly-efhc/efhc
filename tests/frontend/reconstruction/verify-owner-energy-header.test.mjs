import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(sourceDir,'../..');
const read=p=>readFileSync(resolve(root,p),'utf8');
const header=read('src/components/GlobalHeader.tsx');
const profilePage=read('src/features/profile/WebProfilePage.tsx');
const home=read('src/pages/index.tsx');
const css=read('src/styles/energy-header-layout.css');
const app=read('src/pages/_app.tsx');
const layout=read('src/components/Layout.tsx');
test('OWNER: exactly four Header actions and NO admin mode switch in any role',()=>{
 assert.deepEqual([...header.matchAll(/data-action="(FAQ|Wallet|Deposit|HUB)"/g)].map(v=>v[1]),['FAQ','Wallet','Deposit','HUB']);
 assert.match(header,/data-action-count="4"/);
 assert.match(header,/data-admin-entry-owner="profile-only"/);
 assert.doesNotMatch(header,/onModeSwitch|showAdminEntry|showAdminDemoEntry|kind="admin"|kind="user"|\/admin/);
});
test('Profile Admin entry uses confirmed roles; TEST visual role is not production RBAC',()=>{
 assert.match(profilePage,/\{ctx\.canRenderAdminPage \|\| ctx\.isAdmin \? \([\s\S]*?router\.push\("\/admin"\)[\s\S]*?\) : null\}/);
 assert.match(layout,/const canRenderAdminPage = Boolean\(props\.isAdmin\) \|\| \(\s*isDemoBackendMode\(\) && authSession\.status === "authenticated" &&\s*authSession\.context\?\.roles\.includes\("test_visual"\) === true\s*\)/);
 assert.match(layout,/isAdminRoute && !canRenderAdminPage/);
 assert.match(app,/fetchAdminAccess\(\)/);
 assert.doesNotMatch(profilePage,/data-admin-demo-entry="true"/);
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
test('EG EI PB variants and theme material untouched by cycle CSS',()=>{
 assert.match(home,/data-eg=\{energyFrameSurface\.variant\}/);
 assert.match(home,/data-pb=\{progressSurface\.variant\}/);
 assert.match(home,/data-ei=\{iconSurface\.variant\}/);
 assert.doesNotMatch(css,/data-color-theme-id=|data-global-theme-id=|background:linear-gradient|background-color:/);
});
test('current USER cascade loads real header and energy adapters',()=>{
 assert.ok(app.indexOf('/user-shell.css')>app.indexOf('/FRONTEND_v866.css'));
 assert.ok(app.indexOf('/react-runtime-layout.css')>app.indexOf('/user-shell.css'));
 assert.match(read('public/FRONTEND_v866.css'),/\.efhc-energy-stage_value\{[^}]*font-size:clamp\(/);
});
