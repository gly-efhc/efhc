import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read = (name) => readFileSync(new URL(name, sourceUrl), 'utf8');
const css = read('../styles/panels-layout.css');
const page = read('../pages/panels.tsx');
const ci = read('../../../deployment/pages-tools/browser-smoke.mjs');
const shell = read('../styles/recovered-layout.css');

test('PA-01 alone has two-column activation values and source-dense size', () => {
  assert.match(css, /efhc-panels-activation-card\[data-pa="PA-01"\] > \.grid > \.grid \{\s*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(css, /efhc-panels-activation-card\[data-pa="PA-01"\] \.efhc-panels-activate \{\s*min-height: 40px;\s*height: 40px;/);
  assert.doesNotMatch(css, /efhc-panels-activation-card\[data-pa="PA-(?:0[2-9]|1\d)"\] > \.grid > \.grid/);
});

test('panels financial D8 and protected portfolio CTA action remain intact', () => {
  assert.match(page, /format8\(totalActivationBalance\)/);
  assert.match(page, /data-panels-portfolio-entrypoint="canonical"/);
  assert.match(page, /router\.push\(PANELS_ROUTE_STATIC_GUARD\.portfolio\)/);
  assert.match(page, /await activationMutation\.mutateAsync\(idk\)/);
});

test('release browser smoke verifies actual computed PA-01 and Header status containment', () => {
  assert.match(ci, /OWNER_PANELS_PA01_RENDERED_GEOMETRY_REGRESSION/);
  assert.match(ci, /statusWithinProfile/);
  assert.match(ci, /OWNER_HEADER_PROFILE_STATUS_REGRESSION/);
  assert.match(ci, /OWNER_ANDROID_BACK_NAVIGATION_FAILED/);
  assert.match(shell, /data-regression-nav-canon="v888"/);
});
