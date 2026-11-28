import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const section = readFileSync(new URL('../../../frontend/src/components/profile/ProfileHistorySection.tsx', import.meta.url), 'utf8');

test('Balance can request the next server page when no loaded rows match the filter', () => {
  assert.match(section, /const showEmptyFeed = isReferenceBalance && !props\.loading && operations\.length === 0;/);
  const blank = section.split(') : showEmptyFeed ? (')[1]?.split(') : showFilterEmpty ? (')[0] || '';
  assert.match(blank, /\{props\.nextCursor \? <BalanceHistoryLoadMore onLoadMore=\{props\.onLoadMore\} \/> : null\}/);
  assert.doesNotMatch(blank, /<BalanceHistoryEmptyState/);
});
