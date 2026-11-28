import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
const root=resolve(sourceDir, '..', '..');
const read=(rel)=>readFileSync(resolve(root,rel),'utf8');
import test from 'node:test';
test('historical frozen home evidence (Q1062: deferred if reference unavailable)',()=>{
 const fixture=JSON.parse(read('src/reconstruction/frozen-v866-home-fixture.json'));
 assert.equal(fixture.source_sha256,'9b6371f5fb62939596b78206f95031c447e9f2b375e62b30704403bb25102aef');
 assert.equal(fixture.pages_preview.main_balance,fixture.source_dom_ids.balanceValue);
 assert.equal(fixture.pages_preview.total_generated_kwh,fixture.source_dom_ids.energyValue);
 assert.equal(fixture.pages_preview.active_panels,60);
});
test('current USER shell retains source-style marker and real stylesheet without DEMO balance fallback',()=>{
 const app=read('src/pages/_app.tsx'),layout=read('src/components/Layout.tsx');
 assert.match(app,/NEXT_PUBLIC_EFHC_PAGES_PREVIEW !== "1" \? <OnboardingTour/);
 assert.match(app,/!isAdminRoute && !isBrowserShop \? \([\s\S]*?\/user-shell\.css/);
 assert.match(layout,/data-efhc-source-styles=\{appMode === "user" \? "true" : undefined\}/);
 assert.match(app,/import \{ emptyOwnerSnapshot \} from "\.\.\/lib\/browserFallback"/);
 assert.match(app,/snap \?\? emptyOwnerSnapshot\(\)/);
 assert.doesNotMatch(app,/getBrowserFallbackSnapshot|frozen-v866-home-fixture/);
 const fallback=read('src/lib/browserFallback.ts');
 const empty=fallback.slice(fallback.indexOf('export function emptyOwnerSnapshot'));
 assert.match(empty,/main_balance: "0\.00000000"/);
 assert.match(empty,/bonus_balance: "0\.00000000"/);
 assert.match(empty,/exchange_preview: \{ok: false/);
 // Check the surviving historical fragment separately; not an assertion of loaded CSS parity.
 const css=read('src/styles/user-shell-layout.css');
 assert.match(css,/efhc-energy-stage_image/);
 assert.match(css,/data:image\/webp;base64/);
 assert.match(css,/data-efhc-source-styles="true"/);
 assert.doesNotMatch(css,/#admin|\.efhc-admin-/);
});
