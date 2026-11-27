import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const root = new URL("../../", import.meta.url);
test("All supported public languages and frozen FAQ assets pass the source release gate", () => {
  const run = spawnSync(process.execPath, ["src/reconstruction/pages_ci/verify-production-assets.mjs"], {
    cwd: root, encoding: "utf8",
  });
  assert.equal(run.status, 0, run.stdout + run.stderr);
  assert.match(run.stdout, /languages=16/);
});

test("Serwist is the only persistent cache for public locale dictionaries", () => {
  const source = readFileSync(new URL("src/lib/i18n.ts", root), "utf8");
  assert.doesNotMatch(source, /localStorage|sessionStorage|localeChecksum/);
  assert.match(source, /fetch\(publicAssetPath\(/);
  const sourceMetadata = JSON.parse(readFileSync(new URL("public/pwa-build.json", root), "utf8"));
  for (const key of ["cache_limits", "locale_checksums", "faq_checksums", "precache"]) {
    assert.equal(Object.hasOwn(sourceMetadata, key), false);
  }
});
