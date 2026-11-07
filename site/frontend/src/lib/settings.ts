import { normalizeLang, type Lang } from "./i18n";
import { currentUserDataOwner } from "./userDataCache";
import { windowStateStorage } from "./windowState";
import {
  DEFAULT_INTERFACE_VARIANTS,
  INTERFACE_VARIANT_REGISTRY,
  normalizeInterfaceVariant,
  normalizeInterfaceVariants,
} from "./interfaceVariantRegistry";
import type { InterfaceVariantSettings } from
  "../types/interfaceCustomization";
import {
  GLOBAL_THEME_GROUPS,
  GLOBAL_THEME_CATALOG,
  normalizeGlobalThemeId,
  type GlobalThemeId,
  type ThemeOverrideMap,
  type ThemeOverridesById,
} from "./globalThemeRegistry";
import {
  telegramCloudStorageGet,
  telegramCloudStorageSet,
} from "./telegram";
import {
  COLOR_THEME_PROGRESS_STARTER,
  colorThemeIdFromLegacyGlobalTheme,
  normalizeColorThemeId,
  runtimeLegacyThemeIdForColorTheme,
  type ColorThemeId,
} from "./colorThemeRegistry";

export type UserSettings = {
  lang: Lang;

  // Telegram/browser chrome compatibility. Global EFHC themes are stored
  // separately in global_theme_id and theme_overrides.
  theme_mode: "auto" | "dark" | "light";
  avatar_source: "telegram" | "social" | "energy" | "system";
  avatar_url?: string | null;
  avatar_social_provider?: string | null;
  avatar_social_url?: string | null;
  avatar_custom_images?: string[];
  avatar_custom_index?: number;
  avatar_energy_variant?: string;
  avatar_system_id?: string | null;

  sfx_enabled: boolean;
  music_enabled: boolean;
  sfx_volume: number;
  sfx_pack: "default";
  haptics_enabled: boolean;

  reduce_motion: boolean;
  hide_balances: boolean;
  show_decimal_detail: boolean;

  // Clean startup schema: one initial settings format, no legacy user migration.
  interface_settings_version: 4;
  color_theme_id: ColorThemeId;
  // Runtime CSS theme projection derived deterministically from Color Theme.
  global_theme_id: GlobalThemeId;
  // Theme-specific runtime mirror; independent design selection is authoritative.
  theme_overrides: ThemeOverridesById;
  // Canonical independent design selections. Color changes must not rewrite it.
  interface_variants: InterfaceVariantSettings;

  confirm_actions: boolean;
  confirm_purchase: boolean;
  confirm_withdraw: boolean;
  confirm_convert: boolean;
  confirm_watch_ad: boolean;

  toasts_enabled: boolean;
  important_alerts_only: boolean;
};

// Single persistent namespace for a new project with no historical users.
const KEY = "EFHC_USER_SETTINGS_V1";
const CLOUD_KEY = "ui_settings_v1";

export const COMMON_DEFAULT_INTERFACE_VARIANTS: InterfaceVariantSettings =
  { ...DEFAULT_INTERFACE_VARIANTS };

export const DEFAULT_SETTINGS: UserSettings = {
  lang: "en",
  theme_mode: "dark",
  avatar_source: "telegram",
  avatar_url: null,
  avatar_social_provider: null,
  avatar_social_url: null,
  avatar_custom_images: [],
  avatar_custom_index: 0,
  avatar_energy_variant: "EI-07",
  avatar_system_id: null,
  sfx_enabled: true,
  music_enabled: false,
  sfx_volume: 0.6,
  sfx_pack: "default",
  haptics_enabled: true,
  reduce_motion: false,
  hide_balances: false,
  show_decimal_detail: true,
  interface_settings_version: 4,
  color_theme_id: "CT-01",
  global_theme_id: "01",
  theme_overrides: {},
  interface_variants: { ...COMMON_DEFAULT_INTERFACE_VARIANTS },
  confirm_actions: true,
  confirm_purchase: true,
  confirm_withdraw: true,
  confirm_convert: true,
  confirm_watch_ad: true,
  toasts_enabled: true,
  important_alerts_only: false,
};

export function resetSettings(): UserSettings {
  return {
    ...DEFAULT_SETTINGS,
    interface_variants: { ...DEFAULT_SETTINGS.interface_variants },
    theme_overrides: {},
  };
}

function normalizeThemeOverrides(value: unknown): ThemeOverridesById {
  const input = value && typeof value === "object"
    ? value as Record<string, unknown>
    : {};
  const out: ThemeOverridesById = {};
  for (const definition of GLOBAL_THEME_CATALOG) {
    const raw = input[definition.id];
    if (!raw || typeof raw !== "object") continue;
    const source = raw as Record<string, unknown>;
    const normalized: ThemeOverrideMap = {};
    for (const group of GLOBAL_THEME_GROUPS) {
      if (typeof source[group] !== "string") continue;
      normalized[group] = normalizeInterfaceVariant(group, source[group]);
    }
    if (Object.keys(normalized).length > 0) {
      out[definition.id] = normalized;
    }
  }
  return out;
}

