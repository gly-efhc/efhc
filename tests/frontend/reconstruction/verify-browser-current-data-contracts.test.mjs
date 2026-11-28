import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../../../deployment/pages-tools/browser-smoke.mjs',import.meta.url),'utf8');
const helpers=source.slice(source.indexOf('function isD8('),source.indexOf('const diagnosticDir'));
const {isD8,utcMillis,assertPortfolio,assertRanksRows}=new Function(helpers+'\nreturn {isD8,utcMillis,assertPortfolio,assertRanksRows};')();
test('D8 parser accepts arbitrary valid values and rejects truncated or invalid decimals',()=>{
  for(const value of ['0.00000000','42.12345678','9007199254740993.00000001'])assert.equal(isD8(value),true);
  for(const value of ['42.1','-1.00000000','1.000000001','1e8',''])assert.equal(isD8(value),false);
  assert.doesNotMatch(source,/PAGES_FROZEN_(?:BALANCE|ENERGY)_FIXTURE_MISSING/);
});
test('portfolio validator checks batch, identity, UTC, order and uniqueness',()=>{
  const rows=[{id:'PNL-00000007',date:'01.01.2026, 00:00:00 UTC',overflow:false},{id:'PNL-00000009',date:'02.01.2026, 00:00:00 UTC',overflow:false}];
  const model=(r,batch='20')=>({mode:'portfolio-page',tab:'active',order:'oldest-first',batch,rows:r,ids:r.map(x=>x.id)});
  assert.doesNotThrow(()=>assertPortfolio(model(rows),'active','oldest-first'));
  assert.throws(()=>assertPortfolio(model(rows.slice().reverse()),'active','oldest-first'),/SORT_INVALID/);
  assert.throws(()=>assertPortfolio(model([rows[0],rows[0]]),'active','oldest-first'),/DUPLICATE/);
  assert.throws(()=>assertPortfolio(model(rows,'40'),'active','oldest-first'),/BATCH_INVALID/);
  assert.throws(()=>assertPortfolio(model([{...rows[0],id:'PNL-00000000'}]),'active','oldest-first'),/DATE_GEOMETRY/);
  assert.equal(Number.isNaN(utcMillis('30.02.2026, 00:00:00 UTC')),true);
});
test('rank validator retains exact D8 order and equal-score tie semantics',()=>{
  const rows=[{pos:7,energy:'9007199254740993.00000002'},{pos:8,energy:'9007199254740993.00000001'},{pos:8,energy:'9007199254740993.00000001'}];
  assert.doesNotThrow(()=>assertRanksRows(rows));
  assert.throws(()=>assertRanksRows(rows.slice().reverse()),/SORT_OR_TIE/);
  assert.throws(()=>assertRanksRows([rows[1],{...rows[2],pos:9}]),/SORT_OR_TIE/);
  assert.throws(()=>assertRanksRows([{pos:1,energy:'1.1'}]),/ROW_INVALID/);
  assert.doesNotMatch(source,/efhc:react:unified-demo:v893|OWNER_RANKS_220_DEMO/);
});
test('guest gate and provider state are not replaced by visual proof',()=>{
  assert.match(source,/PAGES_ADMIN_GUEST_GATE_INVALID/);
  assert.match(source,/VISUAL_ONLY ADMIN/);
  assert.match(source,/providerSource!==\x27server-session\x27/);
  assert.match(source,/PAGES_PROVIDER_GUEST_SESSION_INVALID/);
});
