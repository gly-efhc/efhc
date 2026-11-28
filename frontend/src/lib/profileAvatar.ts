import type { UserSettings } from "./settings";
import { normalizeInterfaceVariant } from "./interfaceVariantRegistry";

export const PROFILE_AVATAR_MAX_CUSTOM_IMAGES = 3; // legacy read-only compatibility
export const PROFILE_AVATAR_DENIED_ENERGY_VARIANTS = [] as const;

export const PROFILE_AVATAR_ENERGY_VARIANTS = [
  "EI-07",
] as const;

export type SystemProfileAvatarSlot = {
  id: string;
  asset_path: string;
  available: boolean;
};

// Ten reserved built-in avatar slots. Artwork is not fabricated here: a slot
// becomes selectable only after its approved asset exists and available=true.
export const SYSTEM_PROFILE_AVATAR_SLOTS: readonly SystemProfileAvatarSlot[] =
  Array.from({ length: 10 }, (_, index) => ({
    id: `avatar-${String(index + 1).padStart(2, "0")}`,
    asset_path: `/assets/profile-avatars/avatar-${String(index + 1).padStart(2, "0")}.webp`,
    available: false,
  }));

export function getAvailableSystemProfileAvatars(): SystemProfileAvatarSlot[] {
  return SYSTEM_PROFILE_AVATAR_SLOTS.filter((item) => item.available);
}

export function getSystemProfileAvatarUrl(settings: UserSettings): string | null {
  const id = settings.avatar_system_id || null;
  if (!id) return null;
  const slot = SYSTEM_PROFILE_AVATAR_SLOTS.find((item) => item.id === id);
  return slot?.available ? slot.asset_path : null;
}

export function getActiveCustomAvatar(settings: UserSettings): string | null {
  // Legacy compatibility only. v066 no longer exposes local file upload.
  const images = Array.isArray(settings.avatar_custom_images)
    ? settings.avatar_custom_images.slice(0, PROFILE_AVATAR_MAX_CUSTOM_IMAGES)
    : [];
  const index = Number.isInteger(settings.avatar_custom_index)
    ? Number(settings.avatar_custom_index)
    : 0;
  return images[index] || settings.avatar_url || null;
}

export function getEnergyAvatarVariant(settings: UserSettings): string {
  const variant = normalizeInterfaceVariant(
    "EI",
    settings.avatar_energy_variant || "EI-07",
  );
  return PROFILE_AVATAR_ENERGY_VARIANTS.some((item) => item === variant)
    ? variant
    : "EI-07";
}
