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

    const activeEditor = () => Boolean(document.querySelector(
      "input:focus,textarea:focus,select:focus,[contenteditable='true']:focus",
    ));
    const safeToReload = () => !disposed && navigator.onLine &&
      document.visibilityState === "visible" &&
      !walletModalRef.current && !handoffPending &&
      queryClient.isMutating() === 0 &&
      !activeEditor() && Date.now() - lastActivityAt >= 6000;
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
      // Browser/Serwist controls install -> waiting -> activate. No custom
      // skipWaiting request can interrupt another tab's ongoing operation.
      void registration.update().catch(() => undefined);
    };
    const onControllerChange = () => {
      const controller = navigator.serviceWorker.controller;
      if (oldController && controller && oldController !== controller) {
        refreshPending = true;
        reloadWhenSafe();
      }
      oldController = controller;
    };
    const nativePrefetch = () => {
      const controller = navigator.serviceWorker.controller;
      if (!controller || !navigator.onLine) return;
      const urls = [...document.querySelectorAll<HTMLScriptElement>("script[src]"),
        ...document.querySelectorAll<HTMLLinkElement>("link[rel='stylesheet'][href]")]
        .map(element => element.getAttribute("src") || element.getAttribute("href"))
        .filter((value): value is string => typeof value === "string" && value.length > 0)
        .map(value => new URL(value, location.href))
        .filter(url => url.origin === location.origin &&
          url.pathname.startsWith(scope) &&
          (/\/_next\/static\//.test(url.pathname) || /\.[a-f0-9]{16}\.css$/i.test(url.pathname)))
        .map(url => url.href);
      if (!urls.length) return;
      // Standard Serwist CACHE_URLS payload, handled by Serwist.handleCache.
      controller.postMessage({type:"CACHE_URLS",payload:{urlsToCache:[...new Set(urls)]}});
    };

    navigator.serviceWorker.addEventListener("controllerchange", onControllerChange);
    for (const event of ["pointerdown", "keydown", "touchstart"])
      document.addEventListener(event,markActivity,{passive:true});
    window.addEventListener("blur",markBlur);
    window.addEventListener("focus",markFocus);
    const onResume = () => {checkForUpdate(); reloadWhenSafe();};
    window.addEventListener("pageshow",onResume);
    window.addEventListener("online",onResume);
    document.addEventListener("visibilitychange",onResume);
    const updateInterval = window.setInterval(checkForUpdate,15*60*1000);
    const idleInterval = window.setInterval(reloadWhenSafe,1000);

    void navigator.serviceWorker.register(`${base}/sw.js`,{
      scope,updateViaCache:"none",
    }).then(result => {
      if (disposed) return;
      registration = result;
      checkForUpdate();
      nativePrefetch();
    }).catch(error => {
      console.warn("EFHC_PWA_REGISTRATION_FAILED",error);
    });

    return () => {
      disposed = true;
      window.clearInterval(updateInterval);
      window.clearInterval(idleInterval);
      navigator.serviceWorker.removeEventListener("controllerchange",onControllerChange);
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
