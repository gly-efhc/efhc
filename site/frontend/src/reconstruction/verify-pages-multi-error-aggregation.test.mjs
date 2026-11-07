import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, mkdtempSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';

const yaml = readFileSync(new URL('../../../ci/efhc-pages.yml',import.meta.url),'utf8');
const css = readFileSync(new URL('../styles/ranks-hero.css',import.meta.url),'utf8');
const start = '          cat > "$RUNNER_TEMP/efhc-pages-tools/browser-smoke.mjs" <<\'EFHC_BUNDLED_BROWSER_SMOKE_MJS\'\n';
const end = '          EFHC_BUNDLED_BROWSER_SMOKE_MJS';
function extract() {
 assert.equal(yaml.split(start).length,2);
 const raw = yaml.split(start)[1].split(end)[0];
 return raw.split('\n').map(l=>l.startsWith('          ')?l.slice(10):l).join('\n');
}

test('importable Pages browser tool parses as real ESM',()=>{
 const dir=mkdtempSync(join(tmpdir(),'efhc-pages-v903-'));
 try {const p=join(dir,'browser-smoke.mjs'); writeFileSync(p,extract());
   const run=spawnSync(process.execPath,['--check',p],{encoding:'utf8',timeout:15000});
   assert.equal(run.status,0,run.stderr);
 } finally {rmSync(dir,{recursive:true,force:true});}
});

test('Chrome checks are independent and aggregate failures before failing CI',()=>{
 const source=extract();
 const cases=[...source.matchAll(/await runIndependentCheck\('([^']+)'/g)].map(m=>m[1]);
 assert.deepEqual(cases,[
   'shell-rendered-geometry','shell-navigation-and-back','panels-activation','panels-portfolio',
   'ranks-responsive','ranks-pagination','tasks-themes-and-variants','tasks-demo-action',
   'route-faq','route-hub','route-admin','route-provider'
 ]);
 assert.match(source,/EFHC_BROWSER_REGRESSION_AGGREGATE count=/);
 assert.match(source,/EFHC_BROWSER_CHECK_SUMMARY=/);
 assert.match(source,/checkFailures, checkOutcomes/);
 assert.match(source,/process\.exitCode=1/);
 assert.match(source,/EFHC_BROWSER_INFRA_BLOCKER/);
 assert.equal(new Set(cases).size,cases.length);
});

test('aggregation helper continues after feature failure, but raises on transport failure',async()=>{
 const source=extract();
 const fn=source.split('async function runIndependentCheck(name, task) {')[1].split('\n\nconst diagnosticDir')[0];
 assert.ok(fn.includes("checkFailures.push(failure)"));
 const body='async function runIndependentCheck(name, task) {'+fn;
 const logs=[]; const fakeConsole={log:(...x)=>logs.push(x.join(' ')),error:(...x)=>logs.push(x.join(' '))};
 const make=new Function('fakeConsole',`const checkOutcomes=[],checkFailures=[];let currentRoute='/';\nconst console=fakeConsole,track=()=>{},limitText=x=>String(x).slice(0,240);\n${body}\nreturn {runIndependentCheck,checkOutcomes,checkFailures}`);
 const {runIndependentCheck,checkOutcomes,checkFailures}=make(fakeConsole);
 await runIndependentCheck('first',async()=>{throw Error('CSS REGRESSION')});
 await runIndependentCheck('second',async()=>{});
 await runIndependentCheck('third',async()=>{throw Error('PANEL REGRESSION')});
 assert.deepEqual(checkOutcomes.map(x=>x.status),['FAIL','PASS','FAIL']);
 assert.deepEqual(checkFailures.map(x=>x.section),['first','third']);
 await assert.rejects(runIndependentCheck('infra',async()=>{throw Error('CDP timeout: Runtime.evaluate')}),/EFHC_BROWSER_INFRA_BLOCKER/);
 assert.equal(checkFailures.length,3);
});

test('Ranks override supersedes generic clipping only within Ranks hero',()=>{
 assert.match(css,/\.efhc-independent-shell\[data-interface-app-mode="user"\][\s\S]*?\.efhc-ranks-shell\[data-kg\][\s\S]*?\[data-ranks-hero-summary="responsive-ranks-summary"\][\s\S]*?\.efhc-game-stat_value\s*\{\s*overflow:\s*visible/);
 assert.match(css,/overflow-wrap:\s*anywhere/);
 assert.doesNotMatch(css,/!important/);
});
