import React, {useEffect, useRef} from "react";
import {useQueryClient} from "@tanstack/react-query";
import {appBasePath} from "../lib/appBasePath";
import {useWalletProvider} from "../lib/wallet-provider";

/** Serwist is the only owner of the HTTP cache and service worker lifecycle.
 * The app merely requests browser-native update checks and can defer a React
 * reload while a form, mutation or wallet handoff is active.
 * No custom cache policy, cache status scan, install protocol or GC.
 */
export function PwaRuntimeStatus(props: {
  t: (key: string) => string;
  enabled?: boolean;
  headless?: boolean;
}): React.JSX.Element | null {
  const queryClient = useQueryClient();
  const {modalOpened: walletModalOpened} = useWalletProvider();
  const walletModalRef = useRef(walletModalOpened);
  walletModalRef.current = walletModalOpened;

  useEffect(() => {
    if (props.enabled === false || !("serviceWorker" in navigator)) return;
    const local = ["localhost", "127.0.0.1", "::1"].includes(location.hostname);
    if (location.protocol !== "https:" && !local) return;
    const base = appBasePath();
    const scope = `${base || ""}/`;
    let disposed = false;
    let registration: ServiceWorkerRegistration | null = null;
    let lastActivityAt = Date.now();
    let refreshPending = false;
    let oldController = navigator.serviceWorker.controller;
    let handoffPending = false;
    let checkingActivation = false;
    let lastActivationCheck = 0;

    const activeEditor = () => Boolean(document.querySelector(
      "input:focus,textarea:focus,select:focus,[contenteditable='true']:focus",
    ));
    const safeForMaintenance = () => !disposed &&
      !walletModalRef.current && !handoffPending &&
      queryClient.isMutating() === 0 && !activeEditor();
    // A click requests manual maintenance; it must not trigger the
    // six-second delay reserved for automatic worker activation.
    const safeForUpgrade = () =>
      safeForMaintenance() && Date.now() - lastActivityAt >= 6000;
    const safeToReload = () => safeForUpgrade() && navigator.onLine &&
      document.visibilityState === "visible";
    const onSafetyCheck = (event: MessageEvent) => {
      if (event.data?.type !== "EFHC_PWA_CLIENT_SAFE") return;
      event.ports?.[0]?.postMessage({
        safe:event.data?.purpose === "maintenance"
          ? safeForMaintenance() : safeForUpgrade(),
      });
    };
    const reloadWhenSafe = () => {
      if (!refreshPending || !safeToReload()) return;
      refreshPending = false;
      location.reload();
    };
    const markActivity = () => {lastActivityAt = Date.now();};
    const markBlur = () => {
      if (walletModalRef.current) handoffPending = true;
      markActivity();
    };
    const markFocus = () => {
      handoffPending = false;
      markActivity();
    };
    const checkForUpdate = () => {
      if (disposed || !registration || !navigator.onLine) return;
      // Serwist checks installation and native lifecycle; activation below
      // requires an affirmative idle response from every scoped client.
      void registration.update().catch(() => undefined);
    };
    const activateWhenSafe = () => {
      const waiting = registration?.waiting;
      if (!waiting || !safeToReload() || checkingActivation ||
          Date.now() - lastActivationCheck < 5000) return;
      checkingActivation = true;
      lastActivationCheck = Date.now();
      const channel = new MessageChannel();
      let finished = false;
      const finish = (safe: boolean) => {
        if (finished) return;
        finished = true;
        window.clearTimeout(timeout);
        channel.port1.close();
        checkingActivation = false;
        if (safe && !disposed && registration?.waiting === waiting &&
            safeToReload()) {
          // Serwist owns activation through its native SKIP_WAITING handler.
          waiting.postMessage({type:"SKIP_WAITING"});
        }
      };
      const timeout = window.setTimeout(() => finish(false), 4500);
      channel.port1.onmessage = event => finish(event.data?.safe === true);
      try {
        waiting.postMessage({type:"EFHC_PWA_CHECK_CLIENTS"},[channel.port2]);
      } catch { finish(false); }
    };
    const onControllerChange = () => {
      const controller = navigator.serviceWorker.controller;
      if (oldController && controller && oldController !== controller) {
        refreshPending = true;
        reloadWhenSafe();
      }
      oldController = controller;
    };
    const nativePrefetch = async () => {
      if (disposed || !navigator.onLine) return;
      try {
        const active = navigator.serviceWorker.controller ||
          (await navigator.serviceWorker.ready).active;
        if (!active || disposed) return;
        // The final Pages manifest, not an EFHC runtime queue, enumerates
        // public exported resources. Serwist handles these URLs natively.
        const response = await fetch(`${base}/pwa-build.json`, {cache:"no-store"});
        if (!response.ok) return;
        const manifest = await response.json() as {
          build_id?: unknown; precache_deferred?: unknown;
        };
        // A previously installed tab may still have an older active worker
        // while Pages already serves a successor manifest. Never send the
        // successor URL list into a predecessor's precache controller.
        const documentBuild = document.querySelector<HTMLMetaElement>(
          'meta[name="efhc-build-id"]',
        )?.content;
        if (!documentBuild || manifest.build_id !== documentBuild ||
            registration?.waiting) return;
        if (!Array.isArray(manifest.precache_deferred)) return;
        const urlsToCache = manifest.precache_deferred
          .filter((value): value is string => typeof value === "string")
          .filter(value => value.startsWith(scope) &&
            !/\/(?:api|auth|wallet|connect|tonconnect)(?:\/|$)/i.test(value));
        if (!urlsToCache.length) return;
        active.postMessage({type:"CACHE_URLS",payload:{urlsToCache}});
      } catch {
        // Deferred public downloads are optional and retry upon next visit.
      }
    };

    navigator.serviceWorker.addEventListener("controllerchange", onControllerChange);
    navigator.serviceWorker.addEventListener("message", onSafetyCheck);
    for (const event of ["pointerdown", "keydown", "touchstart"])
      document.addEventListener(event,markActivity,{passive:true});
    window.addEventListener("blur",markBlur);
    window.addEventListener("focus",markFocus);
    const onResume = () => {checkForUpdate(); activateWhenSafe(); reloadWhenSafe();};
    window.addEventListener("pageshow",onResume);
    window.addEventListener("online",onResume);
    document.addEventListener("visibilitychange",onResume);
    const updateInterval = window.setInterval(checkForUpdate,15*60*1000);
    const idleInterval = window.setInterval(() => {
      activateWhenSafe();
      reloadWhenSafe();
    },1000);

    void navigator.serviceWorker.register(`${base}/sw.js`,{
      scope,updateViaCache:"none",
    }).then(result => {
      if (disposed) return;
      registration = result;
      checkForUpdate();
      void nativePrefetch();
    }).catch(error => {
      console.warn("EFHC_PWA_REGISTRATION_FAILED",error);
    });

    return () => {
      disposed = true;
      window.clearInterval(updateInterval);
      window.clearInterval(idleInterval);
      navigator.serviceWorker.removeEventListener("controllerchange",onControllerChange);
      navigator.serviceWorker.removeEventListener("message",onSafetyCheck);
      for (const event of ["pointerdown", "keydown", "touchstart"])
        document.removeEventListener(event,markActivity);
      window.removeEventListener("blur",markBlur);
      window.removeEventListener("focus",markFocus);
      window.removeEventListener("pageshow",onResume);
      window.removeEventListener("online",onResume);
      document.removeEventListener("visibilitychange",onResume);
    };
  }, [props.enabled,queryClient]);

  // No cache overlays or technical popup: Serwist owns update and caching.
  void props.headless;
  void props.t;
  return null;
}
