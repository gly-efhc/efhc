/* EFHC Workbox source: injectManifest builds the only deployed /efhc/sw.js.
   Configuration and Workbox runtime directory are inserted after final Pages export.
   This source never registers a second service worker and never caches auth/finance. */
const EFHC_PWA_BUILD_CONFIG = __EFHC_BUILD_CONFIG__;
const APP_BASE = __EFHC_BASE_PATH__;
// All Workbox modules are bundled locally into the same deployed sw.js.
// The runtime has no importScripts/CDN dependency when offline.
import * as precaching from "workbox-precaching";
import * as routing from "workbox-routing";
import * as strategies from "workbox-strategies";
import * as expiration from "workbox-expiration";
const wb = {precaching,routing,strategies,expiration};
const config = EFHC_PWA_BUILD_CONFIG;
const precacheList = self.__WB_MANIFEST;
const expected = new Set(config.precache);
const deferred = new Set(config.precache_deferred || []);
const essential = new Set(config.precache_critical || []);
const ownPrefix = "efhc-pwa-";
const paths = {
  pages: "efhc-public-pages-" + config.build_id,
  assets: "efhc-static-assets-" + config.build_id,
  media: "efhc-public-media",
  locale: "efhc-public-translations",
  preserved: "efhc-legacy-assets",
};
const ownedClients = new Set();
let activePrefetch = null;
let lastCacheReport = 0;
const scoped = value => APP_BASE + "/" + value.replace(/^\/+/, "");
const isScoped = url => url.origin === self.location.origin &&
  (url.pathname === APP_BASE || url.pathname.startsWith(APP_BASE + "/"));
const safePath = value => {
  try {
    const url = new URL(value, self.location.origin);
    return isScoped(url) && expected.has(url.pathname) ? url.pathname : null;
  } catch { return null; }
};
const isHtml = path => path.endsWith(".html");
const isMedia = path => /\.(?:png|jpg|jpeg|svg|ico|webp|avif|mp3)$/i.test(path);
const isLocale = path => /\/(?:locale|faq)\/[^/]+\.json$/i.test(path);
const isFinance = path => /\/(?:api|auth|wallet|connect|tonconnect)(?:\/|$)/i.test(path);
const notify = async data => {
  const clients = await self.clients.matchAll({type:"window",includeUncontrolled:true});
  for (const client of clients) {
    try { if (isScoped(new URL(client.url))) client.postMessage(data); } catch {}
  }
};
const readOnlyOffline = path =>
  /\/(?:faq|hub|web-profile)(?:\/|$)/.test(path);

// Critical files are the *only* atomic install. Other resources never block activation.
wb.precaching.precacheAndRoute(precacheList, {
  directoryIndex: "index.html",
  ignoreURLParametersMatching: [/^utm_/, /^fbclid$/],
});

const verifiedHtml = {
  fetchDidSucceed: async ({request,response}) => {
    if (!response || !response.ok) throw new Error("EFHC_HTML_UNAVAILABLE");
    const body = await response.clone().text();
    if (!body.includes('name="efhc-build-id" content="' + config.build_id + '"')) {
      throw new Error("EFHC_HTML_GENERATION_MISMATCH");
    }
    return response;
  },
};
const pageStrategy = new wb.strategies.NetworkFirst({
  cacheName: paths.pages,
  networkTimeoutSeconds: 2,
  plugins: [verifiedHtml],
});
const staticStrategy = new wb.strategies.CacheFirst({
  cacheName: paths.assets,
});
const mediaStrategy = new wb.strategies.CacheFirst({
  cacheName: paths.media,
  plugins: [new wb.expiration.ExpirationPlugin({
    maxEntries: 120,
    maxAgeSeconds: 30 * 24 * 3600,
    purgeOnQuotaError: true,
  })],
});
const localeStrategy = new wb.strategies.StaleWhileRevalidate({
  cacheName: paths.locale,
  plugins: [new wb.expiration.ExpirationPlugin({
    maxEntries: 48,
    maxAgeSeconds: 14 * 24 * 3600,
    purgeOnQuotaError: true,
  })],
});

const cachedSplash = async () =>
  (await wb.precaching.matchPrecache(scoped("offline.html"))) ||
  new Response("", {status: 503});

const routeAsHtml = url => {
  if (url.pathname.endsWith(".html")) return url.pathname;
  const path = url.pathname.endsWith("/") ? url.pathname : url.pathname + "/";
  return path + "index.html";
};

