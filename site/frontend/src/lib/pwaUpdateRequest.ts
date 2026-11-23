import { appBasePath } from "./appBasePath";

const MIN_AUTOMATIC_CHECK_INTERVAL = 20_000;
const REGISTRATION_READY_WAIT = 2_000;

let lastAutomaticCheck = Number.NEGATIVE_INFINITY;
let inFlight: Promise<void> | null = null;
let startedOffline = false;
let trailingWake: ReturnType<typeof setTimeout> | undefined;

function cancelTrailingWake() {
  if (trailingWake !== undefined) clearTimeout(trailingWake);
  trailingWake = undefined;
}

async function readyWithin(
  container: ServiceWorkerContainer,
): Promise<ServiceWorkerRegistration | undefined> {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      container.ready,
      new Promise<undefined>(resolve => {
        timeout = setTimeout(() => resolve(undefined), REGISTRATION_READY_WAIT);
      }),
    ]);
  } finally {
    if (timeout !== undefined) clearTimeout(timeout);
  }
}

/**
 * Discover a successor for the app's existing native service-worker scope.
 * This never controls activation, reload, registration or application data.
 */
export function requestPwaUpdate({ force = false } = {}): Promise<void> {
  if (typeof window === "undefined" || !window.isSecureContext ||
      !navigator.serviceWorker) return Promise.resolve();
  const online = navigator.onLine;
  if (!force && (!online || document.visibilityState !== "visible")) {
    return Promise.resolve();
  }
  if (inFlight) {
    // The online event must not be swallowed by an explicit offline attempt.
    if (!force && online && startedOffline) {
      return inFlight.then(() => requestPwaUpdate());
    }
    return inFlight;
  }
  const elapsed = Date.now() - lastAutomaticCheck;
  if (!force && elapsed >= 0 && elapsed < MIN_AUTOMATIC_CHECK_INTERVAL) {
    // Do not lose a genuine return immediately following an earlier check.
    // Multiple signals share one bounded trailing update, still foreground-only.
    if (trailingWake === undefined) {
      trailingWake = setTimeout(() => {
        trailingWake = undefined;
        void requestPwaUpdate();
      }, MIN_AUTOMATIC_CHECK_INTERVAL - elapsed);
    }
    return Promise.resolve();
  }

  if (!force) cancelTrailingWake();
  startedOffline = !online;
  if (startedOffline) {
    lastAutomaticCheck = Number.NEGATIVE_INFINITY;
    cancelTrailingWake();
  }
  const operation: Promise<void> = (async () => {
    const container = navigator.serviceWorker;
    const scope = new URL(`${appBasePath() || ""}/`, window.location.origin).href;
    const script = new URL("sw.js", scope).href;
    const known = await container.getRegistration(scope);
    const registration = known ?? (force ? await readyWithin(container) : undefined);
    if (registration?.scope !== scope) return;
    const worker = registration.active ?? registration.waiting ?? registration.installing;
    if (worker?.scriptURL !== script) return;

    if (!force) lastAutomaticCheck = Date.now();
    await registration.update();
  })().catch(() => {
    // The browser can reject when offline, or can retry on the next wake.
    // The result of cache maintenance is reported separately.
  }).finally(() => {
    if (inFlight === operation) {
      inFlight = null;
      startedOffline = false;
    }
  });
  inFlight = operation;
  return operation;
}
