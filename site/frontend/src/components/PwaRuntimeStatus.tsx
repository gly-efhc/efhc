import { useRouter } from "next/router";
import { useQueryClient } from "@tanstack/react-query";
import { appBasePath } from "../lib/appBasePath";
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  RUNTIME_PROGRESS_EVENT,
  type RuntimeProgressDetail,
} from "../lib/runtimeProgress";

type CacheLimit = {
  max_age_seconds: number;
  max_bytes: number;
  max_entries: number;
};

type AdaptiveCachePolicy = {
  content: CacheLimit;
  static: CacheLimit;
  tier: "conservative" | "standard" | "expanded";
};

const SAFE_PREFETCH_ROUTES = new Set([
  "/",
  "/app",
  "/ads",
  "/faq",
  "/hub",
  "/ranks",
  "/referrals",
  "/referrals/my",
  "/referrals/active",
  "/referrals/inactive",
  "/tasks",
  "/web-profile",
]);
const FINANCIAL_ROUTES = new Set([
  "/browser-shop",
  "/exchange",
  "/panels",
  "/panels/portfolio",
  "/withdraw",
]);

async function resolveAdaptiveCachePolicy(): Promise<
  AdaptiveCachePolicy
> {
  const runtimeNavigator = navigator as Navigator & {
    connection?: { saveData?: boolean; effectiveType?: string };
    deviceMemory?: number;
  };
  const memory = Number(runtimeNavigator.deviceMemory || 0);
  const estimate = await navigator.storage?.estimate?.().catch(() => null);
  const quota = Number(estimate?.quota || 0);
  const saveData = Boolean(runtimeNavigator.connection?.saveData);
  const lowQuota = quota > 0 && quota < 200 * 1024 * 1024;
  if (saveData || (memory > 0 && memory <= 2) || lowQuota) {
    return {
      tier: "conservative",
      static: {
        max_entries: 180,
        max_age_seconds: 2_592_000,
        max_bytes: 36 * 1024 * 1024,
      },
      content: {
        max_entries: 90,
        max_age_seconds: 604_800,
        max_bytes: 20 * 1024 * 1024,
      },
    };
  }
  const expanded = memory >= 4 && quota >= 500 * 1024 * 1024;
  if (expanded) {
    return {
      tier: "expanded",
      static: {
        max_entries: 520,
        max_age_seconds: 3_888_000,
        max_bytes: 180 * 1024 * 1024,
      },
      content: {
        max_entries: 300,
        max_age_seconds: 1_209_600,
        max_bytes: 80 * 1024 * 1024,
      },
    };
  }
  return {
    tier: "standard",
    static: {
      max_entries: 320,
      max_age_seconds: 2_592_000,
      max_bytes: 92 * 1024 * 1024,
    },
    content: {
      max_entries: 180,
      max_age_seconds: 604_800,
      max_bytes: 48 * 1024 * 1024,
    },
  };
}

function connectionAllowsPrefetch(): boolean {
  const connection = (
    navigator as Navigator & {
      connection?: { saveData?: boolean; effectiveType?: string };
    }
  ).connection;
  if (connection?.saveData) return false;
  return (
    connection?.effectiveType !== "2g" &&
    connection?.effectiveType !== "slow-2g"
  );
}

function collectCacheableResources(): string[] {
  const urls = new Set<string>();
  for (const entry of performance.getEntriesByType("resource")) {
    if (entry.name.startsWith(window.location.origin)) {
      urls.add(entry.name);
    }
  }
  document.querySelectorAll<HTMLImageElement>("img[src]").forEach(
    (node) => urls.add(new URL(node.src, window.location.origin).href),
  );
  document.querySelectorAll<HTMLLinkElement>("link[href]").forEach(
    (node) => urls.add(new URL(node.href, window.location.origin).href),
  );
  document.querySelectorAll<HTMLScriptElement>("script[src]").forEach(
    (node) => urls.add(new URL(node.src, window.location.origin).href),
  );
  return [...urls];
}

