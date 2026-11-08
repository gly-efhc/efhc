const PWA_SCOPE = new URL(self.registration.scope).pathname.replace(/\/$/, "");
const scoped = (path) => `${PWA_SCOPE}/${path.replace(/^\//, "")}`;
const BUILD_CONFIG_URL = scoped("pwa-build.json");
const OFFLINE_URL = scoped("offline.html");
const READONLY_OFFLINE_URL = scoped("offline-readonly.html");
function relativePath(path) {
  if (PWA_SCOPE && path !== PWA_SCOPE && !path.startsWith(PWA_SCOPE + "/")) return null;
  return path.slice(PWA_SCOPE.length) || "/";
}
const CACHE_PREFIX = "efhc-pwa-";
const CACHED_AT = "x-efhc-cached-at";
let configPromise = null;
let runtimeCachePolicy = null;
// Ready notifications must come from a rendered client on this exact build.
// Older open tabs retain their prior hashed bundles until they are replaced.
const readyBuildClients = new Set();

async function loadConfig() {
  if (!configPromise) {
    configPromise = typeof EFHC_PWA_BUILD_CONFIG !== "undefined"
      ? Promise.resolve(EFHC_PWA_BUILD_CONFIG)
      : fetch(BUILD_CONFIG_URL, { cache: "no-store" })
      .then((response) => { if (!response.ok) throw Error("PWA config HTTP " + response.status); return response.json(); })
      .catch(async () => (await caches.match(BUILD_CONFIG_URL))?.json() || ({
        build_id: "efhc-fallback",
        precache: [OFFLINE_URL, READONLY_OFFLINE_URL, scoped("manifest.webmanifest")],
        cache_limits: {
          static: {
            max_entries: 240,
            max_age_seconds: 2592000,
            max_bytes: 83886080,
          },
          content: {
            max_entries: 120,
            max_age_seconds: 604800,
            max_bytes: 41943040,
          },
        },
      }));
  }
  return configPromise;
}

function boundedInteger(value, fallback, minimum, maximum) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(maximum, Math.max(minimum, Math.round(parsed)));
}

function normalizeCachePolicy(policy, defaults) {
  const source = policy || {};
  const staticSource = source.static || {};
  const contentSource = source.content || {};
  return {
    tier: ["conservative", "standard", "expanded"].includes(source.tier)
      ? source.tier
      : "standard",
    static: {
      max_entries: boundedInteger(
        staticSource.max_entries,
        defaults.static.max_entries,
        80,
        3000,
      ),
      max_age_seconds: boundedInteger(
        staticSource.max_age_seconds,
        defaults.static.max_age_seconds,
        86_400,
        5_184_000,
      ),
      max_bytes: boundedInteger(
        staticSource.max_bytes,
        defaults.static.max_bytes || 83886080,
        10485760,
        536870912,
      ),
    },
    content: {
      max_entries: boundedInteger(
        contentSource.max_entries,
        defaults.content.max_entries,
        40,
        400,
      ),
      max_age_seconds: boundedInteger(
        contentSource.max_age_seconds,
        defaults.content.max_age_seconds,
        86_400,
        1_209_600,
      ),
      max_bytes: boundedInteger(
        contentSource.max_bytes,
        defaults.content.max_bytes || 41943040,
        5242880,
        268435456,
      ),
    },
  };
}

function cachePolicy(config) {
  const defaults = config.cache_limits || config.limits;
  const policy = runtimeCachePolicy || normalizeCachePolicy(null, defaults);
  if (config.static_export) {
    policy.static.max_entries = Math.max(policy.static.max_entries, defaults.static.max_entries);
    policy.static.max_bytes = Math.max(policy.static.max_bytes, defaults.static.max_bytes);
  }
  return policy;
}

async function cacheNames() {
  const config = await loadConfig();
  return {
    config,
    staticName: `${CACHE_PREFIX}${config.build_id}-static`,
    contentName: `${CACHE_PREFIX}${config.build_id}-content`,
  };
}

function isApiRequest(pathname) {
  const p = relativePath(pathname);
  return p === null || p === "/api" || p.startsWith("/api/");
}

function isProtectedPath(pathname) {
  const p = relativePath(pathname);
  return p === null || isApiRequest(pathname) || p.startsWith("/admin/") || p === "/admin" ||
    p === "/health" || p.startsWith("/meta/") || p === "/openapi.json";
}

function isImmutableAsset(url) {
  const p = relativePath(url.pathname);
  return p !== null && (p.startsWith("/_next/static/") || p.startsWith("/assets/") ||
    p.startsWith("/images/") || p.startsWith("/skins/") ||
    /\.(?:js|css|woff2?|png|jpe?g|webp|avif|svg|ico|mp3)$/.test(p));
}