// A navigation must never mix the active worker's JS with newer HTML on Pages.
// For deferred routes reuse same-generation HTML; if absent offline show only
// the existing EFHC splash, and retry the requested URL after reconnecting.
wb.routing.registerRoute(
  ({request,url}) => request.mode === "navigate" && isScoped(url) &&
    !isFinance(url.pathname),
  async ({event,url}) => {
    const html = routeAsHtml(url);
    if (!expected.has(html)) return cachedSplash();
    const request = new Request(new URL(html, url.origin).href, {
      credentials: "same-origin",
      cache: "no-store",
    });
    try {
      return await pageStrategy.handle({event,request});
    } catch {
      return cachedSplash();
    }
  },
);

wb.routing.registerRoute(
  ({request,url}) => request.method === "GET" &&
    isScoped(url) && isFinance(url.pathname),
  new wb.strategies.NetworkOnly(),
);
wb.routing.registerRoute(
  ({request,url}) => request.method === "GET" && isScoped(url) &&
    url.pathname === scoped("pwa-build.json"),
  new wb.strategies.NetworkOnly(),
);
wb.routing.registerRoute(
  ({request,url}) => request.method === "GET" && isScoped(url) &&
    deferred.has(url.pathname) && !isMedia(url.pathname) &&
    !isLocale(url.pathname) && !isHtml(url.pathname),
  async ({event,request}) => {
    try { return await staticStrategy.handle({event,request}); }
    catch {
      // One-time migration: previously installed hashed bundles are retained.
      const retained = await caches.open(paths.preserved);
      return (await retained.match(request, {ignoreSearch:true})) || Response.error();
    }
  },
);
wb.routing.registerRoute(
  ({request,url}) => request.method === "GET" && isScoped(url) &&
    deferred.has(url.pathname) && isLocale(url.pathname),
  localeStrategy,
);
wb.routing.registerRoute(
  ({request,url}) => request.method === "GET" && isScoped(url) &&
    deferred.has(url.pathname) && isMedia(url.pathname),
  mediaStrategy,
);

async function cacheHas(path) {
  if (essential.has(path)) {
    return Boolean(await wb.precaching.matchPrecache(path));
  }
  const name = isHtml(path) ? paths.pages :
    isMedia(path) ? paths.media :
    isLocale(path) ? paths.locale : paths.assets;
  return Boolean(await (await caches.open(name)).match(path));
}
async function storeDeferred(path) {
  if (!deferred.has(path) || await cacheHas(path)) return true;
  const request = new Request(new URL(path, self.location.origin).href, {
    credentials: "same-origin",cache: "reload",
  });
  const response = await fetch(request);
  if (!response || !response.ok) return false;
  if (isHtml(path)) await verifiedHtml.fetchDidSucceed({request,response});
  const cacheName = isHtml(path) ? paths.pages :
    isMedia(path) ? paths.media :
    isLocale(path) ? paths.locale : paths.assets;
  await (await caches.open(cacheName)).put(request, response.clone());
  return true;
}
async function prefetchDeferred(priority = []) {
  if (activePrefetch) return activePrefetch;
  // The fixed order and requested URLs are only an in-memory session hint.
  // No navigation-history key, per-owner tracking, or persistent queue.
  const high = priority.map(safePath).filter(Boolean);
  const fixed = [
    "panels/portfolio/index.html", "tasks/index.html", "web-profile/index.html",
    "exchange/index.html", "withdraw/index.html", "faq/index.html",
    "hub/index.html", "browser-shop/index.html",
  ].map(scoped);
  const ordered = [...new Set([...high,...fixed,...config.precache_deferred])]
    .filter(path => deferred.has(path) &&
      !/\/audio\/|\.mp3$/i.test(path) &&
      // Language files are cached on actual use by an owner, not in bulk.
      (!isLocale(path) || /\/(?:locale|faq)\/en\.json$/i.test(path)));
  let position = 0, done = 0, failed = 0;
  const run = async () => {
    while (position < ordered.length) {
      const path = ordered[position++];
      try {
        const success = await storeDeferred(path);
        if (!success) failed++;
      } catch { failed++; }
      done++;
      if (done % 8 === 0 || done === ordered.length) {
        await notify({type:"CACHE_PROGRESS",reason:"deferred",completed:done,
          total:ordered.length,percent:Math.round(100*done/ordered.length)});
      }
    }
  };
  activePrefetch = (async () => {
    await Promise.all([run(),run()]);
    await notify({type:"CACHE_COMPLETE",reason:"deferred",completed:done,
      total:ordered.length,failed});
  })();
  try { await activePrefetch; } finally { activePrefetch = null; }
}