function idle(callback: () => void): () => void {
  const browserWindow = window as Window & {
    requestIdleCallback?: (
      callback: IdleRequestCallback,
      options?: IdleRequestOptions,
    ) => number;
    cancelIdleCallback?: (id: number) => void;
  };
  if (browserWindow.requestIdleCallback) {
    const id = browserWindow.requestIdleCallback(callback, {
      timeout: 2500,
    });
    return () => browserWindow.cancelIdleCallback?.(id);
  }
  const id = globalThis.setTimeout(callback, 900);
  return () => globalThis.clearTimeout(id);
}

function formatMegabytes(bytes: number): string {
  if (!bytes) return "0 MB";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function PwaRuntimeStatus(props: {
  t: (key: string) => string;
  enabled?: boolean;
  /** OWNER cycle 0009: keep PWA side-effects without any technical popup. */
  headless?: boolean;
}) {
  const router = useRouter();
  const { t } = props;
  const enabled = props.enabled !== false;
  // Current-session-only navigation context. Never persist a visit history.
  const recentSessionRoutes = useRef<string[]>([]);
  const queryClient = useQueryClient();
  const [cacheProgress, setCacheProgress] = useState(0);
  const [cacheVisible, setCacheVisible] = useState(false);
  const [cacheEntries, setCacheEntries] = useState(0);
  const [cacheBytes, setCacheBytes] = useState(0);
  const [waiting, setWaiting] = useState<ServiceWorker | null>(null);
  const [updateActivated, setUpdateActivated] = useState(false);
  const [persisted, setPersisted] = useState<boolean | null>(null);
  const [onboardingDone, setOnboardingDone] = useState(false);
  const [visualProof, setVisualProof] = useState(false);
  const [persistBusy, setPersistBusy] = useState(false);
  const statusRef = useRef<HTMLElement | null>(null);
  const [online, setOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );
  const financialRoute = FINANCIAL_ROUTES.has(router.pathname);

  const staticRoutes = useMemo(() => {
    const map: Record<string, string[]> = {
      "/": ["/tasks", "/ranks", "/faq"],
      "/tasks": ["/referrals", "/ranks"],
      "/web-profile": ["/faq", "/hub"],
      "/faq": ["/web-profile", "/hub"],
      "/hub": ["/faq", "/web-profile"],
    };
    return map[router.pathname] || [];
  }, [router.pathname]);

  const nextRoutes = useMemo(() => {
    const values = [
      ...staticRoutes,
      ...recentSessionRoutes.current.slice().reverse(),
    ];
    return [...new Set(values)]
      .filter((route) => SAFE_PREFETCH_ROUTES.has(route))
      .slice(0, 4);
  }, [router.pathname, staticRoutes]);

  // Keep one SW registration for this mounted app. Route learning may change
  // continuously, but must not repeatedly restart an update installation.
  const routerForCacheRef = useRef(router);
  const routesForCacheRef = useRef(nextRoutes);
  routerForCacheRef.current = router;
  routesForCacheRef.current = nextRoutes;

  useEffect(() => {
    if (!SAFE_PREFETCH_ROUTES.has(router.pathname)) return;
    const recent = recentSessionRoutes.current.filter(route => route !== router.pathname);
    recent.push(router.pathname);
    recentSessionRoutes.current = recent.slice(-4);
  }, [router.pathname]);

  const requestPersistence = useCallback(async () => {
    if (!navigator.storage?.persist) return;
    setPersistBusy(true);
    try {
      setPersisted(await navigator.storage.persist());
    } catch {
      setPersisted(false);
    } finally {
      setPersistBusy(false);
    }
  }, []);

  useEffect(() => {
    const markOnline = () => setOnline(true);
    const markOffline = () => setOnline(false);
    window.addEventListener("online", markOnline);
    window.addEventListener("offline", markOffline);
    return () => {
      window.removeEventListener("online", markOnline);
      window.removeEventListener("offline", markOffline);
    };
  }, []);

  useEffect(() => {
    if (!navigator.storage?.persisted) return;
    void navigator.storage.persisted().then(setPersisted).catch(
      () => setPersisted(false),
    );
    const onInstalled = () => void requestPersistence();
    window.addEventListener("appinstalled", onInstalled);
    return () => window.removeEventListener("appinstalled", onInstalled);
  }, [requestPersistence]);

  useEffect(() => {
    const proofWindow = window as Window & {
      __EFHC_PUBLIC_VISUAL_PROOF__?: boolean;
    };
    const localHost = [
      "localhost",
      "127.0.0.1",
      "::1",
    ].includes(window.location.hostname);
    setVisualProof(
      proofWindow.__EFHC_PUBLIC_VISUAL_PROOF__ === true &&
      navigator.webdriver === true &&
      localHost,
    );
  }, []);

  useEffect(() => {
    const onProofUpdate = () => {
      const proofWorker = {
        postMessage: () => setUpdateActivated(true),
      } as unknown as ServiceWorker;
      setWaiting(proofWorker);
    };
    window.addEventListener("efhc-pwa-update-proof", onProofUpdate);
    return () => {
      window.removeEventListener("efhc-pwa-update-proof", onProofUpdate);
    };
  }, []);

  useEffect(() => {
    const onProgress = (event: Event) => {
      const detail = (event as CustomEvent<RuntimeProgressDetail>).detail;
      if (detail.channel !== "cache") return;
      setCacheProgress(detail.value);
      setCacheVisible(!detail.complete);
    };
    window.addEventListener(RUNTIME_PROGRESS_EVENT, onProgress);
    return () => {
      window.removeEventListener(RUNTIME_PROGRESS_EVENT, onProgress);
    };
  }, []);

  useEffect(() => {
    if (!enabled || !("serviceWorker" in navigator)) return;
    const isLocal = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
    if (window.location.protocol !== "https:" && !isLocal) return;
    let disposed = false;
    let cleanupIdle: () => void = () => undefined;
    let trackedRegistration: ServiceWorkerRegistration | null = null;
    let trackedWorker: ServiceWorker | null = null;
    let lastUpdateCheck = 0;
    let lastInteractionAt = Date.now();
    let cleanupReloadTimer: number | null = null;
    let verifyInFlight = false;
    let autoReloadBuildId = "";
    let staleDetectedAt = 0;
    let lastCacheSweepAt = 0;
    const markActivity = () => { lastInteractionAt = Date.now(); };
    const hasActiveEditor = () => Boolean(document.querySelector(
      "input:focus, textarea:focus, select:focus, [contenteditable='true']:focus",
    ));
    const attemptIdleReload = () => {
      if (disposed || !autoReloadBuildId || !navigator.onLine ||
          document.visibilityState === "hidden" ||
          (Date.now() - lastInteractionAt < 6000 &&
            (!staleDetectedAt || Date.now() - staleDetectedAt < 15000)) ||
          queryClient.isMutating() > 0 || hasActiveEditor()) return;
      const key = "efhc:pwa-reload:" + autoReloadBuildId;
      try {
        const attempts = Math.max(0, Number(window.sessionStorage.getItem(key) || 0));
        if (attempts >= 3) {
          console.warn("EFHC_PWA_UPGRADE_STALLED", autoReloadBuildId, attempts);
          window.dispatchEvent(new CustomEvent("efhc:pwa-upgrade-stalled", {
            detail: { buildId: autoReloadBuildId, attempts },
          }));
          autoReloadBuildId = "";
          return;
        }
        const lastAttemptAt = Number(window.sessionStorage.getItem(key + ":at") || 0);
        const retryDelayMs = attempts * 2500;
        if (Date.now() - lastAttemptAt < retryDelayMs) return;
        window.sessionStorage.setItem(key, String(attempts + 1));
        window.sessionStorage.setItem(key + ":at", String(Date.now()));
      } catch { /* Storage is optional; a live reload is still bounded by unload. */ }
      try {
        window.sessionStorage.setItem("efhc:pwa-scroll-restore",
          JSON.stringify({path: window.location.pathname + window.location.search,
            y: window.scrollY, at: Date.now()}));
      } catch { /* The page still upgrades without scroll persistence. */ }
      window.location.reload();
    };
    const verifyLoadedBuild = async () => {
      if (disposed || verifyInFlight || !navigator.serviceWorker.controller) return;
      verifyInFlight = true;
      try {
        const manifest = await fetch(appBasePath() + "/pwa-build.json", {cache: "no-store"})
          .then(response => response.ok ? response.json() : null);
        if (!manifest?.build_id || !Array.isArray(manifest.precache)) return;
        // Never navigate based on a new network manifest while the older
        // controller is still active. The active worker itself must attest
        // to the same fully installed release before an idle upgrade.
        const activeBuildId = await new Promise<string | null>(resolve => {
          const channel = new MessageChannel();
          let settled = false;
          const finish = (value: string | null) => {
            if (settled) return;
            settled = true;
            window.clearTimeout(timeout);
            channel.port1.close();
            resolve(value);
          };
          const timeout = window.setTimeout(() => finish(null), 1600);
          channel.port1.onmessage = event => {
            const value = event.data;
            finish(value?.type === "ACTIVE_BUILD" ? String(value.buildId) : null);
          };
          try {
            navigator.serviceWorker.controller?.postMessage({type: "GET_ACTIVE_BUILD"}, [channel.port2]);
          } catch { finish(null); }
        });
        if (activeBuildId !== manifest.build_id) return;
        const precached = new Set<string>(manifest.precache);
        const assets = Array.from(document.querySelectorAll("script[src], link[rel='stylesheet'][href]"))
          .map(element => element.getAttribute("src") || element.getAttribute("href"))
          .filter((value): value is string => typeof value === "string" && value.length > 0)
          .map(value => new URL(value, window.location.href))
          .filter(url => url.origin === window.location.origin &&
            url.pathname.includes("/_next/static/"))
          .map(url => url.pathname);
        if (!assets.length) return;
        const currentDocumentBuild = document.querySelector<HTMLMetaElement>(
          'meta[name="efhc-build-id"]',
        )?.content;
        if (currentDocumentBuild === manifest.build_id && assets.every(asset => precached.has(asset))) {
          navigator.serviceWorker.controller?.postMessage({
            type: "CLIENT_BUILD_READY", buildId: manifest.build_id, assets,
          });
          // On every verified application load, request an immediate sweep of
          // predecessor PWA generations. Never erase owner-scoped local data.
          if (Date.now() - lastCacheSweepAt >= 30_000) {
            lastCacheSweepAt = Date.now();
            navigator.serviceWorker.controller?.postMessage({type: "GET_CACHE_STATUS"});
          }
          staleDetectedAt = 0;
          const verifiedKey = "efhc:pwa-reload:" + manifest.build_id;
          try {
            window.sessionStorage.removeItem(verifiedKey);
            window.sessionStorage.removeItem(verifiedKey + ":at");
          } catch { /* Storage is optional. */ }
          autoReloadBuildId = "";
        } else if (navigator.onLine) {
          // A new worker cannot replace an already running React bundle.
          // Defer an automatic swap until user interactions and mutations finish.
          autoReloadBuildId = manifest.build_id;
          if (!staleDetectedAt) staleDetectedAt = Date.now();
          attemptIdleReload();
        }
      } catch { /* Keep the last usable offline shell. */ }
      finally { verifyInFlight = false; }
    };
    const onControllerChange = () => { void verifyLoadedBuild(); };
    const activateStagedWorker = (registration: ServiceWorkerRegistration) => {
      const staged = registration.waiting;
      if (!staged) return;
      setWaiting(staged);
      // A new Workbox worker has finished only the critical shell. Never
      // force its activation during a mutation, user editing, wallet handoff,
      // background tab or recent activity. The pre-React cold-start gate can
      // independently activate a safe update under the existing splash.
      const safeIdle =
        navigator.onLine && document.visibilityState === "visible" &&
        queryClient.isMutating() === 0 && !hasActiveEditor() &&
        Date.now() - lastInteractionAt >= 6000 &&
        !(document.activeElement instanceof HTMLInputElement &&
          document.activeElement.type === "password");
      if (!safeIdle) return;
      staged.postMessage({ type: "SKIP_WAITING", efhcSafeToActivate: true });
    };
    const checkForUpdate = () => {
      if (disposed || !trackedRegistration || !navigator.onLine ||
          document.visibilityState === "hidden") return;
      const now = Date.now();
      if (now - lastUpdateCheck < 60_000) return;
      lastUpdateCheck = now;
      void trackedRegistration.update().catch(() => {
        // Preserve the installed offline application on transient network failure.
      }).finally(() => {
        if (!disposed && trackedRegistration) activateStagedWorker(trackedRegistration);
      });
    };
    const onWorkerStateChange = () => {
      const worker = trackedWorker;
      const registration = trackedRegistration;
      if (
        worker?.state === "installed" &&
        registration &&
        navigator.serviceWorker.controller
      ) {
        activateStagedWorker(registration);
      }
    };
    const onUpdateFound = () => {
      const registration = trackedRegistration;
      if (!registration) return;
      trackedWorker?.removeEventListener(
        "statechange",
        onWorkerStateChange,
      );
      trackedWorker = registration.installing;
      trackedWorker?.addEventListener(
        "statechange",
        onWorkerStateChange,
      );
    };
    const onMessage = (event: MessageEvent) => {
      const data = event.data || {};
      if (data.type === "CACHE_PROGRESS") {
        setCacheVisible(true);
        setCacheProgress(Number(data.percent || 0));
        setCacheBytes(Number(data.completedBytes || 0));
      }
      if (data.type === "CACHE_COMPLETE") {
        setCacheProgress(100);
        setCacheEntries(Number(data.completed || 0));
        setCacheBytes(Number(data.completedBytes || 0));
        window.setTimeout(() => setCacheVisible(false), 900);
      }
      if (data.type === "CACHE_RETIREMENT_PENDING") {
        void verifyLoadedBuild();
      }
      if (data.type === "CACHE_STATUS") {
        setCacheEntries(
          Number(data.staticEntries || 0) +
          Number(data.contentEntries || 0),
        );
        setCacheBytes(
          Number(data.staticBytes || 0) +
          Number(data.contentBytes || 0),
        );
      }
      if (data.type === "UPDATE_AVAILABLE") {
        void navigator.serviceWorker.getRegistration().then(
          (registration) => {
            if (registration?.waiting) {
              activateStagedWorker(registration);
            }
          },
        );
      }
      if (data.type === "UPDATE_ACTIVATED") {
        void verifyLoadedBuild();
        setUpdateActivated(true);
        window.setTimeout(() => setUpdateActivated(false), 1800);
      }
    };
    navigator.serviceWorker.addEventListener("message", onMessage);
    navigator.serviceWorker.addEventListener("controllerchange", onControllerChange);
    for (const name of ["pointerdown", "keydown", "touchstart"])
      document.addEventListener(name, markActivity, {passive: true});
    // A returned external wallet window is never treated as idle immediately.
    window.addEventListener("focus", markActivity);
    window.addEventListener("blur", markActivity);
    cleanupReloadTimer = window.setInterval(attemptIdleReload, 1000);
    const periodicUpdateTimer = window.setInterval(() => checkForUpdate(), 60_000);
    // An UPDATE_AVAILABLE message may arrive during install, before the
    // registration exposes its waiting worker. Poll only the installed worker:
    // no incomplete build can be activated this way.
    const waitingActivationTimer = window.setInterval(() => {
      if (!disposed && trackedRegistration?.waiting) activateStagedWorker(trackedRegistration);
    }, 2500);
    const onPageEntered = () => {lastUpdateCheck = 0; checkForUpdate(); void verifyLoadedBuild();};
    const onPageResumed = () => {checkForUpdate(); void verifyLoadedBuild();};
    router.events.on("routeChangeComplete", onPageEntered);
    void navigator.serviceWorker.register(`${appBasePath()}/sw.js`, { scope: `${appBasePath() || ""}/`, updateViaCache: "none" }).then(
      (registration) => {
        if (disposed) return;
        trackedRegistration = registration;
        activateStagedWorker(registration);
        registration.addEventListener("updatefound", onUpdateFound);
        window.addEventListener("pageshow", onPageResumed);
        window.addEventListener("online", onPageResumed);
        document.addEventListener("visibilitychange", onPageResumed);
        checkForUpdate();
        void verifyLoadedBuild();
        cleanupIdle = idle(() => {
          const target =
            navigator.serviceWorker.controller || registration.active;
          void resolveAdaptiveCachePolicy().then((policy) => {
            target?.postMessage({
              policy,
              type: "SET_CACHE_POLICY",
            });
          });
          target?.postMessage({ type: "GET_CACHE_STATUS" });
          if (!connectionAllowsPrefetch()) return;
          void Promise.all(
            routesForCacheRef.current.map((route) => routerForCacheRef.current.prefetch(route)),
          ).finally(() => {
            window.setTimeout(() => {
              target?.postMessage({
                reason: "learned-idle-prefetch",
                type: "CACHE_URLS",
                urls: collectCacheableResources(),
              });
            }, 250);
          });
        });
      },
    ).catch((error: unknown) => {
      // A failed registration must be visible to diagnostics, not silently ignored.
      console.warn("EFHC_PWA_REGISTRATION_FAILED", error);
      window.dispatchEvent(new CustomEvent("efhc:pwa-registration-failed"));
    });
    return () => {
      disposed = true;
      cleanupIdle();
      router.events.off("routeChangeComplete", onPageEntered);
      window.clearInterval(periodicUpdateTimer);
      window.clearInterval(waitingActivationTimer);
      if (cleanupReloadTimer !== null) window.clearInterval(cleanupReloadTimer);
      for (const name of ["pointerdown", "keydown", "touchstart"])
        document.removeEventListener(name, markActivity);
      window.removeEventListener("focus", markActivity);
      window.removeEventListener("blur", markActivity);
      navigator.serviceWorker.removeEventListener("controllerchange", onControllerChange);
      window.removeEventListener("pageshow", onPageResumed);
      window.removeEventListener("online", onPageResumed);
      document.removeEventListener("visibilitychange", onPageResumed);
      trackedRegistration?.removeEventListener(
        "updatefound",
        onUpdateFound,
      );
      trackedWorker?.removeEventListener(
        "statechange",
        onWorkerStateChange,
      );
      trackedRegistration = null;
      trackedWorker = null;
      navigator.serviceWorker.removeEventListener("message", onMessage);
    };
  }, [enabled]);

  useEffect(() => {
    try {
      const key = "efhc:pwa-scroll-restore";
      const value = window.sessionStorage.getItem(key);
      if (!value) return;
      const saved = JSON.parse(value) as {path?:string;y?:number;at?:number};
      window.sessionStorage.removeItem(key);
      if (saved.path !== window.location.pathname + window.location.search ||
          !Number.isFinite(saved.y) ||
          !Number.isFinite(saved.at) ||
          Date.now() - Number(saved.at) > 60_000) return;
      const frame = window.requestAnimationFrame(() => {
        window.scrollTo({top:Math.max(0,Number(saved.y)),behavior:"auto"});
      });
      return () => window.cancelAnimationFrame(frame);
    } catch { /* Ignore inaccessible session storage. */ }
  }, []);

  // A staged update retains old chunks only while legacy pages are open.
  // After a verified shell is loaded, obsolete CacheStorage is retired.
  // A mismatched bundle reloads at idle, never during a React Query mutation.

  useEffect(() => {
    const syncOnboarding = () => {
      try {
        setOnboardingDone(
          window.localStorage.getItem("onboarding_v1_seen") === "1",
        );
      } catch {
        setOnboardingDone(true);
      }
    };
    syncOnboarding();
    window.addEventListener(
      "efhc:onboarding-complete",
      syncOnboarding,
    );
    return () => {
      window.removeEventListener(
        "efhc:onboarding-complete",
        syncOnboarding,
      );
    };
  }, []);

  const applyUpdate = () => {
    waiting?.postMessage({ type: "SKIP_WAITING" });
    setWaiting(null);
  };

  const showPersistence =
    persisted === false &&
    onboardingDone &&
    !router.pathname.startsWith("/admin") &&
    !visualProof;
  const proofLegal =
    typeof window === "undefined"
      ? ""
      : String(
          (window as Window & {
            __EFHC_LEGAL_PROOF_KIND__?: string;
          }).__EFHC_LEGAL_PROOF_KIND__ || "",
        );
  const legalQuery = String(router.query.legal || proofLegal);
  const readOnlyRoute =
    router.pathname === "/faq" ||
    router.pathname === "/hub" ||
    (router.pathname === "/web-profile" &&
      (legalQuery === "privacy" || legalQuery === "terms"));
  const showReadOnlyOffline = !online && readOnlyRoute;
  const floatingVisible = cacheVisible || waiting !== null || updateActivated || showPersistence;
  useEffect(() => {
    const status = statusRef.current;
    if (!floatingVisible || !status) return;
    const root = document.documentElement;
    const reserveSpace = () => {
      root.style.setProperty("--efhc-pwa-floating-height", `${status.getBoundingClientRect().height}px`);
    };
    reserveSpace();
    const observer = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(reserveSpace);
    observer?.observe(status);
    window.addEventListener("resize", reserveSpace, { passive: true });
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", reserveSpace);
      root.style.removeProperty("--efhc-pwa-floating-height");
    };
  }, [floatingVisible]);
  // Technical cache/persistence/update/offline cards are not product UI.
  // Keep registration, navigation learning and safe update effects operational.
  if (props.headless) return null;
  if (
    !cacheVisible &&
    !waiting &&
    !updateActivated &&
    !showPersistence &&
    !showReadOnlyOffline
  ) {
    return null;
  }
  return (
    <aside
      ref={statusRef}
      className="efhc-pwa-runtime-status"
      data-pwa-runtime-status="dynamic-cache-update"
      data-pwa-runtime-layout={
        showReadOnlyOffline &&
        !cacheVisible &&
        !waiting &&
        !updateActivated &&
        !showPersistence
          ? "inline-readonly"
          : "floating"
      }
      aria-live="polite"
    >
      {showReadOnlyOffline ? (
        <div
          className="efhc-pwa-readonly-card"
          data-pwa-offline-mode="public-read-only"
        >
          <strong>{t("pwa.offline_read_only")}</strong>
          <small>{t("pwa.offline_read_only_detail")}</small>
        </div>
      ) : null}
      {cacheVisible ? (
        <div className="efhc-pwa-cache-progress">
          <div>
            <span>{t("pwa.cache_progress")}</span>
            <strong>{cacheProgress}%</strong>
          </div>
          <div className="efhc-pwa-cache-track">
            <span style={{ width: `${cacheProgress}%` }} />
          </div>
          <small>
            {cacheEntries ? `${cacheEntries} · ` : ""}
            {formatMegabytes(cacheBytes)}
          </small>
        </div>
      ) : null}
      {showPersistence ? (
        <div className="efhc-pwa-storage-card">
          <span>{t("pwa.keep_offline")}</span>
          <button
            type="button"
            disabled={persistBusy}
            onClick={() => void requestPersistence()}
          >
            {persistBusy
              ? t("common.loading")
              : t("pwa.keep_offline_action")}
          </button>
        </div>
      ) : null}
      {waiting ? (
        <div className="efhc-pwa-update-card">
          <span>{t("pwa.update_available")}</span>
          {financialRoute ? (
            <small>{t("pwa.update_after_operation")}</small>
          ) : null}
          <button type="button" onClick={applyUpdate}>
            {t("pwa.update_now")}
          </button>
        </div>
      ) : null}
      {updateActivated ? (
        <div className="efhc-pwa-update-applied">
          {t("pwa.update_ready")}
        </div>
      ) : null}
    </aside>
  );
}
