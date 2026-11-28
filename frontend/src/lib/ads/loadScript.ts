const scriptPromises = new Map<string, Promise<void>>();

export function loadProviderScript(
  src: string,
  attributes: Record<string, string> = {},
): Promise<void> {
  const normalized = String(src || "").trim();
  if (!normalized || typeof document === "undefined") {
    return Promise.reject(new Error("SDK_LOAD_FAILED"));
  }
  const attrKey = Object.entries(attributes)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${value}`)
    .join("&");
  const cacheKey = `${normalized}|${attrKey}`;
  const cached = scriptPromises.get(cacheKey);
  if (cached) return cached;

  const promise = new Promise<void>((resolve, reject) => {
    const existing = Array.from(document.querySelectorAll<HTMLScriptElement>(
      "script[data-efhc-provider-src]",
    )).find((item) => item.dataset.efhcProviderSrc === cacheKey);
    if (existing?.dataset.efhcLoaded === "1") {
      resolve();
      return;
    }
    const script = existing || document.createElement("script");
    if (!existing) {
      script.async = true;
      script.src = normalized;
      script.dataset.efhcProviderSrc = cacheKey;
      for (const [name, value] of Object.entries(attributes)) {
        script.setAttribute(name, value);
      }
      document.head.appendChild(script);
    }
    script.addEventListener("load", () => {
      script.dataset.efhcLoaded = "1";
      resolve();
    }, { once: true });
    script.addEventListener("error", () => {
      scriptPromises.delete(cacheKey);
      reject(new Error("SDK_LOAD_FAILED"));
    }, { once: true });
  });
  scriptPromises.set(cacheKey, promise);
  return promise;
}