function normalizeIndependentDesignSelections(value: unknown): InterfaceVariantSettings {
  const input = value && typeof value === "object"
    ? value as Partial<InterfaceVariantSettings>
    : {};
  return normalizeInterfaceVariants({
    ...COMMON_DEFAULT_INTERFACE_VARIANTS,
    ...input,
  });
}

function normalizeAvatarImages(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .filter((item) => /^data:image\/(?:png|jpeg|webp);base64,/i.test(item))
    .slice(0, 3);
}

function normalizeAvatarSource(value: unknown): UserSettings["avatar_source"] {
  // Only configured avatar providers or system-defined options are accepted.
  return value === "energy" || value === "social" || value === "telegram" || value === "system"
    ? value
    : "telegram";
}

function normalizeSocialAvatarUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const candidate = value.trim();
  if (!candidate || candidate.length > 2048) return null;
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== "https:" || !parsed.hostname) return null;
    if (parsed.username || parsed.password) return null;
    return candidate;
  } catch {
    return null;
  }
}

function withLocalAvatarPayload(
  cloudSource: unknown,
  local: UserSettings,
): unknown {
  const source = cloudSource && typeof cloudSource === "object"
    ? cloudSource as Record<string, unknown>
    : {};
  return {
    ...source,
    avatar_custom_images: local.avatar_custom_images || [],
    avatar_custom_index: local.avatar_custom_index || 0,
    avatar_url: local.avatar_url || null,
  };
}

function cloudSafeSettings(s: UserSettings): UserSettings {
  return {
    ...s,
    avatar_custom_images: [],
    avatar_url: null,
  };
}


function normalizeSettings(parsed: any): UserSettings {
  // Only the canonical startup schema is accepted; prior test snapshots are not users.
  // Never mutate the caller-owned object.
  if (!parsed || typeof parsed !== "object" || ![1, 2, 3, 4].includes(parsed.interface_settings_version)) {
    return resetSettings();
  }
  const source = parsed;
  const resetRetiredSelections = parsed.interface_settings_version === 1;
  const resetEnergySelections = ![3, 4].includes(parsed.interface_settings_version);
  const colorThemeId = normalizeColorThemeId(source.color_theme_id);
  // Canonical Color Theme projects to the runtime CSS theme slot.
  const globalThemeId = runtimeLegacyThemeIdForColorTheme(colorThemeId);
  const themeOverrides = resetRetiredSelections ? {} : normalizeThemeOverrides(source.theme_overrides);
  const effectiveVariants = resetRetiredSelections
    ? { ...DEFAULT_INTERFACE_VARIANTS }
    : normalizeIndependentDesignSelections(source.interface_variants);
  // OWNER: retired choices fall back to the active CT canon independently.
  // Surviving model IDs and the other page's selection remain unchanged.
  if (!resetEnergySelections) {
    for (const group of ["PB", "RP"] as const) {
      const storedProgress = source.interface_variants?.[group];
      if (typeof storedProgress === "string"
        && !INTERFACE_VARIANT_REGISTRY[group].includes(storedProgress)) {
        effectiveVariants[group] = COLOR_THEME_PROGRESS_STARTER[colorThemeId]
          .replace("PB-", `${group}-`);
      }
    }
  }
  // OWNER 0560: reset only BN from pre-v4 preferences; old numbering changed.
  // Preserve all unrelated independent designs and Color Theme selections.
  if (parsed.interface_settings_version !== 4) {
    effectiveVariants.BN = "BN-01";
    for (const definition of GLOBAL_THEME_CATALOG) {
      const override = themeOverrides[definition.id];
      if (!override) continue;
      delete override.BN;
      if (Object.keys(override).length === 0) delete themeOverrides[definition.id];
    }
  }
  // OWNER 0548: reset only the retired EI/PB/RP selections; other choices survive v2->v3.
  if (resetEnergySelections) {
    effectiveVariants.EI = "EI-07";
    effectiveVariants.PB = "PB-01";
    effectiveVariants.RP = "RP-01";
  }
  const avatarImages = normalizeAvatarImages(source.avatar_custom_images);
  const legacyAvatar = typeof source.avatar_url === "string"
    && /^data:image\/(?:png|jpeg|webp);base64,/i.test(source.avatar_url)
    ? source.avatar_url
    : null;
  if (avatarImages.length === 0 && legacyAvatar) avatarImages.push(legacyAvatar);
  const requestedIndex = Number.isInteger(source.avatar_custom_index)
    ? Number(source.avatar_custom_index)
    : 0;
  const avatarIndex = avatarImages.length > 0
    ? Math.max(0, Math.min(avatarImages.length - 1, requestedIndex))
    : 0;
  const avatarUrl = avatarImages[avatarIndex] || null;
  const socialAvatarUrl = normalizeSocialAvatarUrl(source.avatar_social_url);
  const socialProvider = typeof source.avatar_social_provider === "string"
    && /^[a-z][a-z0-9_-]{0,31}$/.test(source.avatar_social_provider)
    ? source.avatar_social_provider
    : null;
  const systemAvatarId = typeof source.avatar_system_id === "string"
    && /^avatar-(?:0[1-9]|10)$/.test(source.avatar_system_id)
    ? source.avatar_system_id
    : null;
  const requestedAvatarSource = normalizeAvatarSource(source.avatar_source);
  const normalizedAvatarEnergyVariant = normalizeInterfaceVariant(
    "EI",
    source.avatar_energy_variant || "EI-07",
  );
  const avatarEnergyVariant = normalizedAvatarEnergyVariant;
  const avatarSource = requestedAvatarSource === "social" && (!socialAvatarUrl || !socialProvider)
    ? "telegram"
    : requestedAvatarSource === "system" && !systemAvatarId
      ? "telegram"
      : requestedAvatarSource;

  return {
    ...DEFAULT_SETTINGS,
    ...source,
    lang: normalizeLang(source.lang),
    avatar_source: avatarSource,
    avatar_url: avatarUrl,
    avatar_social_provider: socialProvider,
    avatar_social_url: socialAvatarUrl,
    avatar_custom_images: avatarImages,
    avatar_custom_index: avatarIndex,
    avatar_energy_variant: avatarEnergyVariant,
    avatar_system_id: systemAvatarId,
    hide_balances: false,
    show_decimal_detail: true, // OWNER 0556: full display precision is unconditional.
    interface_settings_version: 4,
    color_theme_id: colorThemeId,
    global_theme_id: globalThemeId,
    theme_overrides: themeOverrides,
    interface_variants: effectiveVariants,
  } as UserSettings;
}

