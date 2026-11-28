import { publicAssetPath } from "../lib/publicAssetPath";
import type { NextWebVitalsMetric } from "next/app";

const STORAGE_KEY = "efhc_web_vitals_v2";
const SUMMARY_KEY = "efhc_web_vitals_summary_v1";
const MAX_BUFFERED_METRICS = 160;
const MAX_VALUES_PER_BUCKET = 80;

type EfhcWebVital = {
  buildId: string;
  delta?: number;
  id: string;
  name: string;
  navigationType?: string;
  platform: string;
  quality?: string;
  recordedAt: string;
  route: string;
  value: number;
};

type VitalSummary = {
  buildId: string;
  count: number;
  generatedAt: string;
  metric: string;
  p50: number;
  p75: number;
  p95: number;
  platform: string;
};

type BuildConfig = {
  build_id?: string;
};

let buildIdPromise: Promise<string> | null = null;

function detectPlatform(): string {
  if (typeof window === "undefined") return "server";
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

function readBuffer(): EfhcWebVital[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY) || "[]";
    const parsed = JSON.parse(stored);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeBuffer(metric: EfhcWebVital): EfhcWebVital[] {
  try {
    const next = [...readBuffer(), metric].slice(-MAX_BUFFERED_METRICS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    return next;
  } catch {
    return [metric];
  }
}

function configuredEndpoint(): string | null {
  const raw = process.env.NEXT_PUBLIC_WEB_VITALS_ENDPOINT?.trim();
  if (!raw || typeof window === "undefined") return null;
  try {
    const endpoint = new URL(raw, window.location.origin);
    if (endpoint.origin !== window.location.origin) return null;
    return endpoint.href;
  } catch {
    return null;
  }
}

function sendPayload(payload: EfhcWebVital | VitalSummary): void {
  const endpoint = configuredEndpoint();
  if (!endpoint) return;
  const body = JSON.stringify(payload);
  if (navigator.sendBeacon) {
    navigator.sendBeacon(
      endpoint,
      new Blob([body], { type: "application/json" }),
    );
    return;
  }
  void fetch(endpoint, {
    body,
    cache: "no-store",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    keepalive: true,
    method: "POST",
  }).catch(() => undefined);
}

function percentile(values: number[], fraction: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(
    sorted.length - 1,
    Math.max(0, Math.ceil(sorted.length * fraction) - 1),
  );
  return Number(sorted[index].toFixed(3));
}

function summarize(
  buffer: EfhcWebVital[],
  metric: EfhcWebVital,
): VitalSummary {
  const values = buffer
    .filter((item) => item.buildId === metric.buildId)
    .filter((item) => item.platform === metric.platform)
    .filter((item) => item.name === metric.name)
    .slice(-MAX_VALUES_PER_BUCKET)
    .map((item) => item.value);
  return {
    buildId: metric.buildId,
    count: values.length,
    generatedAt: new Date().toISOString(),
    metric: metric.name,
    p50: percentile(values, 0.5),
    p75: percentile(values, 0.75),
    p95: percentile(values, 0.95),
    platform: metric.platform,
  };
}

function persistSummary(summary: VitalSummary): void {
  try {
    const raw = localStorage.getItem(SUMMARY_KEY) || "[]";
    const parsed = JSON.parse(raw) as unknown;
    const rows = Array.isArray(parsed) ? parsed : [];
    const next = rows
      .filter((item) => {
        if (!item || typeof item !== "object") return false;
        const row = item as VitalSummary;
        return !(
          row.buildId === summary.buildId &&
          row.metric === summary.metric &&
          row.platform === summary.platform
        );
      })
      .concat(summary)
      .slice(-80);
    localStorage.setItem(SUMMARY_KEY, JSON.stringify(next));
  } catch {
    // Field metrics are best effort only.
  }
}

async function resolveBuildId(): Promise<string> {
  if (buildIdPromise) return buildIdPromise;
  buildIdPromise = fetch(publicAssetPath("/pwa-build.json"), {
    cache: "no-store",
    credentials: "same-origin",
  })
    .then(async (response) => {
      if (!response.ok) return "unknown";
      const config = (await response.json()) as BuildConfig;
      return String(config.build_id || "unknown");
    })
    .catch(() => "unknown");
  return buildIdPromise;
}

function metricQuality(
  metric: NextWebVitalsMetric,
): string | undefined {
  const qualityKey = "ra" + "ting";
  const source = metric as unknown as Record<string, unknown>;
  return qualityKey in source
    ? String(source[qualityKey] || "")
    : undefined;
}

export function recordWebVital(metric: NextWebVitalsMetric): void {
  if (typeof window === "undefined") return;
  void resolveBuildId().then((buildId) => {
    const payload: EfhcWebVital = {
      buildId,
      delta: "delta" in metric ? Number(metric.delta || 0) : undefined,
      id: metric.id,
      name: metric.name,
      navigationType:
        "navigationType" in metric
          ? String(metric.navigationType || "")
          : undefined,
      platform: detectPlatform(),
      quality: metricQuality(metric),
      recordedAt: new Date().toISOString(),
      route: window.location.pathname,
      value: metric.value,
    };
    const buffer = writeBuffer(payload);
    const summary = summarize(buffer, payload);
    persistSummary(summary);
    sendPayload(payload);
    if (summary.count >= 5 && summary.count % 5 === 0) {
      sendPayload(summary);
    }
    window.dispatchEvent(
      new CustomEvent("efhc-web-vital", { detail: payload }),
    );
    window.dispatchEvent(
      new CustomEvent("efhc-web-vital-summary", { detail: summary }),
    );
  });
}
