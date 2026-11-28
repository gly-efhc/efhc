import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(sourceDir,'../../..');
const layout=fs.readFileSync(path.join(root,'frontend/src/components/Layout.tsx'),'utf8');
const yaml=fs.readFileSync(path.join(root,'deployment/pages-tools/browser-smoke.mjs'),'utf8');
test('v901: Pages Panels smoke selector uses the same canonical key as Layout.NavItem',()=>{
 const match=layout.match(/href:\s*"\/panels",\s*key:\s*"([^"]+)"/);
 assert.ok(match,'Layout must declare the Panels route and key together');
 assert.equal(match[1],'nav.panels');
 assert.match(layout,/data-nav-key=\{props\.navKey\}/);
 assert.ok(yaml.includes(`a[data-nav-key="${match[1]}"]`));
 assert.ok(!yaml.includes('a[data-nav-key="panels"]'));
});
test('v901: Pages browser smoke fails closed with precise missing button and href diagnostics',()=>{
 assert.match(yaml,/OWNER_NAV_PANELS_BUTTON_MISSING/);
 assert.match(yaml,/OWNER_NAV_PANELS_HREF_MISMATCH/);
 assert.match(yaml,/OWNER_NAV_PANELS_CLICK_DISPATCH_FAILED/);
 assert.match(yaml,/lastNavProbe, routeChecks/);
 assert.match(yaml,/clickPanels\.result\.result\.value!==true/);
 assert.match(yaml,/OWNER_NAV_PANELS_CLICK_FAILED/);
});
test('v901: Keep intact strict nav and balance checks plus isolated diagnostic collection',()=>{
 assert.match(yaml,/PAGES_BALANCE_D8_OR_DISPLAY_MISMATCH/);
 assert.match(yaml,/OWNER_BOTTOM_NAV_RENDERED_REGRESSION/);
 assert.match(yaml,/EFHC_CI_DIAGNOSTIC_JSON=/);
 assert.match(yaml,/EFHC_PAGES_CHROME_RUNTIME_SMOKE=FAIL/);
 assert.match(fs.readFileSync(path.join(root,'.github/workflows/efhc-pages.yml'),'utf8'),/\$RUNNER_TEMP\/efhc-pages-tools\/browser-smoke\.mjs/);
});
