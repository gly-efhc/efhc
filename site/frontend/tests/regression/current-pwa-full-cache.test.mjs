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

test("Pages has one Serwist worker with native update and prefetch APIs", () => {
  const prepare = readFileSync(path.join(pagesTools, "prepare_pages.py"), "utf8");
  const runtime = read("src/components/PwaRuntimeStatus.tsx");
  const worker = readFileSync(path.join(pagesTools,"sw-serwist.js"),"utf8");
  const app = read("src/pages/_app.tsx");
  assert.doesNotMatch(prepare,/public\/sw\.js'\)\.unlink/);
  assert.doesNotMatch(prepare,/public\/manifest\.webmanifest'\)\.unlink/);
  assert.match(runtime,/serviceWorker\.register/);
  assert.match(runtime,/registration\.update\(\)/);
  assert.match(runtime,/type:"CACHE_URLS",payload:\{urlsToCache\}/);
  assert.match(runtime,/queryClient\.isMutating\(\) === 0/);
  assert.match(runtime,/!walletModalRef\.current && !handoffPending/);
  assert.match(runtime,/controllerchange/);
  assert.match(runtime,/document\.addEventListener\("visibilitychange",onResume\)/);
  assert.match(worker,/sw\.addEventListeners\(\)/);
  assert.match(worker,/skipWaiting:false/);
  assert.doesNotMatch(runtime,/ACTIVATE_WHEN_SAFE|GET_ACTIVE_BUILD|CLIENT_BUILD_READY|PREFETCH_PRIORITY/);
  // Only the explicitly requested one-shot public runtime purge may delete
  // a fixed set of Serwist-owned caches. No second runtime cache manager.
  assert.match(worker,/const retireLegacyOnce = async/);
  assert.match(worker,/self\.addEventListener\("activate"/);
  assert.match(worker,/const publicRuntimeCaches = Object\.freeze\(/);
  assert.match(worker,/new CacheExpiration\(name/);
  assert.match(worker,/for \(const name of publicRuntimeCaches\)/);
  assert.match(worker,/caches\.delete\(name\)/);
  assert.match(app,/router\.basePath\}\/manifest\.webmanifest/);
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
  copyFileSync(path.join(publicDir, "manifest.webmanifest"), path.join(root, "manifest.webmanifest"));
  copyFileSync(path.join(publicDir, "offline.html"), path.join(root, "offline.html"));
  copyFileSync(path.join(publicDir, "offline-readonly.html"), path.join(root, "offline-readonly.html"));
  const first = run("fix_pages_assets.py", root);
  assert.equal(first.status, 0, first.stderr);
  const config = JSON.parse(readFileSync(path.join(root, "pwa-build.json"), "utf8"));
  assert.equal(config.static_export, true);
  assert.ok(config.precache_critical.includes("/efhc/index.html"));
  assert.ok(config.precache_critical.includes("/efhc/_next/static/main.js"));
  assert.ok(config.precache_critical.includes("/efhc/panels/index.html"));
  assert.ok(config.precache_critical.includes("/efhc/admin/users/index.html"));
  assert.ok(config.precache_critical.includes("/efhc/browser-shop/index.html"));
  assert.deepEqual(config.precache.filter(url => /\.(?:html|js|css)$/.test(url)
    && !config.precache_critical.includes(url)), [],
    "Every route HTML/JS/CSS must be atomic, not deferred after activation");
  const critical = new Set(config.precache_critical);
  const deferred = new Set(config.precache_deferred);
  assert.equal(critical.size + deferred.size, config.precache.length);
  assert.deepEqual([...critical, ...deferred].sort(), [...config.precache].sort());
  assert.ok([...critical].every(value => !deferred.has(value)));
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
  assert.ok(worker.includes("efhc-serwist-pages"),
    "Final worker must use the Serwist-only public pages strategy");
  assert.ok(worker.includes("EFHC_HTML_GENERATION_MISMATCH"),
    "Bundled Serwist worker must refuse mixed-generation HTML");
  assert.ok(!worker.includes("workbox-precaching"),
    "The final PWA worker must not retain an independent Workbox module");
  assert.ok(!/\bimportScripts\s*\(\s*["']https?:/i.test(worker),
    "The deployed Serwist runtime must be bundled locally without CDN scripts");
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

test("Public offline catalog never overwrites a verified newer response after mount", async () => {
  const { sourceRuntime } = await import("../helpers/source-runtime.mjs");
  const key = /const STORAGE_KEY = "([^"]+)"/.exec(read("src/lib/publicCatalogPersistence.ts"))?.[1];
  assert.ok(key, "Reuse the existing public catalogue storage identity");
  const timestamp = Date.now() - 60_000;
  const old = {items:[{sku:"previous"}]};
  const fresh = {items:[{sku:"current"}]};
  const storage = new Map([[key,JSON.stringify([{
    key:["tasksCatalog"],data:old,updatedAt:timestamp,
  }])]]);
  const runtime = sourceRuntime({storage,session:new Map()});
  const client = runtime.load("lib/queryClient.ts").createEfhcQueryClient();
  const catalog = runtime.load("lib/publicCatalogPersistence.ts");
  const queryKey = ["tasksCatalog"];
  client.setQueryData(queryKey,fresh,{updatedAt:Date.now()});
  catalog.hydratePublicCatalogQueries(client);
  assert.deepEqual(JSON.parse(JSON.stringify(client.getQueryData(queryKey))),fresh);
  // An empty in-memory query still receives the last valid offline catalog.
  client.removeQueries({queryKey});
  catalog.hydratePublicCatalogQueries(client);
  assert.deepEqual(JSON.parse(JSON.stringify(client.getQueryData(queryKey))),old);
  client.clear();
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
  const ownerSwitch = read("src/lib/queryClient.ts");
  assert.match(ownerSwitch, /saveSettings\(resetSettings\(\)\)/);
  assert.doesNotMatch(ownerSwitch, /saveSettings\(loadSettings\(\)\)/);
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

// Native Serwist owns atomic precache, runtime caching, and revision expiry.
// The full export is tested above; real Chromium A→B→C, failed navigation,
// older tabs, and offline routes are tested in tests/parity/pwa-cache-integration.mjs.
test("Serwist installs only the final critical export without a second PWA engine",()=>{
  const worker=readFileSync(path.join(pagesTools,"sw-serwist.js"),"utf8");
  const builder=readFileSync(path.join(pagesTools,"inject_serwist.mjs"),"utf8");
  const config=read("serwist.config.mjs");
  assert.match(worker,/precacheEntries:self\.__SW_MANIFEST/);
  assert.match(worker,/precacheOptions:\{/);
  assert.match(builder,/config\.precache_critical/);
  assert.match(builder,/EFHC_SERWIST_CONFIGURATOR_PASS/);
  assert.match(config,/precachePrerendered:false/);
  assert.doesNotMatch(worker,/from ["']workbox-/);
  assert.doesNotMatch(worker,/\bcache\.put\s*\(/);
});

test("Serwist rejects cross-generation HTML and never restores stale legacy HTML",()=>{
  const worker=readFileSync(path.join(pagesTools,"sw-serwist.js"),"utf8");
  assert.match(worker,/EFHC_HTML_GENERATION_MISMATCH/);
  assert.match(worker,/cachedResponseWillBeUsed/);
  assert.match(worker,/if \(!expected\.has\(pathname\)\)/);
  assert.match(worker,/matchPrecache\(scoped\("offline\.html"\)\)/);
  assert.doesNotMatch(worker,/legacyAssetFallback|legacyHtmlFallback/);
  assert.doesNotMatch(worker,/legacyHtmlFallback/);
});

test("Serwist owns public cache expiry without manual legacy GC or personal storage changes",()=>{
  const worker=readFileSync(path.join(pagesTools,"sw-serwist.js"),"utf8");
  assert.match(worker,/new ExpirationPlugin\(/);
  assert.match(worker,/cleanupOutdatedCaches:true/);
  assert.doesNotMatch(worker,/retireLegacyCachesOnce|readyClients|legacyPublicCaches/);
  // Only the explicitly requested one-shot public runtime purge may delete
  // a fixed set of Serwist-owned caches. No second runtime cache manager.
  assert.match(worker,/const retireLegacyOnce = async/);
  assert.match(worker,/self\.addEventListener\("activate"/);
  assert.match(worker,/const publicRuntimeCaches = Object\.freeze\(/);
  assert.match(worker,/new CacheExpiration\(name/);
  assert.match(worker,/for \(const name of publicRuntimeCaches\)/);
  assert.match(worker,/caches\.delete\(name\)/);
  assert.doesNotMatch(worker,/localStorage\.clear|indexedDB\.deleteDatabase/);
});

test("Android maskable icon preserves the canonical EFHC logo and safe zone", () => {
  const manifest = JSON.parse(read("public/manifest.webmanifest"));
  const regular = manifest.icons.filter((icon) => icon.purpose === "any");
  const maskable = manifest.icons.filter((icon) => icon.purpose === "maskable");
  assert.deepEqual(regular.map((icon) => icon.sizes), ["192x192", "512x512", "any"]);
  assert.deepEqual(regular[2], {
    src: "/assets/efhc/canon/efhc_logo_canon.svg",
    sizes: "any",
    type: "image/svg+xml",
    purpose: "any",
  });
  assert.equal(maskable.length, 1);
  assert.deepEqual(maskable[0], {
    src: "/assets/efhc/efhc_maskable.svg",
    sizes: "any",
    type: "image/svg+xml",
    purpose: "maskable",
  });
  const original = read("public/assets/efhc/canon/efhc_logo_canon.svg");
  const adaptive = read("public/assets/efhc/efhc_maskable.svg");
  const expected = original
    .replace(
      'width="8192" height="8192" viewBox="-163 -163 8518 8518"',
      'width="2048" height="2048" viewBox="-2048 -2048 12288 12288"',
    )
    .replace(
      '  <circle id="yellow-field"',
      '  <rect id="mask-background" x="-2048" y="-2048" width="12288" height="12288" fill="#000000" />\n  <circle id="yellow-field"',
    );
  assert.equal(adaptive, expected.replace(/C(?=\d)/g, "C "), "Android SVG must not alter the original logo geometry");
  assert.doesNotMatch(adaptive, /C\d{2,}/, "SVG path command must not resemble a program identifier");
  assert.ok(4163 < 0.4 * 12288, "EFHC outer ring must fit entirely inside the Android safe zone");
});

test("Profile update checks Serwist without claiming a manual cache purge", () => {
  const settings=read("src/components/profile/ProfileSettingsDialog.tsx");
  assert.match(settings,/registration\.update\(\)/);
  assert.match(settings,/pwa\.maintenance_title/);
  assert.match(settings,/pwa\.native_cache_managed/);
  assert.doesNotMatch(settings,/GET_CACHE_STATUS|CLEAN_STALE_PUBLIC_CACHE/);
  assert.doesNotMatch(settings,/localStorage\.clear\(|caches\.delete\(|indexedDB\.deleteDatabase\(/);
});

test("Android native splash follows the approved EFHC loading surface", () => {
  const manifest = JSON.parse(read("public/manifest.webmanifest"));
  const splash = read("src/components/SplashScreen.tsx");
  const maskable = read("public/assets/efhc/efhc_maskable.svg");
  assert.equal(manifest.background_color, "#000000");
  assert.equal(manifest.theme_color, "#000000");
  assert.match(splash, /bg-black transition-opacity/);
  assert.match(splash, /efhc_logo_canon\.svg/);
  assert.match(splash, /efhc-splash-progress/);
  const documentSource = read("src/pages/_document.tsx");
  const appSource = read("src/pages/_app.tsx");
  const pagesPrep = readFileSync(path.join(pagesTools, "prepare_pages.py"), "utf8");
  assert.doesNotMatch(documentSource, /efhc-bootstrap-splash/,
    "React must be the only startup splash; the PWA gate stays headless");
  assert.doesNotMatch(documentSource, /__EFHC_PWA_GATE__|efhc:pwa-gate-ready/);
  assert.match(appSource, /<SplashScreen\b/);
  assert.match(appSource, /effectiveSplashReady = splashReady \|\| shellTimeoutReady/,
    "The React splash must not be held by a second PWA cache gate");
  assert.match(appSource, /if \(!effectiveSplashReady\)/);
  assert.match(pagesPrep, /src\/components\/SplashScreen\.tsx/,
    "Pages must correct the logo URL of the active React splash");
  assert.match(maskable, /id="mask-background"[^>]+fill="#000000"/);
});

test("Startup has no second cache bootstrap or hidden update gate", () => {
  const doc=read("src/pages/_document.tsx");
  const app=read("src/pages/_app.tsx");
  assert.doesNotMatch(doc,/efhcBootstrapScript|repairOnce|ACTIVATE_WHEN_SAFE/);
  assert.doesNotMatch(doc,/dangerouslySetInnerHTML/);
  assert.doesNotMatch(app,/pwaGateReady|efhc:pwa-gate-ready/);
  assert.match(app,/effectiveSplashReady = splashReady \|\| shellTimeoutReady/);
  assert.match(app,/<SplashScreen\b/);
});

test("Splash logo stays vector-sharp without GPU scale rasterization", () => {
  const splash = read("src/components/SplashScreen.tsx");
  const css = read("src/styles/globals.css");
  const start = css.indexOf("@keyframes efhc-splash-breathe{");
  const end = css.indexOf(".efhc-faq-shell{", start);
  assert.ok(start >= 0 && end > start, "The canonical splash animation is present");
  const animation = css.slice(start, end);
  assert.match(animation, /opacity:0\.94/);
  assert.doesNotMatch(animation, /transform|will-change/);
  assert.match(splash, /efhc_logo_canon\.svg/);
});
