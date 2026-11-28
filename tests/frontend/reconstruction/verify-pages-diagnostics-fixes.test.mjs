import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
const root = resolve(sourceDir, "../../..");
const read = (p) => readFileSync(resolve(root, p), "utf8");
const browser = read("deployment/pages-tools/browser-smoke.mjs");
const workflow = read(".github/workflows/efhc-pages.yml");
const scanner = read("frontend/src/reconstruction/ci_predeploy_diagnostics.py");
const tasks = read("frontend/src/pages/tasks.tsx");
const badge = read("frontend/src/components/ui/Badge.tsx");
const css = read("frontend/src/styles/tasks-layout.css");
const pkg = JSON.parse(read("frontend/package.json"));
const lock = JSON.parse(read("frontend/package-lock.json"));
const support = "frontend/src/reconstruction/pages_ci/";

test("Chrome Tasks reads current server cards without synthetic tasks or actions", () => {
  assert.match(tasks, /data-tasks-page-runtime="react-server-data"/);
  for(const hook of ['useTasksCatalog','useMyTasks','useTaskEarnings']) assert.ok(tasks.includes(hook+'()'));
  assert.doesNotMatch(tasks, /data-demo-task-mode|isolated-preview/);
  const block=browser.slice(browser.indexOf("const tasksProbe=async()=>"),browser.indexOf("await runIndependentCheck('route-faq'"));
  assert.doesNotMatch(block,/global-id-unified-preview|demo_join_telegram|\.click\(|count!==5|enabled!==5/);
  assert.match(block,/assertTasksReadOnlySnapshot\(result,true\)/);
  assert.match(block,/tasks-catalog-read-only/);
  assert.match(badge, /className=\{/);
  assert.match(browser, /efhc-task-card_reward > span:last-child/);
  assert.match(css, /efhc-task-card_reward > span:last-child/);
  assert.match(css, /color:var\(--tasks-cycle-accent\)!important/);
});

test("Tasks browser validator distinguishes catalog truth, unavailable states and incomplete evidence",()=>{
  const source=browser.slice(browser.indexOf('function assertTasksReadOnlySnapshot('),browser.indexOf('\nconst diagnosticDir'));
  const validate=new Function(source+'\nreturn assertTasksReadOnlySnapshot')();
  const base={runtime:'react-server-data',hero:true,grid:true,legacyDemo:false,overflow:false,
    cards:[{code:'test-unit',status:'unavailable',action:'claim-bonus',disabled:true,reward:'bonus-efhcb',asset:'EFHCb'}]};
  assert.doesNotThrow(()=>validate(base,true));
  assert.doesNotThrow(()=>validate({...base,cards:[{...base.cards[0],status:'available',disabled:false}]},true));
  assert.throws(()=>validate({...base,cards:[] ,feedback:'neutral'},true),/CATALOG_NOT_QUALIFIED/);
  assert.throws(()=>validate({...base,cards:[]},false),/EMPTY_STATE_MISSING/);
  assert.throws(()=>validate({...base,cards:[{...base.cards[0],disabled:false}]},true),/DISABLED_STATE_INVALID/);
  assert.throws(()=>validate({...base,cards:[base.cards[0],base.cards[0]]},true),/CARD_CONTRACT_INVALID/);
  assert.throws(()=>validate({...base,legacyDemo:true},true),/RUNTIME_OR_RESPONSIVE_FAIL/);
  assert.throws(()=>validate({...base,overflow:true},true),/RUNTIME_OR_RESPONSIVE_FAIL/);
});

test("v907: public Pages diagnostics run real runnable TONConnect and exact release/budget scripts", () => {
  assert.match(scanner, /node', '--test', str\(public_suite\)/);
  assert.match(scanner, /frontend-tonconnect-private-acceptance/);
  assert.match(scanner, /NOT_AVAILABLE/);
  assert.match(scanner, /'frontend-performance-budgets', 'budgets\.mjs'/);
  assert.match(scanner, /'frontend-release-assets', 'verify-production-assets\.mjs'/);
  const importedBudgets = read(support + 'budgets.mjs');
  for (const limit of ['300_000', '250_000', '420_000', '350_000', '370_000']) {
    assert.ok(importedBudgets.includes(limit), limit);
  }
  for (const behavior of ['gzipSync', 'brotliCompressSync', 'build-manifest.json']) {
    assert.ok(importedBudgets.includes(behavior));
  }
  assert.match(importedBudgets, /baseline_comparison: "NOT_AVAILABLE_IN_PUBLIC_PAGES_RUNNER"/);
  assert.ok(read(support + 'verify-production-assets.mjs').length > 0);
  assert.match(pkg.scripts['release-assets:verify'], /src\/reconstruction\/pages_ci\/verify-production-assets\.mjs/);
  assert.match(pkg.scripts['performance-budgets'], /src\/reconstruction\/pages_ci\/budgets\.mjs/);
  assert.doesNotMatch(workflow, /UPDATE_POLICY.json/);
});

test("v907: follow-redirects fixed at registry-verified integrity without dependency downgrades", () => {
  const rec = lock.packages['node_modules/follow-redirects'];
  assert.equal(pkg.overrides['follow-redirects'], '^1.16.2');
  assert.equal(rec.version, '1.16.2');
  assert.equal(rec.resolved, 'https://registry.npmjs.org/follow-redirects/-/follow-redirects-1.16.2.tgz');
  assert.equal(rec.integrity,
    'sha512-/kVP2U8z596Ia0gwFrwyIeo74ta5aVmSeU1FfAUMAmcEP5EP7zydmag3SLiN64NaRKef3lxsq7i/g7ltJQDGow==');
  assert.equal(pkg.dependencies['@tonconnect/sdk'], '5.0.0');
  assert.equal(pkg.dependencies.next, '16.4.3');
});

test("v907: diagnostics never treat missing private backend as successful testing", () => {
  assert.match(scanner, /backend_source_present/);
  for (const tool of ['bandit', 'flake8', 'ruff', 'mypy', 'pip-audit', 'pytest']) {
    assert.match(scanner, new RegExp('backend-' + tool));
  }
  assert.match(scanner, /TOOL_ERROR/);
  assert.match(scanner, /quality-\{args\.phase\}\.json/);
  assert.match(scanner, /asyncio\.create_subprocess_exec/);
  assert.doesNotMatch(scanner, /shell=True/);
});
