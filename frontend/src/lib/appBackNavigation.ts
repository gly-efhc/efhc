import {withoutAppBasePath} from "./appBasePath";
import { useEffect, useRef } from "react";
import type { NextRouter } from "next/router";
import { telegramBackButtonShow, getTelegramWebApp } from "./telegram";

const APP_BACK_BASE = "__efhcAppBackBaseV1";
const APP_BACK_GUARD = "__efhcAppBackGuardV1";
const APP_BACK_LAYER = "__efhcAppBackLayerV1";
const APP_BACK_STACK_KEY = "efhc_app_back_stack_v1";
const MAX_STACK_DEPTH = 48;

type AppHistoryState = Record<string, unknown> & {
  [APP_BACK_BASE]?: boolean;
  [APP_BACK_GUARD]?: boolean;
  [APP_BACK_LAYER]?: boolean;
};

type AndroidBridgeWindow = Window & {
  __EFHC_ANDROID_BACK__?: () => void;
  __EFHC_ANDROID_EXIT__?: () => void;
};

function pathWithoutHash(value: string): string {
  const index = value.indexOf("#");
  const route = index >= 0 ? value.slice(0, index) : value;
  const canonical = withoutAppBasePath(route);
  const query = canonical.indexOf("?");
  const pathname = query < 0 ? canonical : canonical.slice(0, query);
  return (pathname.replace(/\/+$/, "") || "/") + (query < 0 ? "" : canonical.slice(query));
}

function readRouteStack(): string[] {
  try {
    const raw = window.sessionStorage.getItem(APP_BACK_STACK_KEY);
    const parsed = JSON.parse(raw || "[]") as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is string => typeof item === "string")
      .map(pathWithoutHash)
      .slice(-MAX_STACK_DEPTH);
  } catch {
    return [];
  }
}

function writeRouteStack(stack: string[]): void {
  try {
    window.sessionStorage.setItem(
      APP_BACK_STACK_KEY,
      JSON.stringify(stack.slice(-MAX_STACK_DEPTH)),
    );
  } catch {
    // Session history is a best-effort navigation aid only.
  }
}

function rememberRoute(value: string): void {
  const route = pathWithoutHash(value);
  const stack = readRouteStack();
  const existing = stack.lastIndexOf(route);
  if (existing >= 0) {
    writeRouteStack(stack.slice(0, existing + 1));
    return;
  }
  writeRouteStack([...stack, route]);
}

function previousRoute(currentValue: string, fallback?: string): string {
  const current = pathWithoutHash(currentValue);
  try {
    const parsed = new URL(current, "https://efhc.local");
    if (parsed.pathname === "/faq") {
      const key = ["item", "subsection", "section"].find((name) => parsed.searchParams.has(name));
      if (key) {
        parsed.searchParams.delete(key);
        return parsed.pathname + (parsed.searchParams.size ? `?${parsed.searchParams}` : "");
      }
    }
    if (parsed.pathname === "/admin/users" && parsed.searchParams.has("section")) {
      parsed.searchParams.delete("section");
      const query = parsed.searchParams.toString();
      return `${parsed.pathname}${query ? `?${query}` : ""}`;
    }
  } catch {
    // Continue with the route stack fallback.
  }
  const stack = readRouteStack();
  const index = stack.lastIndexOf(current);
  if (index > 0) return stack[index - 1];
  if (stack.length > 1) return stack[stack.length - 2];
  if (fallback) return pathWithoutHash(fallback);
  if (current.startsWith("/admin/")) return "/admin";
  if (current.startsWith("/referrals/")) return "/referrals";
  if (current.startsWith("/panels/")) return "/panels";
  if (current.startsWith("/browser-shop/")) return "/browser-shop";
  return "/";
}

function visibleDialog(): Element | undefined {
  return Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"][aria-modal="true"]'))
    .filter((element) => element.getClientRects().length > 0).at(-1);
}

function hasBackLayer(): boolean {
  return Boolean(visibleDialog())
    || document.documentElement.dataset.customizationMode === "editing"
    || Boolean(document.querySelector('[data-interface-customization-mode="editing"]'));
}

function consumeBackLayer(): boolean {
  if (visibleDialog()) {
    document.dispatchEvent(new KeyboardEvent("keydown", {
      key: "Escape", bubbles: true, cancelable: true,
    }));
    return true;
  }
  const request = new Event("efhc:back-request", { cancelable: true });
  document.dispatchEvent(request);
  return request.defaultPrevented;
}

export function navigateHomeWithinApp(router: NextRouter): Promise<boolean> {
  if (typeof window !== "undefined") writeRouteStack(["/"]);
  return router.replace("/", undefined, { scroll: false });
}

