import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
/** OWNER continuation 0011–0012; R06-backed regression contract.
 * These source tests supplement, but never substitute for, actual Next/Chrome E2E. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
const here=sourceDir;
const read = p=>fs.readFileSync(path.resolve(here,p),'utf8');

test('R06 ranks D8 is atomic, only within the hero; no global styles or list changes',()=>{
 const css=read('../styles/ranks-hero.css');
 const anchor='.efhc-ranks-shell[data-kg] [data-ranks-hero-energy-d8="true"]';
 const i=css.indexOf(anchor);
 assert.ok(i>0,'Missing exact D8 span selector');
 const body=css.slice(i,css.indexOf('}',i));
 assert.match(body,/white-space:\s*nowrap/);
 assert.match(body,/overflow-wrap:\s*normal/);
 assert.match(body,/word-break:\s*normal/);
 assert.doesNotMatch(body,/anywhere/);
 assert.doesNotMatch(css,/\.efhc-rank-card|\.efhc-rank-username|\.efhc-rank-generated|!important/);
 const ranks=read('../pages/ranks.tsx');
 assert.match(ranks,/value=\{<span data-ranks-hero-energy-d8="true">\{myMetric\}<\/span>\}/);
 assert.match(ranks,/data-ranks-load-more="true"/);
});

test('R06 live Chrome check measures text fragments, not only container overflow',()=>{
 const script=read('../../../deployment/pages-tools/browser-smoke.mjs');
 assert.ok((script.match(/const energyFragments=/g)||[]).length>=1);
 assert.ok((script.match(/energyWrapOrClip/g)||[]).length>=3);
 assert.match(script,/energyRange\.getClientRects\(\)/);
 assert.match(script,/OWNER_RANKS_PAGE_SIZE_OR_PROGRESS_INVALID/);
});

test('R06 archive requires independent pagination, no duplicates and scroll anchor',()=>{
 const script=read('../../../deployment/pages-tools/browser-smoke.mjs');
 for(const x of ['OWNER_PORTFOLIO_PAGE_OVERFETCH','OWNER_PORTFOLIO_DATA_NOT_QUALIFIED',
  'OWNER_PORTFOLIO_SCROLL_ANCHOR_OR_DUPLICATE','OWNER_PORTFOLIO_SORT_INVALID'])
  assert.ok(script.includes(x),x);
 const source=read('../pages/panels/portfolio.tsx');
 assert.match(source,/data-panels-tab-button="archive"/);
 assert.match(source,/data-panels-scroll-mode="canonical-window"/);
 assert.match(source,/data-panel-identity=\{p\.public_id \?\? undefined\}/);
 assert.doesNotMatch(source,/data-panel-identity=\{[^}]*String\(p\.id\)/);
});

test('R06 source evidence does not authorize changes to protected UX and economics',()=>{
 const ranks=read('../pages/ranks.tsx');
 const portfolio=read('../pages/panels/portfolio.tsx');
 assert.match(ranks,/useRankTopPages\(/);
 assert.match(ranks,/void moreQ\.fetchNextPage\(\)/);
 assert.match(portfolio,/current === "oldest" \? "newest" : "oldest"/);
 assert.match(portfolio,/listQuery\.fetchNextPage\(\)/);
});