function isContentAsset(url) {
  const p = relativePath(url.pathname);
  return p !== null && (p.startsWith("/locale/") || p.startsWith("/faq/") ||
    p === "/manifest.webmanifest" || p === "/locale-manifest.json" ||
    url.pathname === BUILD_CONFIG_URL);
}

function isSafeCacheUrl(value, config) {
  try {
    const url = new URL(value, self.location.origin);
    if (url.origin !== self.location.origin || url.search || url.hash || isApiRequest(url.pathname)) return false;
    if (config.static_export && Array.isArray(config.precache) && config.precache.includes(url.pathname)) return true;
    if (isProtectedPath(url.pathname)) return false;
    return isImmutableAsset(url) || isContentAsset(url);
  } catch {
    return false;
  }
}

async function notifyClients(message) {
  const clients = await self.clients.matchAll({
    includeUncontrolled: true,
    type: "window",
  });
  for (const client of clients) client.postMessage(message);
}

async function stampedResponse(response) {
  const headers = new Headers(response.headers);
  headers.delete("content-encoding");
  headers.delete("content-length");
  headers.delete("transfer-encoding");
  headers.set(CACHED_AT, String(Date.now()));
  const body = await response.clone().blob();
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function putSafe(cache, request, response) {
  if (!response || !response.ok) return;
  await cache.put(request, await stampedResponse(response));
}

async function responseBytes(response) {
  const header = Number(response?.headers.get("content-length") || 0);
  if (Number.isFinite(header) && header > 0) return header;
  try {
    return (await response.clone().blob()).size;
  } catch {
    return 0;
  }
}

async function pruneCache(cacheName, limits) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  const now = Date.now();
  const maxAgeMs = Number(limits.max_age_seconds || 0) * 1000;
  const maxEntries = Number(limits.max_entries || 0);
  const maxBytes = Number(limits.max_bytes || 0);
  const config = await loadConfig();
  const pinned = config.static_export && cacheName.endsWith("-static")
    ? new Set(config.precache.map((url) => new URL(url, self.location.origin).href))
    : new Set();
  const entries = [];
  for (const request of keys) {
    const response = await cache.match(request);
    const cachedAt = Number(response?.headers.get(CACHED_AT) || 0);
    if (!pinned.has(request.url) && maxAgeMs && cachedAt && now - cachedAt > maxAgeMs) {
      await cache.delete(request);
      continue;
    }
    entries.push({
      request,
      cachedAt,
      pinned: pinned.has(request.url),
      bytes: response ? await responseBytes(response) : 0,
    });
  }
  entries.sort((left, right) => Number(right.pinned) - Number(left.pinned) || right.cachedAt - left.cachedAt);
  let keptEntries = 0;
  let keptBytes = 0;
  for (const entry of entries) {
    const entryAllowed = !maxEntries || keptEntries < maxEntries;
    const byteAllowed = !maxBytes || keptBytes + entry.bytes <= maxBytes;
    if (!entry.pinned && (!entryAllowed || !byteAllowed)) {
      await cache.delete(entry.request);
      continue;
    }
    keptEntries += 1;
    keptBytes += entry.bytes;
  }
  return { bytes: keptBytes, entries: keptEntries };
}

async function cacheUrls(urls, reason = "runtime") {
  const names = await cacheNames();
  const unique = [...new Set(urls)].filter((url) => isSafeCacheUrl(url, names.config) &&
    (!names.config.static_export || names.config.precache.includes(new URL(url, self.location.origin).pathname)));
  const failures = [];
  const total = unique.length;
  let completed = 0;
  let completedBytes = 0;
  await notifyClients({
    type: "CACHE_PROGRESS",
    reason,
    completed,
    total,
    percent: total ? 0 : 100,
  });
  const cache = await caches.open(names.staticName);
  for (const url of unique) {
    try {
      const request = new Request(url, { credentials: "same-origin" });
      const cached = await cache.match(request);
      if (!cached) {
        const response = await fetch(request);
        if (!response.ok) throw Error("Precache HTTP " + response.status);
        await putSafe(cache, request, response);
        completedBytes += await responseBytes(response);
      } else {
        completedBytes += await responseBytes(cached);
      }
    } catch {
      failures.push(url);
    }
    completed += 1;
    await notifyClients({
      type: "CACHE_PROGRESS",
      reason,
      completed,
      completedBytes,
      total,
      percent: total ? Math.round((completed / total) * 100) : 100,
    });
  }
  await pruneCache(names.staticName, cachePolicy(names.config).static);
  // OWNER: the first install of a full exported frontend is atomic. A missing
  // language, font, image or progress design is just as much an incomplete app
  // as a missing HTML/JS shell. Keep the previous active SW if this fails.
  const incompleteExport = reason === "install" && names.config.static_export &&
    (failures.length > 0 || unique.length !== (names.config.precache || []).length);
  const missingEssentialShell = reason === "install" && !names.config.static_export &&
    failures.some((url) => /\.html$|\/_next\/static\/.*\.(?:js|css)$/.test(url));
  if (incompleteExport || missingEssentialShell) {
    await notifyClients({ type: "CACHE_FAILED", failed: failures.length +
      Math.max(0, (names.config.precache || []).length - unique.length), reason });
    throw Error("EFHC_REQUIRED_PRECACHE_FAILED:" + failures.length);
  }
  await notifyClients({
    type: "CACHE_COMPLETE",
    failed: failures.length,
    complete: failures.length === 0,
    reason,
    completed,
    completedBytes,
    total,
    percent: 100,
  });
}

