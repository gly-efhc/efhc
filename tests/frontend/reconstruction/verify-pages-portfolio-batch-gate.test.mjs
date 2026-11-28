import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const ts=require('typescript');
const folder=sourceDir;
const load=()=>{
  const source=fs.readFileSync(path.join(folder,'panelPaginationGate.ts'),'utf8');
  const {outputText,diagnostics}=ts.transpileModule(source,{fileName:'panelPaginationGate.ts',reportDiagnostics:true,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}});
  assert.equal((diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
  const globals={exports:{}};
  vm.runInNewContext(outputText,globals);
  return globals.exports.shouldRequestNextPanelPage;
};
const params={tab:'active',direction:'oldest',itemCount:20,scrollTop:2294,scrollHeight:2742,clientHeight:448,lastTrigger:null,inFlight:false,loading:false,canLoadMore:true};
test('first bottom approach requests exactly one additional portfolio page',()=>{
  const allowed=load();assert.equal(allowed(params),true);
  const prev={tab:'active',direction:'oldest',itemCount:20,scrollTop:2294};
  assert.equal(allowed({...params,lastTrigger:prev}),false,'repeated scroll of the same position is not a second user intent');
  assert.equal(allowed({...params,lastTrigger:prev,itemCount:40}),false,'added rows without actual movement cannot fetch the third page');
  assert.equal(allowed({...params,lastTrigger:prev,inFlight:true}),false,'in flight prevents concurrent cursor requests');
  assert.equal(allowed({...params,lastTrigger:prev,loading:true}),false);
});
test('next 20 panels require deliberate movement by half viewport',()=>{
  const allowed=load();const lastTrigger={tab:'active',direction:'oldest',itemCount:20,scrollTop:2294};
  const onSecondPage={...params,itemCount:40,scrollTop:2294+223,scrollHeight:2294+223+448,lastTrigger};
  assert.equal(allowed(onSecondPage),false);
  assert.equal(allowed({...onSecondPage,scrollTop:2294+224,scrollHeight:2294+224+448}),true);
  assert.equal(allowed({...onSecondPage,scrollTop:2294+250,scrollHeight:2294+250+448,canLoadMore:false}),false);
});
test('only actual list bottom may load, inactive list or wrong dimensions cannot',()=>{
  const allowed=load();
  assert.equal(allowed({...params,scrollTop:1000}),false);
  assert.equal(allowed({...params,scrollHeight:300,clientHeight:448}),false);
  assert.equal(allowed({...params,loading:true}),false);
  assert.equal(allowed({...params,canLoadMore:false}),false);
});
test('tab and direction are independent pagination streams',()=>{
  const allowed=load();
  const prev={tab:'active',direction:'oldest',itemCount:20,scrollTop:2294};
  assert.equal(allowed({...params,lastTrigger:prev,tab:'archive'}),true);
  assert.equal(allowed({...params,lastTrigger:prev,direction:'newest'}),true);
});
test('React uses synchronous request gate and resets on both tabs and sort',()=>{
  const source=fs.readFileSync(path.resolve(folder,'../pages/panels/portfolio.tsx'),'utf8');
  const marker=source.indexOf('lastPageTriggerRef.current = request;');
  assert.ok(marker>=0);
  assert.ok(source.indexOf('inFlightPageTriggerRef.current = request;',marker)<source.indexOf('listQuery.fetchNextPage()',marker));
  assert.match(source,/shouldRequestNextPanelPage\(\{/);
  assert.equal((source.match(/resetPageTrigger\(\);/g)||[]).length,3);
  assert.match(source,/data-panels-batch-size="20"/);
  assert.match(source,/pendingScrollAnchorRef.current = \{/);
});

test('Pages Chrome smoke fails explicitly on auto-overfetch and checks settled page length',()=>{
  const yaml=fs.readFileSync(path.resolve(folder,'../../../deployment/pages-tools/browser-smoke.mjs'),'utf8');
  assert.match(yaml,/OWNER_PORTFOLIO_PAGE_OVERFETCH/);
  assert.match(yaml,/await sleep\(450\);/);
  assert.match(yaml,/if\(portfolio\.ids\.length>expected\)/);
  assert.match(yaml,/OWNER_PORTFOLIO_DATA_NOT_QUALIFIED/);
});