export function loadSettings(): UserSettings {
  if (typeof window === "undefined") return resetSettings();
  try {
    const owner = currentUserDataOwner();
    const local = JSON.parse(windowStateStorage().getItem(KEY) || "null");
    if (local && local.settings_owner === owner) return normalizeSettings(local);
    const legacyOwner = window.localStorage.getItem(`${KEY}:legacy-owner`);
    const raw = (owner ? window.localStorage.getItem(`${KEY}:${owner}`) : null)
      || (!legacyOwner || legacyOwner === owner ? window.localStorage.getItem(KEY) : null);
    if (raw) return normalizeSettings(JSON.parse(raw) || {});
    return resetSettings();
  } catch {
    return resetSettings();
  }
}

export async function loadSettingsAsync(): Promise<UserSettings> {
  const local = loadSettings();
  const owner = currentUserDataOwner();
  // A current local owner model wins over an old provider-level cloud setting.
  try {
    if (!owner || windowStateStorage().getItem(KEY)) return local;
    const raw = await telegramCloudStorageGet(`${CLOUD_KEY}_${owner}`);
    if (currentUserDataOwner() !== owner) return loadSettings();
    // A local choice made while the Telegram request was pending always wins.
    if (windowStateStorage().getItem(KEY) || window.localStorage.getItem(`${KEY}:${owner}`)) return loadSettings();
    if (raw) return normalizeSettings(withLocalAvatarPayload(JSON.parse(raw) || {}, local));
    return local;
  } catch {
    return local;
  }
}

export function saveSettings(s: UserSettings): void {
  if (typeof window === "undefined") return;
  try {
    const owner = currentUserDataOwner();
    const raw = JSON.stringify({...s, settings_owner: owner, interface_settings_version: 4});
    windowStateStorage().setItem(KEY, raw);
    if (owner) {
      window.localStorage.setItem(`${KEY}:${owner}`, raw);
      if (!window.localStorage.getItem(`${KEY}:legacy-owner`)) window.localStorage.setItem(`${KEY}:legacy-owner`, owner);
    }
  } catch {
    // ignore
  }
}

/** Bind the loaded view preferences once, without adopting another window's owner. */
export function bindWindowSettings(): boolean {
  try {
    const raw = JSON.parse(windowStateStorage().getItem(KEY) || "null");
    if (raw?.settings_owner === currentUserDataOwner()) return false;
  } catch { /* Replace malformed optional preferences with defaults. */ }
  saveSettings(loadSettings());
  return true;
}

// Local preferences are authoritative. Serialize cloud synchronization per owner
// so a slower, older Telegram write cannot overwrite a newer local selection.
const settingsCloudSync = new Map<string, Promise<void>>();

export async function saveSettingsAsync(s: UserSettings): Promise<void> {
  saveSettings(s); // Immediate, independent of Telegram and backend availability.
  const owner = currentUserDataOwner();
  if (!owner) return; // Never publish one anonymous window's choices globally.
  const key = `${CLOUD_KEY}_${owner}`;
  const previous = settingsCloudSync.get(key) || Promise.resolve();
  const next = previous.catch(() => undefined).then(async () => {
    if (currentUserDataOwner() !== owner) return;
    // Re-read the latest choice; an earlier scheduled request cannot undo it.
    await telegramCloudStorageSet(key, JSON.stringify(cloudSafeSettings(loadSettings())));
  }).catch(() => undefined);
  settingsCloudSync.set(key, next);
  await next;
  if (settingsCloudSync.get(key) === next) settingsCloudSync.delete(key);
}