export function exitAppHost(router: NextRouter): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(false);
  const telegram = getTelegramWebApp();
  const telegramHost = Boolean(telegram?.initData || telegram?.initDataUnsafe?.user
    || (telegram?.platform && telegram.platform !== "unknown"));
  if (telegramHost && typeof telegram?.close === "function") {
    telegram.close();
    return Promise.resolve(true);
  }
  const nativeApp = (navigator as Navigator & { app?: { exitApp?: () => void } }).app;
  if (typeof nativeApp?.exitApp === "function") {
    nativeApp.exitApp();
    return Promise.resolve(true);
  }
  // Ordinary browser tabs are owned by the browser. At root, let Back return
  // to the previous document instead of rearming a same-URL navigation trap.
  if (window.history.length > 1) {
    window.history.back();
    return Promise.resolve(true);
  }
  return navigateHomeWithinApp(router);
}

export function navigateBackWithinApp(router: NextRouter, fallback?: string): Promise<boolean> {
  if (typeof window === "undefined") return router.replace(fallback || "/");
  if (consumeBackLayer()) return Promise.resolve(true);
  const current = pathWithoutHash(router.asPath || router.pathname);
  if (current === "/") return exitAppHost(router);
  const target = previousRoute(current, fallback);
  if (target === current) return Promise.resolve(false);
  // Consume the logical stack BEFORE navigating. A direct Admin child must
  // not reappear when Back is pressed again on the fallback Admin menu.
  const stack = readRouteStack();
  const index = stack.lastIndexOf(target);
  writeRouteStack(index >= 0 ? stack.slice(0, index + 1) : [target]);
  return router.replace(target, undefined, { scroll: false });
}

