import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';

const require = createRequire(import.meta.url);
// Use workspace TypeScript in CI; fall back to the installed global compiler locally.
const ts = (() => {
  try { return require('typescript'); }
  catch {
    const { execFileSync } = require('node:child_process');
    const globalRoot = execFileSync('npm', ['root', '-g'], { encoding: 'utf8' }).trim();
    return require(join(globalRoot, 'typescript'));
  }
})();
const frontend = resolve(sourceDir, '../..');
const src = (name) => readFileSync(resolve(frontend, name), 'utf8');

// Run actual TS source logic rather than only comparing regex markers.
const temp = mkdtempSync(join(tmpdir(), 'efhc-v881-d8-'));
try {
  mkdirSync(join(temp, 'ton'), { recursive: true });
  mkdirSync(join(temp, 'lib'), { recursive: true });
  mkdirSync(join(temp, 'types'), { recursive: true });
  for (const [source, target] of [
    ['src/lib/ton/units.ts', 'ton/units.js'],
    ['src/lib/format.ts', 'format.js'],
    ['src/lib/browserFallback.ts', 'lib/browserFallback.js'],
    ['src/types/identity.ts', 'types/identity.js'],
  ]) {
    const code = ts.transpileModule(src(source), {
      compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
    }).outputText;
    writeFileSync(join(temp, target), code);
  }
  const fmt = require(join(temp, 'format.js'));
  test('Rank example 8123.12345678 kWh is displayed without lost digits', () => {
    assert.equal(fmt.format8('8123.12345678'), '8123.12345678');
    assert.equal(fmt.format8('0'), '0.00000000');
    assert.equal(fmt.format8('421.125'), '421.12500000');
  });
  test('D8 rejects excess fractional precision or silent integer inflation', () => {
    for (const bad of ['1.123456789','1,23','abc','1.2abc','1e-8','1..2',' 1_000 ']) {
      assert.throws(() => fmt.formatFixedDown(bad, 8), undefined, bad);
    }
    assert.throws(() => fmt.formatFixedDown('1', 9));
    assert.equal(fmt.formatFixedDown('3.14159', 2), '3.14'); // only intentional D2 views
  });
  test('Portfolio total sums atomic decimal strings, not floating Number', () => {
    assert.equal(fmt.sumScaledDown('0.10000000','0.20000000',8), '0.30000000');
    const s = src('src/components/dashboard/PanelsPortfolioRuntime.tsx');
    assert.match(s, /sumScaledDown\(acc, panel\.generated_kwh, 8\)/);
    assert.doesNotMatch(s, /return `\$\{sum\.toFixed\(8\)\} kWh`/);
  });
  test('D8 preserved on all observed financial display paths', () => {
    const paths = [
      'src/pages/ranks.tsx','src/pages/exchange.tsx',
      'src/components/energy/EnergyMvpSummary.tsx',
      'src/components/public/PublicEnergyInteractiveOverview.tsx',
      'src/components/admin/AdminUsersDashboardRuntime.tsx',
      'src/components/admin/AdminPanelsDashboardRuntime.tsx',
    ];
    for (const p of paths) {
      assert.doesNotMatch(src(p), /formatFixedDown\([^\n]*, 2\)/, p);
      assert.match(src(p), /format8\(/, p);
    }
  });
  test('Unsynchronized display models cannot invent generation or balances; D8 remains exact', () => {
    const fallback = require(join(temp, 'lib/browserFallback.js'));
    const owner = '0000003001';
    const empty = fallback.emptyOwnerSnapshot(owner);
    assert.equal(empty.profile.global_id, owner);
    assert.equal(empty.exchange_preview.ok, false);
    for (const snapshot of [fallback.getBrowserFallbackSnapshot(), empty]) {
      for (const field of ['main_balance', 'bonus_balance', 'available_kwh', 'total_generated_kwh', 'gen_per_sec_base', 'gen_per_sec_vip']) {
        assert.equal(snapshot.profile[field], '0.00000000', field);
      }
      assert.equal(snapshot.profile.is_vip, false);
      assert.equal(snapshot.profile.has_activ, false);
      assert.equal(snapshot.panels.active_count, 0);
      assert.equal(snapshot.panels.total_generated_by_panels, '0.00000000');
      assert.equal(snapshot.exchange_preview.max_exchangeable_kwh, '0.00000000');
      assert.equal(snapshot.meta.gen_per_sec_effective, '0.00000000');
    }
    assert.throws(() => fallback.emptyOwnerSnapshot('0000000000'));
  });
  test('Original FAQ route is excluded from asset-only basePath rewrite', () => {
    const text = readFileSync(new URL('./verify-pages-faq-route.test.mjs', import.meta.url), 'utf8');
    assert.match(text, /preserves the real FAQ route/);
    assert.match(src('src/pages/faq.tsx'), /export default function|function FaqPage/);
  });
} finally {
  // Node test callbacks run after module evaluation: leave files available
  // for this process, remove at exit instead of immediately.
  process.once('exit', () => rmSync(temp, { force: true, recursive: true }));
}
