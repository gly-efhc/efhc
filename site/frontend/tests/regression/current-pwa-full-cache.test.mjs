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
  assert.match(runtime, /trackedRegistration\.update\(\)/);
  assert.match(runtime, /staged\.postMessage\(\{ type: "SKIP_WAITING" \}\)/);
  assert.match(runtime, /CLIENT_BUILD_READY/);
  assert.match(runtime, /controllerchange/);
  assert.match(runtime, /attemptIdleReload/);
  assert.match(runtime, /document\.addEventListener\("visibilitychange", checkForUpdate\)/);
});

test("The Pages deploy workflow requires full offline Chromium acceptance before deployment", () => {
  const releaseWorkflow = readFileSync(path.resolve(frontend, "../../.github/workflows/efhc-pages.yml"), "utf8");
  const gate = releaseWorkflow.indexOf("      - name: Require complete offline PWA and persistent React pages before publishing");
  const publish = releaseWorkflow.indexOf("      - name: Deploy real React to GitHub Pages");
  assert.ok(gate > 0, "Full offline PWA gate must be mandatory in Pages workflow");
  assert.ok(publish > gate, "PWA gate must execute before actual Pages publication");
  const gateBody = releaseWorkflow.slice(gate, releaseWorkflow.indexOf("      - name: Retain mandatory persistence evidence", gate));
  assert.match(gateBody, /EFHC_PWA_EXPORT_DIR:/);
  assert.ok(gateBody.includes("node site/frontend/tests/parity/pwa-cache-integration.mjs"));
  assert.ok(gateBody.includes("node site/frontend/tests/parity/persistent-pages.mjs"));
  assert.ok(!gateBody.includes("continue-on-error: true"));
  assert.ok(!gateBody.includes("if: ${{ inputs.full_review"));
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
  assert.match(readFileSync(path.join(root,"index.html"),"utf8"), new RegExp(`efhc-build-id" content="${config.build_id}"`));
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
  assert.ok(worker.includes('p.startsWith("/assets/")'), "Worker scope-relative asset detection must remain intact");
  const verify = run("verify_export.py", root);
  assert.equal(verify.status, 0, verify.stderr);
  const again = run("fix_pages_assets.py", root);
  assert.equal(again.status, 0, again.stderr);
  assert.equal(readFileSync(path.join(root, "sw.js"), "utf8"), worker, "same build must not prepend another config");
  assert.equal(readFileSync(path.join(root, "pwa-build.json"),"utf8"),JSON.stringify(config,null,2)+"\n","build manifest must remain deterministic");
  unlinkSync(path.join(root, "admin/users/index.html"));
  const rejected = run("verify_export.py", root);
  assert.notEqual(rejected.status, 0, "missing offline page must block deployment");
});

test("Existing USER data and local settings are retained rather than replaced by revalidation", () => {
  assert.match(read("src/lib/queryClient.ts"), /refetchOnMount: "always"/);
  assert.match(read("src/hooks/useSnapshot.ts"), /refetchOnMount: "always"/);
  assert.match(read("src/queries/usePanels.ts"), /refetchOnMount: "always"/);
  const settings = read("src/lib/settings.ts");
  const app = read("src/pages/_app.tsx");
  assert.match(app, /setSettingsHydrated\(true\)/);
  assert.match(app, /initialLocalSettingsRef/);
  assert.match(settings, /local choice made while the Telegram request was pending/i);
  assert.match(settings, /window\.localStorage\.getItem\(`\$\{KEY\}:\$\{owner\}`\)/);
  const activity = read("src/lib/frontendActivity.ts");
  assert.match(activity, /refetchQueries/);
  const energy = read("src/pages/index.tsx");
  assert.match(energy, /LIVE_TICK_MS = 333/);
  assert.match(energy, /performance\.now\(\)/);
});


test("Cached energy keeps a smooth local D8 display without extrapolating past the nearest panel expiry", async () => {
  const { sourceRuntime } = await import("../helpers/source-runtime.mjs");
  const h = sourceRuntime();
  const projection = h.load("lib/energyProjection.ts");
  assert.equal(projection.energyDisplayProjectionWindowMs("2026-11-07T12:00:00Z", "2026-11-07T12:00:45Z"), 45000);
  assert.equal(projection.energyDisplayProjectionWindowMs("2026-11-07T12:00:00Z", "2026-11-07T11:59:59Z"), 0);
  assert.equal(projection.energyDisplayProjectionWindowMs("invalid", "2026-11-07T12:00:45Z"), 0);
  assert.equal(projection.energyDisplayProjectionWindowMs("2026-11-07T12:00:00Z", null), Infinity);
  assert.ok(read("src/pages/index.tsx").includes("Math.min(projectUntilMs"), "Local projection must respect the expiry bound");
});

