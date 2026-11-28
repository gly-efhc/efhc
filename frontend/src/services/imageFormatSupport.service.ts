import { publicAssetPath } from "../lib/publicAssetPath";
type ImageSupport = {
  avif: boolean;
  buildId: string;
  platform: string;
  recordedAt: string;
  webp: boolean;
};

const STORAGE_KEY = "efhc_image_format_support_v1";
const WEBP_DATA = [
  "data:image/webp;base64,",
  "UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEA",
  "DsD+JaQAA3AAAAAA",
].join("");
const AVIF_DATA = [
  "data:image/avif;base64,",
  "AAAAIGZ0eXBhdmlmAAAAAGF2aWZtaWYxbWlhZk1BMUIA",
  "AAEcbWV0YQAAAAAAAAAoaGRscgAAAAAAAAAAcGljdAAAAAAA",
  "AAAAAGxpYmF2aWYAAAAAAAAAAAA=",
].join("");


function platform(): string {
  const userAgent = navigator.userAgent.toLowerCase();
  const telegram = Boolean(
    (window as typeof window & {
      Telegram?: { WebApp?: unknown };
    }).Telegram?.WebApp,
  );
  if (telegram && userAgent.includes("android")) {
    return "telegram-android";
  }
  if (telegram && /(iphone|ipad|ipod)/.test(userAgent)) {
    return "telegram-ios";
  }
  if (telegram) return "telegram-desktop";
  if (userAgent.includes("android")) return "browser-android";
  if (/(iphone|ipad|ipod)/.test(userAgent)) return "browser-ios";
  return "browser-desktop";
}

function supports(dataUrl: string): Promise<boolean> {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image.width > 0 && image.height > 0);
    image.onerror = () => resolve(false);
    image.src = dataUrl;
  });
}

async function buildId(): Promise<string> {
  try {
    const response = await fetch(publicAssetPath("/pwa-build.json"), {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) return "unknown";
    const value = (await response.json()) as { build_id?: string };
    return String(value.build_id || "unknown");
  } catch {
    return "unknown";
  }
}

export async function recordImageFormatSupport(): Promise<void> {
  if (typeof window === "undefined") return;
  try {
    const [avif, webp, currentBuild] = await Promise.all([
      supports(AVIF_DATA),
      supports(WEBP_DATA),
      buildId(),
    ]);
    const row: ImageSupport = {
      avif,
      buildId: currentBuild,
      platform: platform(),
      recordedAt: new Date().toISOString(),
      webp,
    };
    const raw = localStorage.getItem(STORAGE_KEY) || "[]";
    const parsed = JSON.parse(raw) as unknown;
    const rows = Array.isArray(parsed) ? parsed : [];
    const next = rows
      .filter((item) => {
        if (!item || typeof item !== "object") return false;
        const existing = item as ImageSupport;
        return !(
          existing.buildId === row.buildId &&
          existing.platform === row.platform
        );
      })
      .concat(row)
      .slice(-40);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    window.dispatchEvent(
      new CustomEvent("efhc-image-format-support", { detail: row }),
    );
  } catch {
    // Format support telemetry is local and best effort only.
  }
}
