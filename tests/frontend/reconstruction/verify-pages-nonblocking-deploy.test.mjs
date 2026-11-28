import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import {resolve} from 'node:path';
const root = resolve(sourceDir, '../../..');
const registered = readFileSync(resolve(root, '.github/workflows/efhc-pages.yml'), 'utf8');
const browser = readFileSync(resolve(root, 'deployment/pages-tools/browser-smoke.mjs'), 'utf8');
const getStep = (yaml, name) => {
  const text = `      - name: ${name}\n`;
  assert.equal(yaml.split(text).length, 2, `exactly one ${name}`);
  return yaml.split(text)[1].split('\n      - name: ')[0];
};
for (const [label, yaml] of [['registered',registered]]){
  test(`${label}: checks and artifacts precede Pages deploy, frontend and Chrome are non-blocking`,()=>{
    const markers = [
      '      - name: Initialize Pages pre-deploy diagnostics',
      '      - name: Collect frontend regression test failures (non-blocking)',
      '      - name: Compile actual React/Next for Pages (no backend)',
      '      - name: Collect Chrome route and UI failures before Pages (non-blocking)',
      '      - name: Summarize pre-deploy diagnostics, including failures',
      '      - name: Upload pre-deploy diagnostic logs, even when tests fail',
      '      - name: Upload compiled React to Pages',
      '      - name: Deploy real React to GitHub Pages'
    ];
    const at = markers.map(marker=>yaml.indexOf(marker));
    assert.ok(at.every(i=>i>=0),String(at));
    assert.ok(at.every((n,i)=>i===0||n>at[i-1]),String(at));
    for (const name of ['Collect frontend regression test failures (non-blocking)','Collect Chrome route and UI failures before Pages (non-blocking)']){
      assert.match(getStep(yaml,name), /continue-on-error: true/);
      assert.match(getStep(yaml,name),/tee "(?:\$RUNNER_TEMP\/efhc-pages-diagnostics\/|\$LOG_DIR\/)/m);
    }
    for (const name of ['Compile actual React/Next for Pages (no backend)','Fail closed if real React static export is missing','Upload compiled React to Pages','Deploy real React to GitHub Pages']){
      assert.doesNotMatch(getStep(yaml,name),/continue-on-error: true/);
    }
  });
  test(`${label}: logging and summary do not conceal failing tests`,()=>{
    const report = getStep(yaml,'Summarize pre-deploy diagnostics, including failures');
    const upload = getStep(yaml,'Upload pre-deploy diagnostic logs, even when tests fail');
    assert.match(report,/steps\.regressions\.outcome/);
    assert.match(report,/steps\.browser_smoke\.outcome/);
    assert.match(report,/test_errors_do_not_block_deploy.*True/);
    assert.match(report,/build_errors_block_deploy.*True/);
    assert.match(upload,/if: always\(\)/);
    assert.match(upload,/continue-on-error: true/);
    assert.match(upload,/retention-days: 14/);
    const published = getStep(yaml,'Report publication status and outstanding diagnostics');
    assert.match(published,/deployed with test failures/);
    assert.match(published,/EFHC_PAGES_DEPLOYED_WITH_TESTS_PASS/);
  });
}
test('registered workflow uses four ZIP-imported tools, without modifying import workflow',()=>{
  for (const path of ['prepare_pages.py','fix_pages_assets.py','verify_export.py','browser-smoke.mjs']){
    assert.ok(registered.includes(`deployment/pages-tools`) && registered.includes(path),path);
  }
  assert.equal(existsSync(resolve(root, 'ci/efhc-pages.yml')), false);
  assert.equal(existsSync(resolve(root, 'site/ci/efhc-pages.yml')), false);
  assert.match(browser,/EFHC_BROWSER_REGRESSION_AGGREGATE/);
  assert.doesNotMatch(registered,/EFHC_BUNDLED_BROWSER_SMOKE_MJS/);
});
