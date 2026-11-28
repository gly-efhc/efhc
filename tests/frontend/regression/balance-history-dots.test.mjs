import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const section = readFileSync(new URL('../../../frontend/src/components/profile/ProfileHistorySection.tsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('../../../frontend/public/react-runtime-layout.css', import.meta.url), 'utf8');

test('Balance HI indicators use one reserved row above the history heading, not the floating layer', () => {
  assert.match(section, /registerDots: !isReferenceBalance/);
  assert.match(section, /data-history-block="head">\s*\{isReferenceBalance && historySurface\.active \? \(\s*<div[^>]*data-indicator-group="HI"[^>]*data-indicator-placement="balance-history"[^>]*>/s);
  assert.match(section, /<VariantIndicatorDots group="HI" effective=\{effective\} \/>[\s\S]*?<h2>\{t\("history\.operations_title"\)\}<\/h2>/);
  const rule = css.match(/\[data-indicator-placement="balance-history"\]\s*\{([^}]+)\}/)?.[1] || '';
  for (const layout of [/position:\s*static/, /grid-column:\s*1\s*\/\s*-1/, /justify-self:\s*center/, /transform:\s*none/]) assert.match(rule, layout);
});
