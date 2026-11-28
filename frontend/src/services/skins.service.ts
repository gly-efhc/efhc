import { z } from "zod";

import { apiRequest } from "../lib/api";

const skinItemSchema = z.object({
  skin_id: z.number().int(),
  title: z.string(),
  price_efhc: z.string(),
  asset_path: z.string(),
});

const mySkinSchema = z.object({
  skin_id: z.number().int(),
  purchased_at: z.string(),
});

const skinsMySchema = z.object({
  active_skin_id: z.number().int(),
  owned: z.array(mySkinSchema),
});

const skinSwitcherItemSchema = z.object({
  skin_id: z.number().int(),
  title: z.string(),
  asset_path: z.string(),
  is_unlocked: z.boolean(),
  is_active: z.boolean(),
});

const skinSwitcherStateSchema = z.object({
  current_level: z.number().int(),
  available_skin_ids: z.array(z.number().int()),
  active_skin_id: z.number().int(),
  items: z.array(skinSwitcherItemSchema),
});

export type SkinItem = z.infer<typeof skinItemSchema>;
export type MySkin = z.infer<typeof mySkinSchema>;
export type SkinsMy = z.infer<typeof skinsMySchema>;
export type SkinSwitcherItem = z.infer<typeof skinSwitcherItemSchema>;
export type SkinSwitcherState = z.infer<typeof skinSwitcherStateSchema>;

export async function getSkinsCatalog(): Promise<SkinItem[]> {
  const raw = await apiRequest<unknown>("/skins/catalog", "GET");
  return z.object({ items: z.array(skinItemSchema) }).parse(raw).items;
}

export async function getMySkins(): Promise<SkinsMy> {
  const raw = await apiRequest<unknown>("/skins/my", "GET");
  return skinsMySchema.parse(raw);
}

export async function getSkinSwitcher(): Promise<SkinSwitcherState> {
  const raw = await apiRequest<unknown>("/skins/switcher", "GET");
  return skinSwitcherStateSchema.parse(raw);
}

export async function buySkin(args: {
  skinId: number;
  idempotencyKey: string;
}): Promise<unknown> {
  return await apiRequest<unknown>(
    `/skins/buy/${args.skinId}`,
    "POST",
    { idempotencyKey: args.idempotencyKey },
  );
}

export async function activateSkin(skinId: number): Promise<unknown> {
  return await apiRequest<unknown>(
    `/skins/activate/${skinId}`,
    "POST",
  );
}

export async function activateSwitcherSkin(
  skinId: number,
): Promise<unknown> {
  return await apiRequest<unknown>(
    `/skins/switcher/activate/${skinId}`,
    "POST",
  );
}