async function cacheFirst(request) {
  const names = await cacheNames();
  const cache = await caches.open(names.staticName);
  const cached = await cache.match(request);
  if (cached) return cached;
  // Fully staged upgrades may take over while an older page remains mounted.
  // Its content-hashed assets must still be served from the previous build.
  const previous = (await caches.keys()).filter((key) =>
    key.startsWith(CACHE_PREFIX) && key.endsWith("-static") && key !== names.staticName);
  for (const name of previous.reverse()) {
    const retained = await (await caches.open(name)).match(request);
    if (retained) return retained;
  }
  const response = await fetch(request);
  // An old open page may still request previous hashed chunks. Do not put
  // those obsolete files in the verified new build's immutable asset cache.
  if (!names.config.static_export || names.config.precache.includes(new URL(request.url).pathname)) {
    await putSafe(cache, request, response);
    void pruneCache(names.staticName, cachePolicy(names.config).static);
  }
  return response;
}

async function staleWhileRevalidate(request, event) {
  const names = await cacheNames();
  const cache = await caches.open(names.contentName);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then(async (response) => {
      await putSafe(cache, request, response);
      await pruneCache(names.contentName, cachePolicy(names.config).content);
      return response;
    })
    .catch(() => undefined);
  if (cached) { event.waitUntil(network); return cached; }
  return (await network) || Response.error();
}

function isReadOnlyOfflineRoute(url) {
  const path = relativePath(url.pathname);
  if (path === "/faq" || path === "/faq/" || path === "/hub" || path === "/hub/") return true;
  if (path !== "/web-profile" && path !== "/web-profile/") return false;
  const legal = url.searchParams.get("legal");
  return legal === "privacy" || legal === "terms";
}

async function navigationFallback(request, event) {
  const config = await loadConfig();
  const url = new URL(request.url);
  // Instant cached-page start: never wait for HTML transport before displaying
  // a complete installed page. An independent SW update check stages new JS/CSS
  // and HTML in the background. Never patch a build's HTML with another build's
  // hashed asset references; that would break offline startup.
  if (config.static_export && relativePath(url.pathname) !== null) {
    const html = url.pathname.endsWith(".html") ? url.pathname : url.pathname.replace(/\\/$/, "") + "/index.html";
    const { staticName } = await cacheNames();
    const cached = await (await caches.open(staticName)).match(html);
    if (cached) {
      if (event && self.navigator?.onLine !== false) {
        event.waitUntil(self.registration.update().catch(() => undefined));
      }
      return cached;
    }
  }
  // No installed HTML: fetch it (initial setup, previously unvisited page),
  // or fall back to the last confirmed offline route.
  try {
    const response = await fetch(request, { cache: "no-store" });
    if (response.ok || !config.static_export) return response;
  } catch { /* Offline navigation falls back to a complete installed shell. */ }
  if (config.static_export && relativePath(url.pathname) !== null) {
    const html = url.pathname.endsWith(".html") ? url.pathname : url.pathname.replace(/\\/$/, "") + "/index.html";
    const cached = await caches.match(html);
    if (cached) return cached;
  }
  const fallback = isReadOnlyOfflineRoute(url) ? READONLY_OFFLINE_URL : OFFLINE_URL;
  return (await caches.match(fallback)) || new Response("EFHC is offline.", {
    status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

async function retireObsoleteBuildsIfSafe() {
  const {config, staticName, contentName} = await cacheNames();
  const windows = await self.clients.matchAll({type: "window", includeUncontrolled: true});
  if (windows.some(client => !readyBuildClients.has(client.id))) return false;
  const keep = new Set([staticName, contentName]);
  const obsolete = (await caches.keys()).filter(name => name.startsWith(CACHE_PREFIX) && !keep.has(name));
  await Promise.all(obsolete.map(name => caches.delete(name)));
  if (obsolete.length) await notifyClients({type: "CACHE_RETIRED", buildId: config.build_id});
  return true;
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const config = await loadConfig();
      await cacheUrls(config.precache || [], "install");
      if (self.registration.active) {
        await notifyClients({
          type: "UPDATE_AVAILABLE",
          buildId: config.build_id,
        });
      }
      // Installation is atomic: all offline resources are already verified.
      // Skip the waiting phase for both initial and update installations;
      // retain the prior hashed assets for any still-open React page.
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await cacheNames();
      const keys = await caches.keys();
      // Preserve one complete previous build while already-open pages may still
      // request its immutable JS/CSS. Keep storage bounded to two builds.
      const previousStatic = keys.filter((key) =>
        key.startsWith(CACHE_PREFIX) && key.endsWith("-static") && key !== names.staticName);
      const previousBuild = previousStatic.at(-1)?.slice(0, -"-static".length) || null;
      const keep = new Set([names.staticName, names.contentName]);
      if (previousBuild) {
        keep.add(previousBuild + "-static");
        keep.add(previousBuild + "-content");
      }
      await Promise.all(
        keys
          .filter((key) => key.startsWith(CACHE_PREFIX) && !keep.has(key))
          .map((key) => caches.delete(key)),
      );
      await self.clients.claim();
      // If no old documents remain open, obsolete build caches can be removed
      // immediately. Otherwise, wait for every client to confirm its new shell.
      await retireObsoleteBuildsIfSafe();
      await notifyClients({
        type: "UPDATE_ACTIVATED",
        buildId: names.config.build_id,
      });
    })(),
  );
});

