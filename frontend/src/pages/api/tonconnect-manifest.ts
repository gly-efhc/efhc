import type { NextApiRequest, NextApiResponse } from "next";

function normalizeBase(value: string): string | null {
  const raw = String(value || "").trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== "https:" && url.hostname !== "localhost") {
      return null;
    }
    return url.origin;
  } catch {
    return null;
  }
}

function publicBase(req: NextApiRequest): string {
  const configured = normalizeBase(
    process.env.EFHC_PUBLIC_ORIGIN
      || process.env.NEXT_PUBLIC_EFHC_APP_ORIGIN
      || "",
  );
  if (configured) return configured;
  const protoHeader = req.headers["x-forwarded-proto"];
  const hostHeader =
    req.headers["x-forwarded-host"] || req.headers.host;
  const proto = Array.isArray(protoHeader)
    ? protoHeader[0]
    : protoHeader || "https";
  const host = Array.isArray(hostHeader) ? hostHeader[0] : hostHeader;
  if (!host) return "https://efhc.app";
  return normalizeBase(`${proto}://${host}`) || "https://efhc.app";
}

export default function handler(
  req: NextApiRequest,
  res: NextApiResponse,
) {
  const base = publicBase(req).replace(/\/$/, "");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Cache-Control", "public, max-age=300");
  res.status(200).json({
    url: base,
    name: "EFHC Bot",
    iconUrl: `${base}/icon.png`,
    termsOfUseUrl: `${base}/web-profile?legal=terms`,
    privacyPolicyUrl: `${base}/web-profile?legal=privacy`,
  });
}
