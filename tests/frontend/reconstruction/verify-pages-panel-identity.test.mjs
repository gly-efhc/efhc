import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read = p => readFileSync(new URL('../../../' + p, import.meta.url), 'utf8');
test('Pages browser portfolio expects canonical public PNL, not obsolete nine-digit fixtures', () => {
  const source = read('deployment/pages-tools/browser-smoke.mjs');
  assert.match(source,/function assertPortfolio\(/);
  assert.match(source,/PNL-\(\?!00000000\$\)/);
  assert.doesNotMatch(source,/PNL-00000060|PNL-00000101|PNL-00000160/);
  assert.match(read('backend/app/services/panels_service.py'), /PNL-\{int\(number\):08d\}/);
  assert.match(read('frontend/src/pages/panels/portfolio.tsx'), /data-panel-identity=\{p\.public_id \?\? undefined\}/);
});
