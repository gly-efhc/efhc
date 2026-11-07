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
  const unique = [...new Set(urls)].filter((url) => isSafeCacheUrl(url, names.config));
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
  if (reason === "install" && failures.some((url) => /\.html$|\/_next\/static\/.*\.(?:js|css)$/.test(url))) {
    await notifyClients({ type: "CACHE_FAILED", failed: failures.length, reason });
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
  const response = await fetch(request);
  await putSafe(cache, request, response);
  void pruneCache(names.staticName, cachePolicy(names.config).static);
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

async function navigationFallback(request) {
  const config = await loadConfig();
  const url = new URL(request.url);
  if (config.static_export && relativePath(url.pathname) !== null) {
    // The Pages Router exports trailingSlash routes as immutable HTML shells.
    const html = url.pathname.endsWith(".html") ? url.pathname : url.pathname.replace(/\/$/, "") + "/index.html";
    const cached = await caches.match(html);
    if (cached) return cached;
  }
  try {
    const response = await fetch(request);
    if (response.ok || !config.static_export) return response;
  } catch { /* Use the existing app route first, fallback only if absent. */ }
  const fallback = isReadOnlyOfflineRoute(url) ? READONLY_OFFLINE_URL : OFFLINE_URL;
  return (await caches.match(fallback)) || new Response("EFHC is offline.", {
    status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
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
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await cacheNames();
      const keep = new Set([names.staticName, names.contentName]);
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => key.startsWith(CACHE_PREFIX) && !keep.has(key))
          .map((key) => caches.delete(key)),
      );
      await self.clients.claim();
      await notifyClients({
        type: "UPDATE_ACTIVATED",
        buildId: names.config.build_id,
      });
    })(),
  );
});

self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type === "SKIP_WAITING") return; // New version takes over on next open.
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
    event.respondWith(navigationFallback(request));
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
