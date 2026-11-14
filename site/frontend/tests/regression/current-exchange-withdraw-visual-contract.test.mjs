import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const css = source("../../src/styles/globals.css");
const registry = source("../../src/lib/interfaceVariantRegistry.ts");
const exchange = source("../../src/pages/exchange.tsx");
const withdraw = source("../../src/pages/withdraw.tsx");

function style(selector) {
  const start = css.lastIndexOf("/* Exchange physical XH-07 uses the standalone three-row KPI layout.");
  assert.ok(start > 0, "dedicated USER-only visual material must exist");
  const tail = css.slice(start);
  const found = tail.indexOf(selector);
  assert.ok(found >= 0, "missing CSS selector: " + selector);
  const open = tail.indexOf("{", found);
  const close = tail.indexOf("}", open + 1);
  assert.ok(open >= 0 && close > open, "CSS declaration must be closed: " + selector);
  return tail.slice(open + 1, close);
}

test("fourth Exchange template binds to physical XH-07 and owns all three KPI rows", () => {
  assert.match(registry, /"XH-04":"XH-07"/);
  assert.match(exchange, /data-xh=\{heroSurface\.variant\}/);
  assert.match(exchange, /<GameStatsGrid>/);
  assert.equal((exchange.match(/<GameStat\b/g) || []).length, 3);

  const hero = style('.efhc-exchange-shell .efhc-exchange-hero[data-xh="XH-07"] {');
  assert.match(hero, /border-radius:\s*1rem/);
  assert.match(hero, /padding:\s*\.85rem/);
  assert.match(hero, /--efhc-ct-accent-rgb/);
  assert.match(hero, /background-image:\s*radial-gradient/);

  const grid = style('.efhc-exchange-shell .efhc-exchange-hero[data-xh="XH-07"] .efhc-game-stats {');
  assert.match(grid, /grid-template-columns:\s*minmax\(0,1fr\)/);
  const metric = style('.efhc-exchange-shell .efhc-exchange-hero[data-xh="XH-07"] .efhc-game-stat {');
  assert.match(metric, /grid-template-columns:\s*minmax\(0,1fr\) minmax\(0,max-content\)/);
  assert.match(metric, /align-items:\s*center/);
  const value = style('.efhc-exchange-shell .efhc-exchange-hero[data-xh="XH-07"] .efhc-game-stat_value {');
  assert.match(value, /text-align:\s*right/);
  assert.match(value, /tabular-nums/);
});

test("all five Withdraw selections map only to their five physical styles", () => {
  assert.match(registry, /WD:\s*numbered\("WD",\s*5\)/);
  assert.match(registry, /"WD-03":"WD-06"/);
  assert.match(registry, /"WD-04":"WD-10"/);
  assert.match(registry, /"WD-05":"WD-13"/);
  assert.match(withdraw, /data-wd=\{withdrawSurface\.variant\}/);
  assert.doesNotMatch(withdraw, /efhc-withdraw-trust-rail/);
  for (const design of ["WD-02", "WD-06", "WD-10", "WD-13"]) {
    const block = style('.efhc-withdraw-shell[data-wd="' + design + '"] {');
    assert.match(block, /--wd-card:/);
    assert.match(block, /--wd-radius:/);
    assert.match(block, /--wd-shadow:/);
    assert.match(block, /--efhc-ct-accent-rgb/);
  }
  const common = style('.efhc-withdraw-shell[data-wd] {');
  assert.match(common, /--wd-radius:\s*14px/);
  assert.match(common, /--wd-accent:\s*var\(--efhc-ct-accent\)/);
  assert.match(css, /\.efhc-withdraw-shell\[data-wd\] :is\(\s*\.efhc-withdraw-hero,\s*\.efhc-withdraw-create-card,\s*\.efhc-withdraw-requests-history\s*\)/);
});

test("flat Withdraw fourth template keeps no rounded or colored side frame", () => {
  const block = style('.efhc-withdraw-shell[data-wd="WD-10"] {');
  assert.match(block, /--wd-radius:\s*0px/);
  assert.match(block, /--wd-shadow:\s*none/);
  const flat = style('.efhc-withdraw-shell[data-wd="WD-10"] :is(\n  .efhc-withdraw-hero,\n  .efhc-withdraw-create-card,\n  .efhc-withdraw-requests-history\n) {');
  assert.match(flat, /border-inline-color:\s*transparent\s*!important/);
  assert.match(flat, /border-radius:\s*0\s*!important/);
  assert.match(flat, /box-shadow:\s*none\s*!important/);
});

test("fifth Withdraw template has independent CT accent rails, no false invalid styling", () => {
  const block = style('.efhc-withdraw-shell[data-wd="WD-13"] {');
  assert.match(block, /--wd-radius:\s*19px/);
  assert.match(block, /--efhc-ct-accent-rgb/);
  assert.match(css, /\.efhc-withdraw-shell\[data-wd="WD-13"\] \.efhc-withdraw-hero\s*\{\s*box-shadow:\s*inset 0 3px 0 rgba\(var\(--efhc-ct-accent-rgb\)/);
  assert.match(css, /\.efhc-withdraw-shell\[data-wd="WD-13"\] :is\(\s*\.efhc-withdraw-create-card,\s*\.efhc-withdraw-requests-history\s*\)\s*\{\s*box-shadow:\s*inset 3px 0 0 rgba\(var\(--efhc-ct-accent-rgb\)/);
  assert.match(css, /\.efhc-input:not\(\[data-amount-state="invalid"\]\)/);
  assert.match(withdraw, /data-amount-state=\{amountTouched && amountIssue/);
  assert.doesNotMatch(withdraw, /withdraw\.latest_operations/);
});
