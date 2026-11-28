import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

// Preflight for a CSSNano failure observed on GitHub Pages v875:
// :not([data-hb="HB-14" data-canon-hb="HB-14"]) is not a valid CSS selector.
// Track attribute blocks, excluding = within quoted values (and brackets in strings).
const stylesDir = path.resolve(sourceDir, '../styles');
function inspectFile(file) {
  const source = fs.readFileSync(file, 'utf8');
  const bad = [];
  let quote = '', escaping = false, comment = false, attr = null;
  for (let i = 0; i < source.length; i++) {
    const c = source[i], n = source[i+1];
    if (comment) { if (c === '*' && n === '/') {comment = false; i++;} continue; }
    if (escaping) {escaping = false; continue;}
    if (c === '\\') {escaping = true; continue;}
    if (quote) {if (c === quote) quote = ''; continue;}
    if (c === '"' || c === "'") {quote = c; continue;}
    if (c === '/' && n === '*') {comment = true; i++; continue;}
    if (c === '[' && attr === null) {attr = {start:i, equals:0};continue;}
    if (c === ']' && attr !== null) {if (attr.equals>1) bad.push(source.slice(attr.start, i+1));attr = null;continue;}
    if (c === '=' && attr !== null) {attr.equals++;}
  }
  return bad;
}
function cssFiles(dir) {return fs.readdirSync(dir,{withFileTypes:true}).flatMap(x=>x.isDirectory()?cssFiles(path.join(dir,x.name)):x.name.endsWith('.css')?[path.join(dir,x.name)]:[]);}
test('all imported CSS attribute selectors have at most one unquoted attribute equality operator',()=>{
  const errors = cssFiles(stylesDir).flatMap(file=>inspectFile(file).map(selector=>`${path.relative(stylesDir,file)}: ${selector}`));
  assert.deepEqual(errors, [], 'Invalid CSS attribute selectors would fail Next CSSNano');
});
test('canonical HB and BN filters have separate bracketed attributes',()=>{
  const s=fs.readFileSync(path.join(stylesDir,'user-shell-layout.css'),'utf8');
  assert.ok(s.includes(':not([data-hb="HB-14"][data-canon-hb="HB-14"])'));
  assert.ok(s.includes('[data-bn="BN-01"][data-canon-bn="BN-01"]'));
});
