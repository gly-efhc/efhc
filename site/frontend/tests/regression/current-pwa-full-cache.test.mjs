import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync, unlinkSync, copyFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import vm from "node:vm";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const pagesTools = path.resolve(frontend, "../ci/pages-tools");
const publicDir = path.join(frontend, "public");
const read = (name) => readFileSync(path.join(frontend, name), "utf8");
const run = (script, root) => spawnSync("python3", [
  path.join(pagesTools, script), "--directory", root, "--base-path", "/efhc",
], { encoding: "utf8" });

test("Pages has a scoped Service Worker and does not delete the PWA files", () => {
  const prepare = readFileSync(path.join(pagesTools, "prepare_pages.py"), "utf8");
  const runtime = read("src/components/PwaRuntimeStatus.tsx");
  const app = read("src/pages/_app.tsx");
  assert.doesNotMatch(prepare, /public\/sw\.js'\)\.unlink/);
  assert.doesNotMatch(prepare, /public\/manifest\.webmanifest'\)\.unlink/);
  assert.match(runtime, /serviceWorker\.register\(`\$\{appBasePath\(\)\}\/sw\.js`/);
  assert.match(runtime, /efhc:pwa-registration-failed/);
  assert.match(app, /router\.basePath\}\/manifest\.webmanifest/);
  assert.doesNotMatch(runtime, /return idle\(\(\) => waiting\.postMessage\(\{ type: "SKIP_WAITING" \}/);
});

test("Complete compiled export is precached, stable on repeated builds and verified fail-closed", (t) => {
  const root = mkdtempSync(path.join(tmpdir(), "efhc-full-pwa-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const put = (name, contents) => {
    const destination = path.join(root, name);
    mkdirSync(path.dirname(destination), { recursive: true });
    writeFileSync(destination, contents, "utf8");
  };
  put("index.html", '<html><script id="__NEXT_DATA__"></script><script src="/efhc/_next/static/main.js"></script></html>');
  put("panels/index.html", "<html>panels shell</html>");
  put("admin/users/index.html", "<html>admin shell without user data</html>");
  put("browser-shop/index.html", "<html>shop shell</html>");
  put("_next/static/main.js", "globalThis.__EFHC_TEST_SHELL__=true;");
  put("_next/static/main.css", "body { color: white; }");
  put("public-runtime-config.js", "window.__EFHC_PUBLIC_CONFIG__={};");
  copyFileSync(path.join(publicDir, "sw.js"), path.join(root, "sw.js"));
  copyFileSync(path.join(publicDir, "manifest.webmanifest"), path.join(root, "manifest.webmanifest"));
  copyFileSync(path.join(publicDir, "offline.html"), path.join(root, "offline.html"));
  copyFileSync(path.join(publicDir, "offline-readonly.html"), path.join(root, "offline-readonly.html"));
  const first = run("fix_pages_assets.py", root);
  assert.equal(first.status, 0, first.stderr);
  const config = JSON.parse(readFileSync(path.join(root, "pwa-build.json"), "utf8"));
  assert.equal(config.static_export, true);
  for (const route of ["index.html", "panels/index.html", "admin/users/index.html", "browser-shop/index.html"]) {
    assert.ok(config.precache.includes("/efhc/" + route), "Missing cached page: " + route);
  }
  assert.ok(config.precache.includes("/efhc/_next/static/main.js"));
  assert.ok(config.precache.includes("/efhc/_next/static/main.css"));
  assert.ok(!config.precache.some((url) => url.includes("/api/") || url.includes(".env")));
  const manifest = JSON.parse(readFileSync(path.join(root, "manifest.webmanifest"), "utf8"));
  assert.equal(manifest.scope, "/efhc/");
  assert.equal(manifest.id, "/efhc/");
  assert.ok(manifest.start_url.startsWith("/efhc/"));
  const worker = readFileSync(path.join(root, "sw.js"), "utf8");
  new vm.Script(worker);
  assert.match(worker, /const EFHC_PWA_BUILD_CONFIG =/);
  const verify = run("verify_export.py", root);
  assert.equal(verify.status, 0, verify.stderr);
  const again = run("fix_pages_assets.py", root);
  assert.equal(again.status, 0, again.stderr);
  assert.equal(readFileSync(path.join(root, "sw.js"), "utf8"), worker, "same build must not prepend another config");
  unlinkSync(path.join(root, "admin/users/index.html"));
  const rejected = run("verify_export.py", root);
  assert.notEqual(rejected.status, 0, "missing offline page must block deployment");
});

test("Existing USER data and local settings are retained rather than replaced by revalidation", () => {
  assert.match(read("src/lib/queryClient.ts"), /refetchOnMount: false/);
  assert.match(read("src/hooks/useSnapshot.ts"), /refetchOnMount: false/);
  assert.match(read("src/queries/usePanels.ts"), /refetchOnMount: false/);
  const settings = read("src/lib/settings.ts");
  assert.match(settings, /local choice made while the Telegram request was pending/i);
  assert.match(settings, /window\.localStorage\.getItem\(`\$\{KEY\}:\$\{owner\}`\)/);
  const activity = read("src/lib/frontendActivity.ts");
  assert.match(activity, /refetchQueries/);
  const energy = read("src/pages/index.tsx");
  assert.match(energy, /LIVE_TICK_MS = 333/);
  assert.match(energy, /performance\.now\(\)/);
});
