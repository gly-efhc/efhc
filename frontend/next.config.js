const { readFileSync } = require("node:fs");
const { join } = require("node:path");
/** @type {import("next").NextConfig} */
const apiProxyTarget =
  process.env.NEXT_PUBLIC_API_PROXY_TARGET?.trim() || "";

const requestedBuildCpus = Number.parseInt(
  process.env.EFHC_NEXT_BUILD_CPUS || "1",
  10,
);
const buildCpus =
  Number.isFinite(requestedBuildCpus) && requestedBuildCpus > 0
    ? requestedBuildCpus
    : 1;


function readEfhcBuildId() {
  try {
    return readFileSync(
      join(__dirname, ".efhc-build-id"),
      "utf8",
    ).trim();
  } catch {
    return "efhc-development";
  }
}

const nextConfig = {
  generateBuildId: async () => readEfhcBuildId(),
  reactStrictMode: true,
  typescript: {
    // npm run build performs blocking tsc before setting this flag.
    // This avoids a duplicate Next type-check worker on Node 22.
    ignoreBuildErrors:
      process.env.EFHC_NEXT_EXTERNAL_TYPECHECK === "1",
  },
  experimental: {
    // Bound static page collection in constrained operator hosts.
    // One worker is the verified deterministic default.
    // It keeps EFHC MVP production builds repeatable.
    cpus: buildCpus,
  },
  async headers() {
    const noStore = "no-cache, no-store, must-revalidate";
    const manifestCache = [
      "public, max-age=3600",
      "stale-while-revalidate=86400",
    ].join(", ");
    const contentCache = [
      "public, max-age=86400",
      "stale-while-revalidate=604800",
    ].join(", ");
    const assetCache = [
      "public, max-age=604800",
      "stale-while-revalidate=2592000",
    ].join(", ");
    const securityHeaders = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "no-referrer" },
      {
        key: "Permissions-Policy",
        value: "camera=(), microphone=(), geolocation=()",
      },
      {
        key: "Strict-Transport-Security",
        value: "max-age=31536000; includeSubDomains",
      },
      {
        key: "Cross-Origin-Opener-Policy",
        value: "same-origin-allow-popups",
      },
      {
        key: "Content-Security-Policy",
        value: [
          "default-src 'self'",
          "base-uri 'self'",
          "object-src 'none'",
          "frame-ancestors 'self' " +
            "https://web.telegram.org " +
            "https://*.telegram.org",
          "form-action 'self'",
          "img-src 'self' data: blob: https:",
          "font-src 'self' data:",
          "style-src 'self' 'unsafe-inline'",
          "script-src 'self' 'unsafe-inline' 'unsafe-eval' " +
            "https://telegram.org",
          "connect-src 'self' https: wss:",
          "frame-src 'self' https:",
          "upgrade-insecure-requests",
        ].join("; "),
      },
    ];
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: noStore },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
      {
        source: "/manifest.webmanifest",
        headers: [
          { key: "Cache-Control", value: manifestCache },
        ],
      },
      {
        source: "/locale/:path*",
        headers: [
          { key: "Cache-Control", value: contentCache },
        ],
      },
      {
        source: "/faq/:path*",
        headers: [
          { key: "Cache-Control", value: contentCache },
        ],
      },
      {
        source: "/pwa-build.json",
        headers: [
          { key: "Cache-Control", value: noStore },
        ],
      },
      {
        source: "/assets/:path*",
        headers: [
          { key: "Cache-Control", value: assetCache },
        ],
      },
      {
        source: "/tonconnect-manifest.json",
        headers: [
          {
            key: "Access-Control-Allow-Origin",
            value: "*",
          },
        ],
      },
    ];
  },
  async rewrites() {
    // Server-generated bootstrap asset, available before React/query startup.
    // It remains local to Next even when application API traffic is proxied.
    const publicAssets = [{
      source: "/public-runtime-config.js",
      destination: "/api/public-runtime-config",
    }];
    if (!apiProxyTarget) return publicAssets;
    return [
      ...publicAssets,
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${apiProxyTarget}/health`,
      },
      {
        source: "/meta/:path*",
        destination: `${apiProxyTarget}/meta/:path*`,
      },
      {
        source: "/openapi.json",
        destination: `${apiProxyTarget}/openapi.json`,
      },
      {
        source: "/docs/:path*",
        destination: `${apiProxyTarget}/docs/:path*`,
      },
      {
        source: "/redoc",
        destination: `${apiProxyTarget}/redoc`,
      },
    ];
  },
};

module.exports = nextConfig;
