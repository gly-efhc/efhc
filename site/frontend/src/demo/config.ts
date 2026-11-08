/** Public HTTPS backend origin only; never expose database URLs or credentials. */
export function demoApiOrigin(): string {
  const raw = process.env.NEXT_PUBLIC_EFHC_BACKEND_API_ORIGIN || process.env.NEXT_PUBLIC_EFHC_DEMO_API_ORIGIN || "";
  let url: URL;
  try { url = new URL(raw); } catch { throw new Error("EFHC_BACKEND_API_ORIGIN_MISSING"); }
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password ||
      url.search || url.hash || (url.pathname !== "/" && url.pathname !== "")) {
    throw new Error("EFHC_BACKEND_API_ORIGIN_INVALID");
  }
  return url.origin;
}
