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
const exportConfig = JSON.parse(await readFile(path.join(root,"pwa-build.json"),"utf8"));
await mkdir(artifactDir, {recursive:true});
const browser = await chromium.launch({
  executablePath: process.env.CHROME_BIN || "/usr/bin/chromium",
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const context = await browser.newContext({
  viewport: {width:390,height:844},
  serviceWorkers: "allow",
});
let page = await context.newPage();
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
  await check("every exported application HTML route remains navigable without transport", async () => {
    const htmlRoutes = exportConfig.precache.filter(url =>
      url.endsWith(".html") && !/\/offline(?:-readonly)?\.html$/.test(url));
    assert.ok(htmlRoutes.length >= 42,"all Next static routes are required, not just six smoke pages");
    await context.setOffline(true);
    try {
      for (const html of htmlRoutes) {
        const destination = html.endsWith("/index.html") ? html.slice(0,-"index.html".length) : html;
        await page.goto(new URL(destination,origin).href,{waitUntil:"domcontentloaded",timeout:25000});
        const view = await page.evaluate(() => ({
          controlled:Boolean(navigator.serviceWorker.controller),
          reactRoot:Boolean(document.querySelector("#__next")),
          bodySize:document.body.innerText.length,
          fallback:document.body.innerText.includes("EFHC is offline."),
        }));
        assert.ok(view.controlled && view.reactRoot && view.bodySize>10 && !view.fallback,
          "offline route shell failed: "+JSON.stringify({destination,view}));
      }
    } finally { await context.setOffline(false); }
    console.log("PWA_ALL_EXPORTED_ROUTES_OK "+htmlRoutes.length);
    results.push({name:"all_exported_routes_inventory",status:"INFO",count:htmlRoutes.length});
  });
  await check("offline reload restores local language, CT theme and audio choices before backend", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    await page.evaluate(() => {
      sessionStorage.setItem("EFHC_USER_SETTINGS_V1",JSON.stringify({
        settings_owner:null,lang:"ru",color_theme_id:"CT-03",global_theme_id:"03",
        theme_mode:"dark",music_enabled:true,sfx_enabled:false,reduce_motion:false,
        interface_settings_version:4,
      }));
    });
    await context.setOffline(true);
    try {
      for (const route of ["","panels/",""]) {
        await page.goto(base+route,{waitUntil:"domcontentloaded",timeout:25000});
        await page.locator('[data-color-theme-id="CT-03"]').first().waitFor({state:"attached",timeout:15000});
        const settings=await page.evaluate(() => JSON.parse(sessionStorage.getItem("EFHC_USER_SETTINGS_V1")||"null"));
        assert.equal(settings?.lang,"ru");
        assert.equal(settings?.color_theme_id,"CT-03");
        assert.equal(settings?.music_enabled,true);
        assert.equal(settings?.sfx_enabled,false);
        if (!route) {
          await page.locator(".efhc-energy-stage_eyebrow").waitFor({state:"visible",timeout:15000});
          const title=(await page.locator(".efhc-energy-stage_eyebrow").innerText()).trim();
          assert.equal(title,"Энергия","visible language must match cached Russian preference");
        }
      }
    } finally { await context.setOffline(false); }
  });
  await check("offline progress indicators stay finite and inside their tracks at 390/1440", async () => {
    await context.setOffline(true);
    try {
      for (const width of [390,1440]) {
        await page.setViewportSize({width,height:900});
        for (const [route,selector] of [
          ["",".efhc-energy-progress-track"],
          ["referrals/",".efhc-energy-progress-track"],
          ["referrals/",".efhc-referral-achievement-track"],
        ]) {
          await page.goto(base+route,{waitUntil:"domcontentloaded",timeout:25000});
          await page.locator(selector).first().waitFor({state:"attached"});
          const data = await page.locator(selector).first().evaluate(track=>{
            const fill = track.firstElementChild;
            const rail = track.getBoundingClientRect();
            const widthCss = fill ? getComputedStyle(fill).width : "";
            const fillRect = fill?.getBoundingClientRect();
            return {rail:rail.width,paint:fillRect?.width ?? 0,widthCss,
              inline:fill?.style?.width ?? "",child:Boolean(fill)};
          });
          assert.equal(data.child,true,route+" "+selector+" has no progress fill");
          assert.ok(Number.isFinite(data.rail) && data.rail>=0);
          assert.ok(Number.isFinite(data.paint) && data.paint>=0 && data.paint<=data.rail+2,
            "progress fill escapes rail "+JSON.stringify({width,route,selector,data}));
          assert.ok(!/(NaN|Infinity|undefined)/i.test(data.inline),
            "invalid progress percentage "+JSON.stringify({width,route,selector,data}));
        }
        const values = await page.locator("[role=progressbar][aria-valuenow]").evaluateAll(nodes=>
          nodes.map(n=>({name:n.getAttribute("aria-label"),value:Number(n.getAttribute("aria-valuenow"))})));
        for (const item of values) assert.ok(Number.isFinite(item.value) && item.value>=0 && item.value<=100,
          "invalid accessibility percentage "+JSON.stringify(item));
      }
    } finally { await context.setOffline(false); }
  });
  await check("PWA update remains waiting during the active session", async () => {
    await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
    const workerFile = path.join(root,"sw.js");
    const original = await readFile(workerFile,"utf8");
    const originalController = await page.evaluate(() => {
      window.__EFHC_OLD_SW_CONTROLLER_TEST__ = navigator.serviceWorker.controller;
      return navigator.serviceWorker.controller?.scriptURL || "";
    });
    assert.ok(originalController.endsWith("/sw.js"),"existing worker must control active session");
    const oldConfig=exportConfig;
    const newBuildId=oldConfig.build_id+"-staged";
    const oldStaticCache="efhc-pwa-"+oldConfig.build_id+"-static";
    const newStaticCache="efhc-pwa-"+newBuildId+"-static";
    const pinned=/^const EFHC_PWA_BUILD_CONFIG = ([^\n]+);\n/.exec(original);
    assert.ok(pinned,"real exported worker must embed an immutable version configuration");
    const nextBuild={...JSON.parse(pinned[1]),build_id:newBuildId};
    const nextWorker="const EFHC_PWA_BUILD_CONFIG = "+JSON.stringify(nextBuild)+";\n"+
      original.slice(pinned[0].length)+"\n// EFHC_TEST_STAGED_VERSION_"+Date.now()+"\n";
    try {
      await writeFile(workerFile,nextWorker,"utf8");
      await page.evaluate(async () => (await navigator.serviceWorker.getRegistration())?.update());
      // Installation revalidates the full precache and is not instantaneous.
      // Poll the actual registry on the Node side; an async waitForFunction
      // expression must not accidentally certify a Promise before it resolves.
      let state = null;
      for (let attempt = 0; attempt < 180; attempt++) {
        state = await page.evaluate(async () => {
          const reg = await navigator.serviceWorker.getRegistration();
          return {
            waiting:reg?.waiting?.state || null,
            active:reg?.active?.state || null,
            installing:reg?.installing?.state || null,
            sameController:navigator.serviceWorker.controller===window.__EFHC_OLD_SW_CONTROLLER_TEST__,
            controller:navigator.serviceWorker.controller?.scriptURL || null,
            scope:reg?.scope || null,
          };
        });
        if (state.waiting === "installed" && state.installing === null) break;
        await page.waitForTimeout(250);
      }
      console.log("PWA_STAGED_UPDATE_STATE",JSON.stringify(state));
      assert.equal(state.sameController,true,"SW changed controller during active session");
      assert.equal(state.controller,originalController);
      assert.equal(state.waiting,"installed","new SW must remain staged until this client closes");
      await page.evaluate(async () => (await navigator.serviceWorker.getRegistration())?.waiting?.postMessage({type:"SKIP_WAITING"}));
      await page.waitForTimeout(500);
      assert.equal(await page.evaluate(async () => Boolean((await navigator.serviceWorker.getRegistration())?.waiting)),true,
        "update activated in the middle of a running session");
      const interim=await page.evaluate(async (names) => {
        const keys=await caches.keys();
        return {old:keys.includes(names.old),staged:keys.includes(names.next)};
      },{old:oldStaticCache,next:newStaticCache});
      assert.equal(interim.old,true,"old app cache must stay available during an active session");
      assert.equal(interim.staged,true,"new version must be completely staged before takeover");

      // App closes: only now may the browser activate the installed worker.
      // Reopening the same browser context preserves realistic PWA cache storage.
      await page.close();
      page=await context.newPage();
      page.on("pageerror",error=>errors.push(String(error.message)));
      await page.goto(base,{waitUntil:"domcontentloaded",timeout:30000});
      await page.waitForFunction(async names => {
        const registration=await navigator.serviceWorker.getRegistration();
        const keys=await caches.keys();
        return registration?.active?.state==="activated" &&
          keys.includes(names.next) && !keys.includes(names.old);
      },{old:oldStaticCache,next:newStaticCache},{timeout:30000});
      const after=await page.evaluate(async names=>({
        keys:await caches.keys(),
        active:(await navigator.serviceWorker.getRegistration())?.active?.state,
        controlled:Boolean(navigator.serviceWorker.controller),
        nextCache:(await caches.open(names.next)).keys().then(keys=>keys.length),
      }),{next:newStaticCache});
      assert.equal(after.active,"activated");
      assert.ok(after.controlled);
      assert.ok((await after.nextCache)>0);
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
