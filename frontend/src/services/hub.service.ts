import { z } from "zod";

import { apiRequest } from "../lib/api";

export const HUB_EFHC_HANDOFF_PATH = "/hub/efhc-handoff" as const;

const hubEfhcHandoffSchema = z.object({
  redirect_url: z.string().url(),
  expires_at: z.string().min(1),
  transport: z.literal("external_url"),
  mode: z.literal("signed_token"),
});

export type HubEfhcHandoff = z.infer<typeof hubEfhcHandoffSchema>;

export async function createHubEfhcHandoff(): Promise<HubEfhcHandoff> {
  const raw = await apiRequest<unknown>(HUB_EFHC_HANDOFF_PATH, "POST");
  return hubEfhcHandoffSchema.parse(raw);
}


export const HUB_PUBLIC_LINKS_PATH = "/hub/links" as const;

const hubPublicLinkSchema = z.object({
  id: z.union([z.string(), z.number()]),
  code: z.string().min(1),
  title: z.string().min(1),
  url: z.string().min(1),
  target_kind: z.string().optional().default("external_url"),
  open_mode: z.string().optional().default("external_browser"),
  sort_order: z.number().optional().default(100),
  is_active: z.boolean().optional().default(true),
});

const hubPublicLinksSchema = z.array(hubPublicLinkSchema);

export type HubPublicLink = z.infer<typeof hubPublicLinkSchema>;

export async function getPublicHubLinks(): Promise<HubPublicLink[]> {
  const raw = await apiRequest<unknown>(HUB_PUBLIC_LINKS_PATH, "GET");
  return hubPublicLinksSchema.parse(raw)
    .filter((item) => item.is_active && item.title.trim() && item.url.trim())
    .sort((a, b) => a.sort_order - b.sort_order || String(a.id).localeCompare(String(b.id)));
}
