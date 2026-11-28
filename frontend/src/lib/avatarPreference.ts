/** Server-owned avatar preferences, separate from UI theme/Energy settings. */
import { z } from "zod";
import { getAvailableSystemProfileAvatars } from "./profileAvatar";

export const AVATAR_ICON_IDS = ["EI-07"] as const;
export const avatarIconSchema = z.enum(AVATAR_ICON_IDS);
export type AvatarIcon = z.infer<typeof avatarIconSchema>;

export function normalizeAvatarHttpsUrl(input: unknown): string | null {
  if (typeof input !== "string") return null;
  const candidate = input.trim();
  if (!candidate || candidate.length > 2048 || candidate.includes("\\") || /\s|[\u0000-\u001f\u007f]/u.test(candidate)) return null;
  try {
    const parsed = new URL(candidate);
    const authority = candidate.match(/^https:\/\/([^/?#]*)/i)?.[1];
    if (!authority || authority.includes("@") || parsed.protocol !== "https:" || !parsed.hostname || parsed.username || parsed.password) return null;
    return candidate;
  } catch { return null; }
}

export const avatarSelectionSchema = z.discriminatedUnion("kind", [
  z.strictObject({ kind: z.literal("provider"), identityId: z.string().regex(/^[1-9][0-9]{0,18}$/) }),
  z.strictObject({ kind: z.literal("url"), url: z.string().max(2048).refine((v) => normalizeAvatarHttpsUrl(v) !== null) }),
  z.strictObject({ kind: z.literal("icon") }),
  z.strictObject({ kind: z.literal("system"), systemId: z.string().regex(/^avatar-(0[1-9]|10)$/) }),
]);
export const avatarPreferenceSchema = z.strictObject({
  schemaVersion: z.literal(1), selection: avatarSelectionSchema, fallbackIcon: avatarIconSchema,
});
export const avatarEnvelopeSchema = z.strictObject({
  preference: avatarPreferenceSchema, revision: z.number().int().nonnegative(), updatedAt: z.string().nullable(),
});
export const avatarSourcesSchema = z.strictObject({
  items: z.array(z.strictObject({
    identityId: z.string(), provider: z.string(), label: z.string(),
    avatarUrl: z.string().nullable(),
    status: z.enum(["available", "no_photo", "unsupported", "reauth_required"]),
    photoRevision: z.string(),
  })),
});
export type AvatarPreference = z.infer<typeof avatarPreferenceSchema>;
export type AvatarEnvelope = z.infer<typeof avatarEnvelopeSchema>;
export type AvatarSource = z.infer<typeof avatarSourcesSchema>["items"][number];
export type ResolvedAvatar =
  | { kind: "icon"; icon: AvatarIcon }
  | { kind: "image"; src: string; key: string; fit: "photo" | "symbol"; fallback: AvatarIcon };

export const ICON_FALLBACK: ResolvedAvatar = { kind: "icon", icon: "EI-07" };
export function resolveAvatar(
  pref: AvatarPreference,
  sources: readonly AvatarSource[],
): ResolvedAvatar {
  const fallback: ResolvedAvatar = { kind: "icon", icon: pref.fallbackIcon };
  const selected = pref.selection;
  if (selected.kind === "icon") return fallback;
  if (selected.kind === "provider") {
    const source = sources.find((s) => s.identityId === selected.identityId);
    if (!source || source.status !== "available") return fallback;
    const src = normalizeAvatarHttpsUrl(source.avatarUrl);
    return src ? {
      kind: "image", src, key: `provider:${source.identityId}:${source.photoRevision}:${src}`,
      fallback: pref.fallbackIcon, fit: "photo",
    } : fallback;
  }
  if (selected.kind === "url") {
    const src = normalizeAvatarHttpsUrl(selected.url);
    return src ? { kind: "image", src, key: `url:${src}`, fallback: pref.fallbackIcon, fit: "photo" } : fallback;
  }
  const slot = getAvailableSystemProfileAvatars().find((s) => s.id === selected.systemId);
  return slot ? {
    kind: "image", src: slot.asset_path, key: `system:${slot.id}`,
    fallback: pref.fallbackIcon, fit: "symbol",
  } : fallback;
}