self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type === "CLIENT_BUILD_READY") {
    event.waitUntil((async () => {
      const names = await cacheNames();
      const assets = data.assets;
      const source = event.source;
      const validAssets = Array.isArray(assets) && assets.length > 0 &&
        assets.some(path => typeof path === "string" && path.startsWith(scoped("_next/static/"))) &&
        assets.every(path => typeof path === "string" && names.config.precache.includes(path));
      if (!source?.id || !validAssets || data.buildId !== names.config.build_id) return;
      readyBuildClients.add(source.id);
      await retireObsoleteBuildsIfSafe();
    })());
    return;
  }
  if (data.type === "SKIP_WAITING") {
    event.waitUntil(self.skipWaiting());
    return;
  }
  if (data.type === "CACHE_URLS" && Array.isArray(data.urls)) {
    event.waitUntil(cacheUrls(data.urls, data.reason || "runtime"));
    return;
  }
  if (data.type === "SET_CACHE_POLICY") {
    event.waitUntil(
      (async () => {
        const names = await cacheNames();
        runtimeCachePolicy = normalizeCachePolicy(
          data.policy,
          names.config.cache_limits || names.config.limits,
        );
        await Promise.all([
          pruneCache(names.staticName, cachePolicy(names.config).static),
          pruneCache(names.contentName, cachePolicy(names.config).content),
        ]);
        await notifyClients({
          type: "CACHE_POLICY_APPLIED",
          policy: runtimeCachePolicy,
        });
      })(),
    );
    return;
  }
  if (data.type === "GET_CACHE_STATUS") {
    event.waitUntil(
      (async () => {
        const names = await cacheNames();
        const staticCache = await caches.open(names.staticName);
        const contentCache = await caches.open(names.contentName);
        const staticState = await pruneCache(
          names.staticName,
          cachePolicy(names.config).static,
        );
        const contentState = await pruneCache(
          names.contentName,
          cachePolicy(names.config).content,
        );
        let precacheMissing = 0;
        for (const url of names.config.precache || []) {
          if (isSafeCacheUrl(url, names.config) && !(await staticCache.match(url))) precacheMissing++;
        }
        await notifyClients({
          type: "CACHE_STATUS",
          precacheMissing,
          buildId: names.config.build_id,
          staticEntries: (await staticCache.keys()).length,
          contentEntries: (await contentCache.keys()).length,
          staticBytes: staticState.bytes,
          contentBytes: contentState.bytes,
          policy: cachePolicy(names.config),
        });
      })(),
    );
  }
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isApiRequest(url.pathname)) return;
  if (request.mode === "navigate") {
    event.respondWith(navigationFallback(request, event));
    return;
  }
  if (isProtectedPath(url.pathname)) return;
  if (isImmutableAsset(url)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (isContentAsset(url)) {
    event.respondWith(staleWhileRevalidate(request, event));
  }
});
