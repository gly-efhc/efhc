export type HttpsUrl = `${string}://${string}`;

export function buildTonConnectManifestUrl(origin: string): HttpsUrl {
  // GitHub Pages cannot serve /api handlers. The isolated preview supplies its
  // own public manifest; production keeps the existing server-authoritative API.
  const pages = process.env.NEXT_PUBLIC_EFHC_PAGES_PREVIEW === "1";
  const firstSegment = pages && typeof window !== "undefined"
    ? window.location.pathname.split("/").filter(Boolean)[0] || ""
    : "";
  const subpath = pages && firstSegment ? `/${encodeURIComponent(firstSegment)}` : "";
  const url = new URL(pages ? `${subpath}/tonconnect-manifest.json` : "/api/tonconnect-manifest", origin);
  return url.toString() as HttpsUrl;
}
