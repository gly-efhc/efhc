/** Browser integration against the real Next static export and actual Chromium SW.
 * This is an ephemeral local Pages test; never publish, touch production,
 * prime financial data or grant Admin privileges.
 */
import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { localPagesBase } from "./pages-base.mjs";

const { chromium } = createRequire(process.env.EFHC_BROWSER_TOOLS || import.meta.url)("playwright-core");
const base = localPagesBase();
const origin = new URL(base).origin;
const root = process.env.EFHC_PWA_EXPORT_DIR;
if (!root || !path.isAbsolute(root)) throw new Error("EFHC_PWA_EXPORT_DIR required");
const artifactDir = process.env.EFHC_PARITY_ARTIFACTS || "/tmp/efhc-persistence-artifacts";
await mkdir(artifactDir, {recursive:true});
const browser = await chromium.launch({
  executablePath: process.env.CHROME_BIN || "/usr/bin/chromium",
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const context = await browser.newContext({
  viewport: {width:390,height:844},
  serviceWorkers: "allow",
});
const page = await context.newPage();
page.setDefaultTimeout(20000);
const results = [];
const errors = [];
page.on("pageerror", error => errors.push(String(error.message)));
await context.route("**/*", route => new URL(route.request().url()).origin === origin
  ? route.continue() : route.abort());
const check = async (name,fn) => {
  await fn();
  results.push({name,status:"PASS"});
  console.log("PWA_INTEGRATION_PASS "+name);
};
try {
  await check("real Chromium installs entire build-scoped offline resource set", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    const config = await (await page.request.get(base+"pwa-build.json")).json();
    assert.equal(config.static_export,true);
    assert.ok(config.precache.length > 40, "full static export assets required");
    await page.evaluate(() => Promise.race([
      navigator.serviceWorker.ready.then(() => true),
      new Promise((_,reject) => setTimeout(() => reject(Error("PWA install timeout")), 95000)),
    ]));
    const info = await page.evaluate(async () => {
      const reg = await navigator.serviceWorker.getRegistration();
      const config = await (await fetch("./pwa-build.json",{cache:"no-store"})).json();
      const cacheName = "efhc-pwa-" + config.build_id + "-static";
      const cache = await caches.open(cacheName);
      const cached = new Set((await cache.keys()).map(req=>new URL(req.url).pathname));
      return {
        registered: Boolean(reg?.active),
        scope: reg?.scope,
        cachedCount: cached.size,
        precacheCount: config.precache.length,
        missing: config.precache.filter(url=>!cached.has(url)),
        cachedPaths: [...cached],
      };
    });
    assert.equal(info.registered,true);
    assert.equal(info.scope,base);
    assert.deepEqual(info.missing,[], "all pages, CSS, JS, languages, themes and resources must be in CacheStorage");
    assert.ok(info.cachedPaths.some(s=>s.includes("/panels/portfolio/index.html")));
    assert.ok(info.cachedPaths.some(s=>s.includes("/admin/index.html")));
    assert.ok(info.cachedPaths.some(s=>s.includes("/browser-shop/index.html")));
    assert.ok(info.cachedPaths.some(s=>s.includes("/_next/static/")));
    assert.ok(info.cachedPaths.every(s=>!s.includes("/api/") && !s.includes("runtime-config.json")), "never cache API/credentials");
    results.push({name:"precache_inventory",status:"INFO",count:info.cachedCount});
  });
  await check("offline deep links use cached React UI instead of offline fallback", async () => {
    await page.reload({waitUntil:"domcontentloaded",timeout:30000});
    await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller),null,{timeout:15000});
    await context.setOffline(true);
    for(const route of ["","panels/portfolio/","faq/","hub/","admin/","browser-shop/"]){
      await page.goto(base+route,{waitUntil:"domcontentloaded",timeout:25000});
      const rendered = await page.evaluate(() => ({
        title:document.title,
        size:document.getElementById("__next")?.innerHTML.length||0,
        text:document.body.innerText.slice(0,2200),
        worker:Boolean(navigator.serviceWorker.controller),
      }));
      assert.equal(rendered.worker,true,"SW controller lost for "+route);
      assert.ok(rendered.size>100,"React shell missing for "+route);
      assert.ok(!rendered.text.includes("EFHC is offline."),"technical fallback replaced route "+route);
      assert.ok(!rendered.text.includes("Application error"),"React error for "+route);
      console.log("PWA_OFFLINE_ROUTE_OK "+(route||"home"));
    }
    await context.setOffline(false);
  });
  await check("PWA update remains waiting during the active session", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    const workerFile = path.join(root,"sw.js");
    const original = await readFile(workerFile,"utf8");
    const originalController = await page.evaluate(() => navigator.serviceWorker.controller?.scriptURL||"");
    assert.ok(originalController.endsWith("/sw.js"),"existing worker must control active session");
    try {
      await writeFile(workerFile,original+"\n// EFHC_TEST_STAGED_UPDATE_"+Date.now()+"\n","utf8");
      await page.evaluate(async () => (await navigator.serviceWorker.getRegistration())?.update());
      await page.waitForFunction(async () => {
        const reg = await navigator.serviceWorker.getRegistration();
        return reg?.waiting?.state === "installed";
      },null,{timeout:45000});
      const state = await page.evaluate(async () => {
        const reg = await navigator.serviceWorker.getRegistration();
        reg?.waiting?.postMessage({type:"SKIP_WAITING"});
        return {waiting:reg?.waiting?.state,controller:navigator.serviceWorker.controller?.scriptURL};
      });
      assert.equal(state.waiting,"installed");
      assert.equal(state.controller,originalController);
      await page.waitForTimeout(500);
      assert.equal(await page.evaluate(async () => Boolean((await navigator.serviceWorker.getRegistration())?.waiting)),true,
        "update activated in the middle of a running session");
    } finally {
      await writeFile(workerFile,original,"utf8");
    }
  });
  assert.deepEqual(errors,[],"unhandled page errors");
} finally {
  await context.setOffline(false).catch(()=>undefined);
  await writeFile(path.join(artifactDir,"pwa-cache-integration.json"),JSON.stringify({
    base,results,errors,build:"ephemeral",physicalPagesDeploy:false,telegramWebView:"NOT_RUN",vps:"NOT_RUN",
  },null,2));
  await context.unrouteAll({behavior:"ignoreErrors"}).catch(()=>undefined);
  await browser.close();
}
