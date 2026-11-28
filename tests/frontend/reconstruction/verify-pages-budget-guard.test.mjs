import { fileURLToPath as sourcePathFromUrl } from 'node:url';
const sourceUrl = new URL('../../../frontend/src/reconstruction/', import.meta.url);
const sourceDir = sourcePathFromUrl(new URL('.', sourceUrl));
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
const script = resolve(sourceDir, 'pages_ci/budgets.mjs');

function withBuild(callback) {
  const dir = mkdtempSync(join(tmpdir(), 'efhc-pages-budget-v907-'));
  try { return callback(dir); } finally { rmSync(dir, { recursive: true, force: true }); }
}
function makeBuild(dir, buffer) {
  const js = join(dir, '.next/static/chunks/demo.js');
  mkdirSync(resolve(js, '../'), { recursive: true });
  writeFileSync(js, buffer);
  writeFileSync(join(dir, '.next/build-manifest.json'), JSON.stringify({pages: {'/faq': ['static/chunks/demo.js']}}));
}
test('v907 public Pages real budget accepts a small compiled JS asset and writes actual evidence', () => {
  withBuild((dir) => {
    makeBuild(dir, 'console.log("real-next-asset")');
    const evidence = join(dir, 'budget-evidence.json');
    const result = execFileSync(process.execPath, [script], { cwd: dir, env: { ...process.env, EFHC_BUDGET_OUTPUT: evidence }, encoding: 'utf8' });
    const data = JSON.parse(readFileSync(evidence, 'utf8'));
    assert.match(result, /PASS/);
    assert.equal(data.status, 'PASSED');
    assert.equal(data.baseline_comparison, 'NOT_AVAILABLE_IN_PUBLIC_PAGES_RUNNER');
    assert.equal(data.rows[0].gzip_budget, 300000);
    assert.ok(data.rows[0].gzip_bytes > 0);
  });
});
test('v907 public Pages budget genuinely rejects oversized compiled assets, never mock PASS', () => {
  withBuild((dir) => {
    const bytes = Buffer.alloc(420000);
    let seed = 17;
    for (let i = 0; i < bytes.length; i += 1) {
      seed ^= seed << 13;
      seed ^= seed >>> 17;
      seed ^= seed << 5;
      bytes[i] = seed & 255;
    }
    makeBuild(dir, bytes);
    const result = spawnSync(process.execPath, [script], { cwd: dir, encoding: 'utf8' });
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, /FAIL route=\/faq/);
  });
});
test('v907 public Pages budget rejects missing Next build manifest', () => {
  withBuild((dir) => {
    const result = spawnSync(process.execPath, [script], { cwd: dir, encoding: 'utf8' });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /ENOENT/);
  });
});