test("A newer local language/theme choice beats a pending older Telegram cloud response", async () => {
  const { sourceRuntime } = await import("../helpers/source-runtime.mjs");
  const owner = "0000000088";
  let releaseCloud;
  const cloudResponse = new Promise((resolve) => { releaseCloud = resolve; });
  const runtime = sourceRuntime({ overrides: {
    "./userDataCache": { currentUserDataOwner: () => owner },
    "./telegram": {
      telegramCloudStorageGet: () => cloudResponse,
      telegramCloudStorageSet: async () => undefined,
    },
  } });
  const settings = runtime.load("lib/settings.ts");
  const pending = settings.loadSettingsAsync();
  settings.saveSettings({ ...settings.resetSettings(), lang: "ru", color_theme_id: "CT-03" });
  releaseCloud(JSON.stringify({ ...settings.resetSettings(), lang: "en", color_theme_id: "CT-01" }));
  const selected = await pending;
  assert.equal(selected.lang, "ru");
  assert.equal(selected.color_theme_id, "CT-03");
  assert.equal(settings.loadSettings().color_theme_id, "CT-03");
});

test("A missing locale or theme asset aborts the full PWA install instead of reporting a ready offline shell", async () => {
  const source = read("public/sw.js");
  const events = new Map();
  const origin = "https://efhc.example";
  const scope = origin + "/efhc/";
  const stored = new Map();
  class RequestStub {
    constructor(value) { this.url = new URL(value, scope).href; }
  }
  const disk = {
    async match(req) { return stored.get(typeof req === "string" ? new URL(req, scope).href : req.url) || undefined; },
    async put(req, response) { stored.set(req.url, response.clone()); },
    async keys() { return [...stored.keys()].map(url => ({url})); },
    async delete(req) { return stored.delete(req.url); },
  };
  const worker = {
    registration: {scope, active:null},
    location: {origin},
    clients: {matchAll:async () => []},
    addEventListener(type, handler) {events.set(type,handler);},
  };
  const config = {
    build_id: "test-incomplete-locale",
    static_export: true,
    precache: ["/efhc/index.html","/efhc/locale/ru.json"],
    cache_limits: {
      static: {max_entries:100,max_age_seconds:2592000,max_bytes:16777216},
      content: {max_entries:100,max_age_seconds:604800,max_bytes:16777216},
    },
  };
  const sandbox = {
    self:worker, URL, Headers, Response, Blob, Request:RequestStub, Date, console,
    EFHC_PWA_BUILD_CONFIG:config,
    caches: {open:async () => disk,match:async req=>disk.match(req),keys:async()=>[],delete:async()=>true},
    fetch:async request => new Response(request.url.endsWith("ru.json") ? "missing" : "html", {
      status:request.url.endsWith("ru.json") ? 404 : 200,
    }),
  };
  vm.runInNewContext(source,sandbox,{filename:"sw.js"});
  let installing;
  events.get("install")({waitUntil(promise){installing=promise;}});
  await assert.rejects(installing,/EFHC_REQUIRED_PRECACHE_FAILED/);
  assert.ok(stored.has(origin+"/efhc/index.html"),"valid page may stage, but worker must fail until locale is present");
});


// A cached installed build must remain usable offline, but never mask a newer
// HTML document when the user reopens the online Pages application.
test("PWA navigation opens the verified installed page without network delay and checks SW update", async () => {
  const source = read("public/sw.js");
  const origin = "https://efhc.example";
  const scope = origin + "/efhc/";
  const cached = new Response("verified installed page", {status: 200});
  let updates = 0, network = 0;
  const sandbox = {
    URL, Response, Request, Headers, Blob, Date, console,
    self: {
      registration: {scope,active:{},update:async()=>{updates++;}},
      location:{origin},navigator:{onLine:true},
      addEventListener:()=>{},clients:{matchAll:async()=>[]},
    },
    EFHC_PWA_BUILD_CONFIG:{
      build_id:"current",static_export:true,precache:["/efhc/panels/index.html"],
      cache_limits:{static:{max_entries:100,max_age_seconds:2592000,max_bytes:10485760},
        content:{max_entries:40,max_age_seconds:604800,max_bytes:5242880}},
    },
    caches:{
      match:async()=>undefined,
      open:async()=>({match:async url=>String(url).endsWith("/panels/index.html")?cached.clone():undefined}),
    },
    fetch:async()=>{network++;throw Error("offline transport");},
  };
  vm.runInNewContext(source+"\nthis.navigateForTest = navigationFallback;", sandbox);
  const holds=[];
  const response=await sandbox.navigateForTest(new Request(scope+"panels/"), {waitUntil:p=>holds.push(p)});
  assert.equal(await response.text(),"verified installed page");
  await Promise.all(holds);
  assert.equal(updates,1,"instant navigation still triggers a background release check");
  assert.equal(network,0,"warm start must not wait for network HTML");
  assert.match(source,/CLIENT_BUILD_READY/);
  assert.match(source,/retireObsoleteBuildsIfSafe/);
});