// Browser history is a transport, not the authority for in-app navigation.
// Direct-entry child routes keep a same-URL guard until Back reaches root.
// Normal internal navigation uses its existing history entries without adding
// duplicates. Native Android/WebView Back shares the logical route stack. Never push a hash:
// Next.js basePath + hash guard previously produced broken nested /Test-3 paths.
export function useAppBackNavigation(router: NextRouter): void {
  const routerRef = useRef(router);
  routerRef.current = router;

  useEffect(() => {
    if (typeof window === "undefined") return;
    let disposed = false;
    let armingFrame = 0;
    let releasingLayerGuard = false;
    let navigationInFlight = false;
    const bridgeWindow = window as AndroidBridgeWindow;

    const armSameUrlGuard = (): void => {
      if (disposed || navigationInFlight) return;
      const layer = hasBackLayer();
      const current = pathWithoutHash(routerRef.current.asPath || routerRef.current.pathname);
      if (!layer && (readRouteStack().length > 1 || current === "/")) return;
      const url = window.location.pathname + window.location.search + window.location.hash;
      const currentState = (window.history.state || {}) as AppHistoryState;
      if (currentState[APP_BACK_GUARD]) return;
      // Preserve Next.js's original state (including __N / key), so its own
      // router.push can keep managing the real path and Next hydration.
      window.history.replaceState({
        ...currentState, [APP_BACK_BASE]: true, [APP_BACK_GUARD]: false, [APP_BACK_LAYER]: false,
      }, "", url);
      window.history.pushState({
        ...currentState, [APP_BACK_BASE]: false, [APP_BACK_GUARD]: true, [APP_BACK_LAYER]: layer,
      }, "", url);
    };
    const scheduleGuard = (): void => {
      window.cancelAnimationFrame(armingFrame);
      armingFrame = window.requestAnimationFrame(armSameUrlGuard);
    };
    const onRouteChangeStart = () => { navigationInFlight = true; };
    const onRouteChange = (url: string): void => {
      navigationInFlight = false;
      rememberRoute(url);
      scheduleGuard();
    };
    rememberRoute(routerRef.current.asPath || routerRef.current.pathname);
    router.events.on("routeChangeStart", onRouteChangeStart);
    router.events.on("routeChangeComplete", onRouteChange);

    // Native Back should close the topmost modal first, then navigate to the
    // previous EFHC route. All financial actions remain in their own handlers.
    const backInsideApp = (): void => {
      void navigateBackWithinApp(routerRef.current).then(scheduleGuard);
    };

    // Next skips its callback on the first same-URL pop (Safari handling).
    // Keep a fallback for that event, but consume every browser Back only once.
    let browserBackHandled = false;
    let browserPopAllowed = false;
    const handleBrowserBack = (): boolean => {
      if (disposed) return true;
      if (releasingLayerGuard) {
        releasingLayerGuard = false;
        return false;
      }
      // A different real history destination belongs to Next, including
      // Forward. Logical Back is only needed for a same-URL guard or a layer.
      const destination = pathWithoutHash(window.location.pathname + window.location.search);
      if (!hasBackLayer() && destination !== pathWithoutHash(routerRef.current.asPath)) return true;
      if (pathWithoutHash(routerRef.current.asPath) === "/" && !hasBackLayer()) return true;
      backInsideApp();
      return false;
    };
    router.beforePopState(() => {
      const allow = browserPopAllowed || handleBrowserBack();
      browserPopAllowed = false;
      // Listener ordering varies. The fallback must not reinterpret an allowed
      // traversal after Next has already updated its current route.
      browserBackHandled = true;
      window.setTimeout(() => { browserBackHandled = false; }, 0);
      return allow;
    });
    const onPopState = (event: PopStateEvent) => {
      if (browserBackHandled) return;
      if (!handleBrowserBack()) event.stopImmediatePropagation();
      else {
        // Capture and Next's callback belong to one traversal. Do not handle
        // it again if Next already exposes the new asPath by the callback.
        browserPopAllowed = true;
        window.setTimeout(() => { browserPopAllowed = false; }, 0);
      }
    };
    window.addEventListener("popstate", onPopState, true);
    const onNativeBack = (event: Event): void => {
      event.preventDefault?.();
      backInsideApp();
    };
    document.addEventListener("backbutton", onNativeBack);
    const bridgeHandler = (): void => backInsideApp();
    bridgeWindow.__EFHC_ANDROID_BACK__ = bridgeHandler;
    const exitHandler = () => { void exitAppHost(routerRef.current); };
    bridgeWindow.__EFHC_ANDROID_EXIT__ = exitHandler;
    let offTelegramBack = () => {};
    let boundTelegram: unknown;
    const connectTelegramBack = () => {
      const host = getTelegramWebApp();
      if (!host || boundTelegram === host) return;
      offTelegramBack();
      boundTelegram = host;
      offTelegramBack = telegramBackButtonShow(bridgeHandler);
    };
    const telegramScript = document.querySelector('script[src*="telegram.org/js/telegram-web-app.js"]');
    telegramScript?.addEventListener("load", connectTelegramBack);
    connectTelegramBack();
    // A modal/editing layer needs one same-URL history entry even at root,
    // so the Android browser Back action can dismiss it before leaving EFHC.
    // Release only layer-owned entries after an explicit close/save; direct-
    // entry route guards remain available for hierarchical Back.
    const syncBackLayer = () => {
      if (disposed || navigationInFlight) return;
      if (hasBackLayer()) { scheduleGuard(); return; }
      const state = (window.history.state || {}) as AppHistoryState;
      if (state[APP_BACK_GUARD] && state[APP_BACK_LAYER] && !releasingLayerGuard) {
        releasingLayerGuard = true;
        window.history.back();
      }
    };
    const layersObserver = typeof MutationObserver === "undefined"
      ? null : new MutationObserver(syncBackLayer);
    layersObserver?.observe(document.body, {
      childList: true, subtree: true, attributes: true,
      attributeFilter: ["aria-hidden", "open", "hidden", "data-interface-customization-mode"],
    });
    layersObserver?.observe(document.documentElement, {
      attributes: true, attributeFilter: ["data-customization-mode"],
    });
    const onRouteError = () => { navigationInFlight = false; syncBackLayer(); };
    router.events.on("routeChangeError", onRouteError);
    scheduleGuard();

    return () => {
      disposed = true;
      layersObserver?.disconnect();
      offTelegramBack();
      telegramScript?.removeEventListener("load", connectTelegramBack);
      if (bridgeWindow.__EFHC_ANDROID_EXIT__ === exitHandler) delete bridgeWindow.__EFHC_ANDROID_EXIT__;
      window.cancelAnimationFrame(armingFrame);
      router.beforePopState(() => true);
      router.events.off("routeChangeStart", onRouteChangeStart);
      router.events.off("routeChangeComplete", onRouteChange);
      router.events.off("routeChangeError", onRouteError);
      window.removeEventListener("popstate", onPopState, true);
      document.removeEventListener("backbutton", onNativeBack);
      if (bridgeWindow.__EFHC_ANDROID_BACK__ === bridgeHandler) {
        delete bridgeWindow.__EFHC_ANDROID_BACK__;
      }
    };
  }, [router.events]);
}

export const APP_BACK_NAVIGATION_CONTRACT = {
  bridge: "window.__EFHC_ANDROID_BACK__",
  native_event: "backbutton",
  browser_event: "popstate",
  history_guard: "same-url-state",
  root_fallback: "/",
  root_exit: "host-close-or-browser-back",
  storage: "sessionStorage",
  pages_mode: "enabled",
} as const;