async function collectLegacy() {
  const keys = await caches.keys();
  const candidates = keys.filter(key => key.startsWith(ownPrefix) && /-(?:static|content)$/.test(key));
  const proven = [];
  for (const name of candidates) {
    const bucket = await caches.open(name);
    const entries = await bucket.keys();
    if (entries.some(entry => {
      try { return isScoped(new URL(entry.url)); } catch { return false; }
    })) proven.push(name);
  }
  return proven;
}
async function snapshotOldWorkboxAssets() {
  const keys = (await caches.keys()).filter(key =>
    /workbox.*precache|efhc.*wb-precache/.test(key));
  const target = await caches.open(paths.preserved);
  for (const name of keys) {
    const bucket = await caches.open(name);
    for (const request of await bucket.keys()) {
      const path = new URL(request.url).pathname;
      if (!path.startsWith(APP_BASE + "/_next/static/") &&
          !/\.[a-f0-9]{16}\.css$/.test(path)) continue;
      if (await target.match(request)) continue;
      const hit = await bucket.match(request);
      if (hit) {
        try { await target.put(request,hit.clone()); }
        catch { return; }
      }
    }
  }
}
async function retireLegacyWhenSafe() {
  const windows = await self.clients.matchAll({type:"window",includeUncontrolled:true});
  const scopedWindows = windows.filter(client => {
    try { return isScoped(new URL(client.url)); } catch { return false; }
  });
  if (scopedWindows.some(client => !ownedClients.has(client.id))) return;
  const names = await collectLegacy();
  for (const name of names) await caches.delete(name);
}
async function reportCache() {
  const now = Date.now();
  if (now - lastCacheReport < 1000) return;
  lastCacheReport = now;
  const cached = await Promise.all(config.precache.map(cacheHas));
  const missing = cached.filter(value=>!value).length;
  await notify({type:"CACHE_STATUS",buildId:config.build_id,
    precacheMissing:missing,staticEntries:cached.length-missing,
    contentEntries:0,staticBytes:0,contentBytes:0});
}
self.addEventListener("install", event => {
  event.waitUntil((async () => {
    await snapshotOldWorkboxAssets();
    await notify({type:"UPDATE_AVAILABLE",buildId:config.build_id});
  })());
});
self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    await self.clients.claim();
    await notify({type:"UPDATE_ACTIVATED",buildId:config.build_id});
    await retireLegacyWhenSafe();
  })());
  // Client runtime sends session priorities after checking saveData and
  // connection. Activation never starts a bulk download on its own.
});
self.addEventListener("message", event => {
  const data = event.data || {};
  const wait = fn => event.waitUntil(Promise.resolve().then(fn));
  if (data.type === "GET_ACTIVE_BUILD") {
    event.ports?.[0]?.postMessage({type:"ACTIVE_BUILD",buildId:config.build_id});
    return;
  }
  if (data.type === "GET_CACHE_STATUS") {
    wait(async () => {await reportCache();await retireLegacyWhenSafe();});
    return;
  }
  if (data.type === "CLIENT_BUILD_READY") {
    wait(async () => {
      if (data.buildId !== config.build_id || !event.source?.id ||
          !Array.isArray(data.assets) || !data.assets.length ||
          !data.assets.every(url => typeof url === "string" && expected.has(url))) return;
      ownedClients.add(event.source.id);
      await retireLegacyWhenSafe();
    });
    return;
  }
  if (data.type === "SKIP_WAITING") {
    wait(async () => {
      if (data.buildId && data.buildId !== config.build_id) return;
      const windows = await self.clients.matchAll({type:"window",includeUncontrolled:true});
      const scopedWindows = windows.filter(client => {
        try { return isScoped(new URL(client.url)); } catch { return false; }
      });
      // A cold gate or one idle tab cannot authorize dropping bundles used
      // in another open tab. Wait for single-client handoff.
      if (scopedWindows.length > 1) return;
      if (data.efhcSafeToActivate !== true) {
        // One-time migration from the old client that sent SKIP_WAITING
        // unconditionally; retain its old hashed chunks for the idle reload.
        const old = await collectLegacy();
        if (!old.length || scopedWindows.length !== 1) return;
      }
      await self.skipWaiting();
    });
    return;
  }
  if (data.type === "CACHE_URLS" || data.type === "PREFETCH_PRIORITY") {
    wait(async () => prefetchDeferred(Array.isArray(data.urls) ? data.urls : []));
    return;
  }
  if (data.type === "SET_CACHE_POLICY") {
    wait(async () => notify({type:"CACHE_POLICY_APPLIED",policy:data.policy || null}));
  }
});
