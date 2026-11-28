import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const ui = readFileSync(new URL('../../../frontend/src/components/profile/ProfileHistorySection.tsx', import.meta.url), 'utf8');
const service = readFileSync(new URL('../../../frontend/src/services/profile.service.ts', import.meta.url), 'utf8');

test('the Balance template puts authoritative PNL only in panel debit details', () => {
  assert.match(service, /panel_public_id: z\.string\(\)\.nullable\(\)\.optional\(\)/);
  assert.match(ui, /direction === "debit" && item\.reason === "panel_activation"/);
  assert.match(ui, /details\.push\(\{ label: t\("panels\.panel_id"\), value: panelPublicId\.replace\("-", ""\) \}\)/);
  assert.equal(ui.match(/panelPublicId/g).length, 4, 'no PNL in title or subtitle');
  assert.match(ui, /details\.push\(\{ label: t\("history\.detail_rate"\), value: "1 kWh = 1 EFHCm" \}\)/);
});
