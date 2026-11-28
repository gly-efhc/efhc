import { z } from "zod";

import { apiRequest } from "../lib/api";
import { dbIdSchema } from "../lib/api/db-id";

export const HUB_SUPPORT_LINKS_PATH = "/hub/support-links" as const;

const supportLinkSchema = z.object({
  id: dbIdSchema,
  title: z.string().min(1),
  subtitle: z.string().nullable().optional(),
  url: z.string().refine((value) => {
    try {
      return ["https:", "tg:", "mailto:", "tel:"].includes(new URL(value).protocol);
    } catch {
      return false;
    }
  }, "Unsupported support URL"),
  open_mode: z.string(),
  icon_key: z.string().nullable().optional(),
});

export type SupportLink = z.infer<typeof supportLinkSchema>;

export async function getSupportLinks(): Promise<SupportLink[]> {
  const raw = await apiRequest<unknown>(HUB_SUPPORT_LINKS_PATH, "GET");
  return z.array(supportLinkSchema).parse(raw);
}
