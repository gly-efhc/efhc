import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = path.resolve(sourceDir, '../../..');
const text = (p) => readFileSync(path.join(root,p),'utf8');
const icon = text('frontend/src/components/interface-settings/InterfaceCustomizationButton.tsx');
const css = text('frontend/src/styles/globals.css');
const provider = text('frontend/src/components/interface-settings/InterfaceCustomizationProvider.tsx');
const selector = text('frontend/src/components/interface-settings/GlobalThemeControl.tsx');
const catalog = text('frontend/src/lib/colorThemeRegistry.ts');
function rule(selectorText){
 const i=css.indexOf(selectorText+' {');
 assert.ok(i>=0, 'missing selector '+selectorText);
 return css.slice(i, css.indexOf('}',i)+1);
}
test('historical gear/check contour proof (Q1062: deferred if reference unavailable)',()=>{
 const source = JSON.parse(text('docs/SSOT/CUSTOMIZATION_GEAR_CANON_v866.json'));
 assert.equal(source.source_sha256,'9b6371f5fb62939596b78206f95031c447e9f2b375e62b30704403bb25102aef');
 for(const contour of [...source.gear_paths,...source.check_paths])assert.ok(icon.includes(`d="${contour}"`),'canon contour missing');
 assert.doesNotMatch(icon, /M19\.2 13\.1v-2\.2/);
 assert.equal((icon.match(/strokeWidth="1\.85"/g)||[]).length,3);
 assert.equal((icon.match(/strokeLinecap="round"/g)||[]).length,3);
});
test('gear and selector restore original dimensions and svg rendering',()=>{
 const gear=rule('.efhc-interface-customization-button');
 const globe=rule('.efhc-global-theme-control');
 for(const x of [gear,globe]){
  assert.match(x,/width:\s*2\.22rem;/);assert.match(x,/height:\s*2\.22rem;/);
  assert.match(x,/min-width:\s*2\.22rem;/);assert.match(x,/min-height:\s*2\.22rem;/);
  assert.match(x,/border-radius:\s*999px;/);
 }
 const svg=rule('.efhc-interface-customization-button svg');
 assert.match(svg,/width:\s*1\.04rem/);assert.match(svg,/stroke-width:\s*1\.85/);
 assert.match(svg,/fill:\s*none/);
});
test('gear editing and save actions remain intact; idle gear does not switch theme',()=>{
 assert.match(icon,/if \(editing\) customization\.save\(\);/);
 assert.match(icon,/else customization\.enter\(\);/);
 assert.doesNotMatch(icon,/nextGlobalTheme/);
 assert.match(provider,/\}, 3_000\);/);
 assert.match(provider,/setButtonVisible\(false\);/);
 assert.match(provider,/setDraftColorThemeId\(nextTheme\.id\);/);
});
test('globe retains 10 CT choices, click and swipe, draft/save semantics',()=>{
 const ids=[...catalog.matchAll(/\{ id: "(CT-\d{2})", slot:/g)].map(x=>x[1]);
 assert.deepEqual(ids,Array.from({length:10},(_,i)=>`CT-${String(i+1).padStart(2,'0')}`));
 assert.match(selector,/customization\.nextGlobalTheme\(\)/);
 assert.match(selector,/customization\.previousGlobalTheme\(\)/);
 assert.match(provider,/color_theme_id: draftColorThemeId/);
 assert.match(selector,/if \(customization\.mode !== "editing"\) return null/);
});
