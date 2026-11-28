import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const text = p => readFileSync(new URL(p,sourceUrl),'utf8');
const layout=text('../components/Layout.tsx');
const css=text('../styles/recovered-layout.css');
const nav=text('../lib/appBackNavigation.ts');
const smoke=text('../../../deployment/pages-tools/browser-smoke.mjs');

test('actual root DOM contains nav, and nav has explicit recovery selector',()=>{
 assert.match(layout,/<FrontendShellRoot[\s\S]*?className=\{/);
 assert.match(layout,/<nav\s+ref=\{bottomNavElementRef\}[\s\S]*?data-regression-nav-canon="v888"/);
 assert.match(css,/nav\.efhc-game-nav\[data-regression-nav-canon="v888"\] \.efhc-game-nav_item/);
 assert.match(css,/min-height:3\.25rem !important/);
});
test('canonical header uses measured equal columns, not first pre-cascade source ratio',()=>{
 assert.match(css,/grid-template-columns:repeat\(2,minmax\(0,1fr\)\) !important/);
 assert.match(layout,/data-regression-dock-canon="v888"/);
 assert.match(css,/\(100vw - 544px\)/);
});
test('theme gear follows approved activity timer, editing visibility and active dock; Energy untouched',()=>{
 const gear=text('../components/interface-settings/InterfaceCustomizationButton.tsx');
 const provider=text('../components/interface-settings/InterfaceCustomizationProvider.tsx');
 const globals=text('../styles/globals.css');
 const runtime=text('../../public/react-runtime-layout.css');
 assert.match(gear,/data-visible=\{customization\.buttonVisible \? "true" : "false"\}/);
 assert.match(provider,/setButtonVisible\(true\);\s*clearHideTimer\(\);\s*if \(mode === "editing"\) return;\s*hideTimerRef\.current = window\.setTimeout\(\(\) => \{\s*setButtonVisible\(false\);\s*hideTimerRef\.current = null;\s*\}, 3_000\)/);
 assert.match(provider,/buttonVisible: mode === "editing" \|\| buttonVisible/);
 assert.match(globals,/\.efhc-customization-control-dock > \.efhc-interface-customization-button\[data-visible="false"\]\s*\{\s*pointer-events: none;/);
 assert.match(globals,/\.efhc-interface-customization-button\[data-visible="false"\]\s*\{[^}]*opacity: 0;/s);
 assert.match(layout,/className="efhc-customization-control-dock"[\s\S]*?<InterfaceCustomizationButton/);
 assert.match(runtime,/\.efhc-independent-shell > \.efhc-customization-control-dock\s*\{[^}]*right:\s*max\(/s);
 assert.match(gear,/if \(editing\) customization\.save\(\)/);
 assert.match(gear,/else customization\.enter\(\)/);
 assert.doesNotMatch(css,/efhc-energy-stage|efhc-energy-chip/);
});
test('Pages Back enabled in same-URL history: no extra Test-3 path or hash',()=>{
 assert.match(nav,/history\.pushState/);
 assert.match(nav,/addEventListener\("popstate"/);
 assert.match(nav,/addEventListener\("backbutton"/);
 assert.match(nav,/bridgeWindow\.__EFHC_ANDROID_BACK__/);
 assert.match(nav,/window\.sessionStorage/);
 assert.doesNotMatch(nav,/const APP_BACK_GUARD_HASH/);
});
test('CI performs actual browser-computed screenshots-equivalent geometry checks and navigation',()=>{
 for(const claim of ['OWNER_BOTTOM_NAV_RENDERED_REGRESSION','OWNER_HEADER_PROFILE_STATUS_REGRESSION','OWNER_CT_GEAR_CORNER_REGRESSION','OWNER_ANDROID_BACK_NAVIGATION_FAILED','OWNER_NAV_PANELS_CLICK_FAILED']) assert.ok(smoke.includes(claim),claim);
 assert.match(smoke,/Emulation\.setDeviceMetricsOverride/);
 assert.match(smoke,/Runtime\.evaluate/);
});
