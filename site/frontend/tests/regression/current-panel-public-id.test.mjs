import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {sourceRuntime} from '../helpers/source-runtime.mjs';

test('only authoritative PNL plus exactly eight digits is accepted by the generated API contract', () => {
  const {PanelPublicIdSchema} = sourceRuntime().load('lib/api/generated/economicUserSeamValidators.ts');
  for (const value of ['PNL-00000001', 'PNL-00004007', 'PNL-99999999']) {
    assert.equal(PanelPublicIdSchema.parse(value), value);
  }
  for (const value of [null, undefined, '', 'PNL-00000000', 'PNL-000000001',
                        'PNL-0000001', 'ID00000001', 'PNL-0000000X', '#1']) {
    assert.equal(PanelPublicIdSchema.safeParse(value).success, false, String(value));
  }
});

test('portfolio never substitutes a technical id for missing PNL', () => {
  const source=fs.readFileSync(new URL('../../src/pages/panels/portfolio.tsx',import.meta.url),'utf8');
  assert.match(source,/Ошибка целостности PNL/);
  assert.doesNotMatch(source,/PNL-.*String\(p\.id\)/);
  assert.doesNotMatch(source,/\{p\.public_id \? p\.public_id : t\("panels\.panel_id"\)\}/);
});

test('unknown purchase result retains same owner-scoped idempotency attempt', () => {
  const source=fs.readFileSync(new URL('../../src/pages/panels.tsx',import.meta.url),'utf8');
  assert.match(source,/efhc:panel-purchase:pending:/);
  assert.match(source,/pendingPurchaseRef\.current \?\? newIdempotencyKey\(\)/);
  assert.match(source,/recordPendingPurchase\(idk\)/);
  assert.match(source,/await activationMutation\.mutateAsync\(idk\)/);
  assert.match(source,/recordPendingPurchase\(null\)/);
  assert.match(source,/error instanceof ApiError && \[400, 403, 422\]/);
});
