import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
/** Current server-authoritative portfolio contract. Historical DEMO data is not a runtime fixture. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {sourceRuntime} from '../helpers/source-runtime.mjs';
const folder=sourceDir;
const read=(name)=>fs.readFileSync(path.resolve(folder,name),'utf8');
test('API pagination passes authoritative cursor and tab, with exactly 20 per request',async()=>{
 const calls=[];
 const h=sourceRuntime({overrides:{'../lib/api':{apiRequest:async(...args)=>{calls.push(args);return {items:[],next_cursor:null};}},
 '../lib/api/generated/economicUserSeamValidators':{parsePanelsPageResponse:value=>value}}});
 // The mocked transport is confined to this unit test; schema validation has its own tests.
 const svc=h.load('services/panels.service.ts');
 const signal=new AbortController().signal;
 for(const tab of ['active','archive']){
  await svc.getPanelsPage({tab,cursor:null,signal});
  await svc.getPanelsPage({tab,cursor:'opaque+/=',signal});
 }
 for(let i=0;i<calls.length;i++){
  const [url,method,opts]=calls[i],parsed=new URL(url,'https://example.invalid');
  assert.match(parsed.pathname,i<2?/\/active$/:/\/archive$/);
  assert.equal(parsed.searchParams.get('limit'),'20');
  assert.equal(parsed.searchParams.get('cursor'),i%2?'opaque+/=':null);
  assert.equal(method,'GET');assert.equal(opts.signal,signal);
 }
});
test('React query key isolates owner, tab and sort; API remains authoritative',()=>{
 const s=read('../queries/usePanels.ts');
 assert.match(s,/queryKey: \[\.\.\.queryKeys\.panels\.list\(globalId, tab\), sortDirection\]/);
 assert.match(s,/enabled: Boolean\(globalId\)/);
 assert.match(s,/getPanelsPage\(\{ tab, cursor: pageParam, signal \}\)/);
 assert.match(s,/getNextPageParam: \(lastPage\) => lastPage\.next_cursor \?\? undefined/);
 assert.doesNotMatch(s,/demoPanelsPage/);
});
test('portfolio sorts loaded pages by activation date with deterministic ID tie-break',()=>{
 const s=read('../pages/panels/portfolio.tsx');
 assert.match(s,/pages\.flatMap\(\(page\) => page\.items\)/);
 assert.match(s,/return \[\.\.\.items\]\.sort/);
 assert.match(s,/sortDirection === "oldest" \? delta : -delta/);
 assert.match(s,/leftId - rightId\s*:\s*rightId - leftId/);
});
test('onScroll uses visible panel identity rather than raw added scrollHeight',()=>{
 const s=read('../pages/panels/portfolio.tsx');
 assert.match(s,/data-panel-identity=\{p\.public_id \?\? undefined\}/);
 assert.match(s,/visibleId: visible\?\.dataset\.panelIdentity/);
 assert.match(s,/visible\.getBoundingClientRect\(\)\.top/);
 assert.doesNotMatch(s,/node\.scrollTop\s*=\s*anchor\.scrollTop\s*\+\s*addedHeight/);
 assert.match(s,/data-panels-batch-size="20"/);
});
test('PC-01 density and UTC seconds are scoped, fixed token Activ stays neutral on archived',()=>{
 const s=read('../pages/panels/portfolio.tsx');
 const css=read('../styles/panels-layout.css');
 assert.match(s, /\$\{dd\}\.\$\{mm\}\.\$\{yy\}, \$\{hh\}:\$\{mi\}:\$\{ss\} UTC/);
 assert.match(s,/data-active=\{p\.is_active \? "true" : "false"\}/);
 assert.match(s,/data-i18n-fixed-token="Activ"/);
 assert.match(css,/\.efhc-panels-portfolio-shell \.efhc-panels-card-surface\[data-pc="PC-01"\]/);
 assert.doesNotMatch(css,/\.efhc-panels-portfolio-shell \.efhc-panels-card-surface\[data-pc="PC-02"\]/);
});
test('Pages CI has a real DOM gate for current pagination, dates and sorted tabs',()=>{
 const s=read('../../../deployment/pages-tools/browser-smoke.mjs');
 for(const label of ['OWNER_PORTFOLIO_INITIAL_OVERFETCH','OWNER_PORTFOLIO_DATA_NOT_QUALIFIED','OWNER_PORTFOLIO_SCROLL_ANCHOR_OR_DUPLICATE','OWNER_PORTFOLIO_SORT_INVALID','OWNER_PORTFOLIO_CARD_DATE_GEOMETRY_REGRESSION']) assert.ok(s.includes(label),label);
});
