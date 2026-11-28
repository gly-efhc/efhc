import type { NextApiRequest, NextApiResponse } from "next";

const PUBLIC_KEYS = ["NEXT_PUBLIC_TWA_RETURN_URL", "NEXT_PUBLIC_TON_RPC_ENDPOINT"] as const;

export default function handler(_req: NextApiRequest, res: NextApiResponse) {
  const config: Record<string, string> = {};
  for (const name of PUBLIC_KEYS) {
    // Computed lookup is runtime-only; Next does not inline these server values.
    const value = (process.env[name] || "").trim();
    if (value) {
      try {
        const url = new URL(value);
        if (url.protocol !== "https:" || url.username || url.password
          || [...url.searchParams.keys()].some((key) => /^(api[_-]?key|key|token|secret|auth)$/i.test(key))) {
          throw new Error("invalid public URL");
        }
      } catch {
        res.status(503).json({ error: "PUBLIC_RUNTIME_URL_INVALID" });
        return;
      }
    }
    config[name] = value;
  }
  res.setHeader("Content-Type", "application/javascript; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  const data = JSON.stringify(config).replace(/</g, "\\u003c");
  res.status(200).send(`window.__EFHC_PUBLIC_CONFIG__=Object.freeze(${data});`);
}
