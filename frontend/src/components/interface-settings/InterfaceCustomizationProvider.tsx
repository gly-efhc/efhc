import React, {
  createContext,
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/router";
import { resolveHeaderThemeComposition } from "../../lib/headerThemeComposition";
import type { UserSettings } from "../../lib/settings";
import {
  cycleInterfaceVariant,
  getRouteInterfaceGroups,
  normalizeInterfaceVariant,
  normalizeInterfaceVariants,
} from "../../lib/interfaceVariantRegistry";
import {
  buildThemeOverride,
  GLOBAL_THEME_GROUPS,
  normalizeGlobalThemeId,
  type GlobalThemeId,
  type ThemeOverridesById,
} from "../../lib/globalThemeRegistry";
import {
  colorThemeIdFromLegacyGlobalTheme,
  cycleColorThemeRecord,
  COLOR_THEME_PROGRESS_STARTER,
  normalizeColorThemeId,
  runtimeLegacyThemeIdForColorTheme,
  type ColorThemeId,
} from "../../lib/colorThemeRegistry";
import type {
  InterfaceCustomizationMode,
  InterfaceVariantGroup,
  InterfaceVariantSettings,
  VariantDotsPlacement,
} from "../../types/interfaceCustomization";
import { InterfaceVariantDotsLayer } from "./InterfaceVariantDotsLayer";

type RegisteredSurface = {
  id: string;
  group: InterfaceVariantGroup;
  element: HTMLElement;
  placement: VariantDotsPlacement;
};

type ContextValue = {
  mode: InterfaceCustomizationMode;
  saved: InterfaceVariantSettings;
  effective: InterfaceVariantSettings;
  globalThemeId: GlobalThemeId;
  colorThemeId: ColorThemeId;
  mutationBlocked: boolean;
  buttonVisible: boolean;
  activeGroups: readonly InterfaceVariantGroup[];
  enter: () => void;
  save: () => void;
  next: (group: InterfaceVariantGroup) => void;
  previous: (group: InterfaceVariantGroup) => void;
  nextGlobalTheme: () => void;
  previousGlobalTheme: () => void;
  selectGlobalTheme: (themeId: string) => void;
  selectIndividualVariant: (group: InterfaceVariantGroup, value: string) => void;
  revealButton: () => void;
  isGroupActive: (group: InterfaceVariantGroup) => boolean;
  registerSurface: (surface: RegisteredSurface) => () => void;
  blockNonCustomizationInteraction: (
    event: React.SyntheticEvent<HTMLElement>,
  ) => void;
};

const noopVariants: InterfaceVariantSettings = {
  SC: "SC-02",
  HB: "HB-01",
  HS: "HS-03",
  EG: "EG-01",
  BN: "BN-01",
  EI: "EI-07",
  PB: "PB-01",
  RP: "PB-01",
  PH: "PH-01",
  PT: "PT-01",
  PC: "PC-01",
  PA: "PA-01",
  XH: "XH-01",
  XS: "XS-01",
  XC: "XC-01",
  XA: "XA-01",
  TG: "TG-01",
  RG: "RG-01",
  KG: "KG-01",
  WG: "WG-01",
  HU: "HU-01",
  FQ: "FQ-01",
  PM: "PM-01",
  HI: "HI-01",
  WD: "WD-01",
  AD: "AD-01",
  BS: "BS-01",
  ER: "ER-01",
  AM: "AM-01",
};

export const InterfaceCustomizationContext = createContext<ContextValue>({
  mode: "idle",
  saved: noopVariants,
  effective: noopVariants,
  globalThemeId: "01",
  colorThemeId: "CT-01",
  mutationBlocked: false,
  buttonVisible: true,
  activeGroups: [],
  enter: () => undefined,
  save: () => undefined,
  next: () => undefined,
  previous: () => undefined,
  nextGlobalTheme: () => undefined,
  previousGlobalTheme: () => undefined,
  selectGlobalTheme: () => undefined,
  selectIndividualVariant: () => undefined,
  revealButton: () => undefined,
  isGroupActive: () => false,
  registerSurface: () => () => undefined,
  blockNonCustomizationInteraction: () => undefined,
});

function withUpdatedThemeOverride(
  current: ThemeOverridesById,
  themeId: GlobalThemeId,
  effective: InterfaceVariantSettings,
): ThemeOverridesById {
  const next: ThemeOverridesById = { ...current };
  const override = buildThemeOverride(themeId, effective);
  if (Object.keys(override).length === 0) {
    delete next[themeId];
  } else {
    next[themeId] = override;
  }
  return next;
}

export function InterfaceCustomizationProvider(
  props: React.PropsWithChildren<{
    settings: UserSettings;
    setSettings: Dispatch<SetStateAction<UserSettings>>;
  }>,
) {
  const router = useRouter();
  const normalizedFromSettings = useMemo(
    () => normalizeInterfaceVariants(props.settings.interface_variants),
    [props.settings.interface_variants],
  );
  const normalizedThemeId = useMemo(
    () => normalizeGlobalThemeId(props.settings.global_theme_id),
    [props.settings.global_theme_id],
  );
  const normalizedColorThemeId = useMemo(
    () => normalizeColorThemeId(props.settings.color_theme_id),
    [props.settings.color_theme_id],
  );
  const [mode, setMode] = useState<InterfaceCustomizationMode>("idle");
  const [saved, setSaved] = useState(normalizedFromSettings);
  const [draft, setDraft] = useState(normalizedFromSettings);
  const [savedThemeId, setSavedThemeId] = useState<GlobalThemeId>(
    normalizedThemeId,
  );
  const [draftThemeId, setDraftThemeId] = useState<GlobalThemeId>(
    normalizedThemeId,
  );
  const [savedColorThemeId, setSavedColorThemeId] = useState<ColorThemeId>(
    normalizedColorThemeId,
  );
  const [draftColorThemeId, setDraftColorThemeId] = useState<ColorThemeId>(
    normalizedColorThemeId,
  );
  const [draftOverrides, setDraftOverrides] = useState<ThemeOverridesById>(
    props.settings.theme_overrides,
  );
  const [buttonVisible, setButtonVisible] = useState(true);
  const [surfaces, setSurfaces] = useState<RegisteredSurface[]>([]);
  const hideTimerRef = useRef<number | null>(null);
  const activeGroups = useMemo(
    () => getRouteInterfaceGroups(router.pathname),
    [router.pathname],
  );

  const clearHideTimer = useCallback(() => {
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  const revealButton = useCallback(() => {
    setButtonVisible(true);
    clearHideTimer();
    if (mode === "editing") return;
    hideTimerRef.current = window.setTimeout(() => {
      setButtonVisible(false);
      hideTimerRef.current = null;
    }, 3_000);
  }, [clearHideTimer, mode]);

  useEffect(() => {
    if (mode === "editing") {
      clearHideTimer();
      setButtonVisible(true);
      return;
    }
    revealButton();
  }, [clearHideTimer, mode, revealButton]);

  useEffect(() => {
    if (mode !== "idle") return;
    setSaved(normalizedFromSettings);
    setDraft(normalizedFromSettings);
    setSavedThemeId(normalizedThemeId);
    setDraftThemeId(normalizedThemeId);
    setSavedColorThemeId(normalizedColorThemeId);
    setDraftColorThemeId(normalizedColorThemeId);
    setDraftOverrides(props.settings.theme_overrides);
  }, [
    mode,
    normalizedFromSettings,
    normalizedThemeId,
    normalizedColorThemeId,
    props.settings.theme_overrides,
  ]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const activity = () => revealButton();
    window.addEventListener("pointermove", activity, { passive: true });
    window.addEventListener("pointerdown", activity, { passive: true });
    window.addEventListener("touchstart", activity, { passive: true });
    window.addEventListener("scroll", activity, { passive: true });
    window.addEventListener("keydown", activity);
    return () => {
      window.removeEventListener("pointermove", activity);
      window.removeEventListener("pointerdown", activity);
      window.removeEventListener("touchstart", activity);
      window.removeEventListener("scroll", activity);
      window.removeEventListener("keydown", activity);
    };
  }, [revealButton]);

  useEffect(() => {
    const discardDraft = () => {
      setMode("idle");
      setDraft(saved);
      setDraftThemeId(savedThemeId);
      setDraftColorThemeId(savedColorThemeId);
      setDraftOverrides(props.settings.theme_overrides);
    };
    const onBackRequest = (event: Event) => {
      if (mode !== "editing") return;
      event.preventDefault();
      discardDraft();
    };
    router.events.on("routeChangeStart", discardDraft);
    document.addEventListener("efhc:back-request", onBackRequest);
    return () => {
      router.events.off("routeChangeStart", discardDraft);
      document.removeEventListener("efhc:back-request", onBackRequest);
    };
  }, [
    router.events, saved, savedThemeId, savedColorThemeId,
    props.settings.theme_overrides, mode,
  ]);

  const isGroupActive = useCallback(
    (group: InterfaceVariantGroup) => activeGroups.includes(group),
    [activeGroups],
  );

  const enter = useCallback(() => {
    setDraft(saved);
    setDraftThemeId(savedThemeId);
    setDraftColorThemeId(savedColorThemeId);
    setDraftOverrides(props.settings.theme_overrides);
    setMode("editing");
  }, [saved, savedThemeId, savedColorThemeId, props.settings.theme_overrides]);

  const save = useCallback(() => {
    const normalized = normalizeInterfaceVariants(draft);
    const canonicalLegacyThemeId = runtimeLegacyThemeIdForColorTheme(
      draftColorThemeId,
    );
    const nextOverrides = withUpdatedThemeOverride(
      draftOverrides,
      canonicalLegacyThemeId,
      normalized,
    );
    setSaved(normalized);
    setSavedThemeId(canonicalLegacyThemeId);
    setDraftThemeId(canonicalLegacyThemeId);
    setSavedColorThemeId(draftColorThemeId);
    setDraftOverrides(nextOverrides);
    props.setSettings((current) => ({
      ...current,
      hide_balances: false,
      interface_settings_version: 4,
      color_theme_id: draftColorThemeId,
      global_theme_id: canonicalLegacyThemeId,
      theme_overrides: nextOverrides,
      interface_variants: normalized,
    }));
    setMode("idle");
    setButtonVisible(true);
  }, [draft, draftOverrides, draftColorThemeId, props]);

  const next = useCallback((group: InterfaceVariantGroup) => {
    if (!isGroupActive(group)) return;
    setDraft((current) => cycleInterfaceVariant(current, group, 1));
  }, [isGroupActive]);

  const previous = useCallback((group: InterfaceVariantGroup) => {
    if (!isGroupActive(group)) return;
    setDraft((current) => cycleInterfaceVariant(current, group, -1));
  }, [isGroupActive]);

  const applyThemeSelection = useCallback((themeId: string) => {
    const nextColorThemeId = themeId.startsWith("CT-")
      ? normalizeColorThemeId(themeId)
      : (/^0?(?:[1-9]|10)$/.test(themeId)
        ? normalizeColorThemeId(`CT-${themeId.padStart(2, "0")}`)
        : colorThemeIdFromLegacyGlobalTheme(themeId === "13" ? "13" : normalizeGlobalThemeId(themeId)));
    const nextLegacyThemeId = runtimeLegacyThemeIdForColorTheme(
      nextColorThemeId,
    );

    // Cycle0459: the user selects one of exactly ten Color Themes.
    // global_theme_id is a deterministic legacy rendering projection only;
    // independent interface_variants remain untouched.
    const currentColorId = mode === "editing" ? draftColorThemeId : savedColorThemeId;
    const sourceVariants = mode === "editing" ? draft : saved;
    const nextVariants = nextColorThemeId === currentColorId ? sourceVariants : {
      ...sourceVariants,
      PB: COLOR_THEME_PROGRESS_STARTER[nextColorThemeId],
      RP: COLOR_THEME_PROGRESS_STARTER[nextColorThemeId].replace("PB-", "RP-"),
    };
    const sourceOverrides = mode === "editing"
      ? draftOverrides
      : props.settings.theme_overrides;
    const nextOverrides = withUpdatedThemeOverride(
      sourceOverrides,
      nextLegacyThemeId,
      nextVariants,
    );

    if (mode === "editing") {
      setDraft(nextVariants);
      setDraftOverrides(nextOverrides);
      setDraftThemeId(nextLegacyThemeId);
      setDraftColorThemeId(nextColorThemeId);
      return;
    }
    setSaved(nextVariants);
    setDraft(nextVariants);
    setSavedThemeId(nextLegacyThemeId);
    setDraftThemeId(nextLegacyThemeId);
    setSavedColorThemeId(nextColorThemeId);
    setDraftColorThemeId(nextColorThemeId);
    setDraftOverrides(nextOverrides);
    props.setSettings((current) => ({
      ...current,
      interface_settings_version: 4,
      color_theme_id: nextColorThemeId,
      global_theme_id: nextLegacyThemeId,
      theme_overrides: nextOverrides,
      interface_variants: nextVariants,
    }));
  }, [draft, draftOverrides, draftColorThemeId, savedColorThemeId, mode, props, saved]);

  const selectIndividualVariant = useCallback((
    group: InterfaceVariantGroup,
    value: string,
  ) => {
    if ((GLOBAL_THEME_GROUPS as readonly string[]).includes(group)) return;
    const normalizedValue = normalizeInterfaceVariant(group, value);
    const source = mode === "editing" ? draft : saved;
    const nextVariants = normalizeInterfaceVariants({
      ...source,
      [group]: normalizedValue,
    });
    if (mode === "editing") {
      setDraft(nextVariants);
      return;
    }
    setSaved(nextVariants);
    setDraft(nextVariants);
    props.setSettings((current) => ({
      ...current,
      interface_settings_version: 4,
      interface_variants: nextVariants,
    }));
  }, [draft, mode, props, saved]);

  const nextGlobalTheme = useCallback(() => {
    const nextTheme = cycleColorThemeRecord(draftColorThemeId, 1);
    const nextLegacyThemeId = runtimeLegacyThemeIdForColorTheme(nextTheme.id);
    if (nextTheme.id !== draftColorThemeId) {
      setDraft((current) => ({...current, PB: COLOR_THEME_PROGRESS_STARTER[nextTheme.id], RP: COLOR_THEME_PROGRESS_STARTER[nextTheme.id].replace("PB-", "RP-")}));
    }
    setDraftColorThemeId(nextTheme.id);
    setDraftThemeId(nextLegacyThemeId);
    setDraftOverrides((current) => withUpdatedThemeOverride(
      current, nextLegacyThemeId, nextTheme.id !== draftColorThemeId
        ? {...draft, PB: COLOR_THEME_PROGRESS_STARTER[nextTheme.id], RP: COLOR_THEME_PROGRESS_STARTER[nextTheme.id].replace("PB-", "RP-")} : draft,
    ));
  }, [draft, draftColorThemeId]);

  const previousGlobalTheme = useCallback(() => {
    const nextTheme = cycleColorThemeRecord(draftColorThemeId, -1);
    const nextLegacyThemeId = runtimeLegacyThemeIdForColorTheme(nextTheme.id);
    if (nextTheme.id !== draftColorThemeId) {
      setDraft((current) => ({...current, PB: COLOR_THEME_PROGRESS_STARTER[nextTheme.id], RP: COLOR_THEME_PROGRESS_STARTER[nextTheme.id].replace("PB-", "RP-")}));
    }
    setDraftColorThemeId(nextTheme.id);
    setDraftThemeId(nextLegacyThemeId);
    setDraftOverrides((current) => withUpdatedThemeOverride(
      current, nextLegacyThemeId, nextTheme.id !== draftColorThemeId
        ? {...draft, PB: COLOR_THEME_PROGRESS_STARTER[nextTheme.id], RP: COLOR_THEME_PROGRESS_STARTER[nextTheme.id].replace("PB-", "RP-")} : draft,
    ));
  }, [draft, draftColorThemeId]);

  const registerSurface = useCallback((surface: RegisteredSurface) => {
    setSurfaces((current) => [
      ...current.filter((item) => item.id !== surface.id),
      surface,
    ]);
    return () => {
      setSurfaces((current) => current.filter(
        (item) => item.id !== surface.id,
      ));
    };
  }, []);

  const blockNonCustomizationInteraction = useCallback(
    (event: React.SyntheticEvent<HTMLElement>) => {
      if (mode !== "editing") return;
      const target = event.target as Element | null;
      if (
        target?.closest('[data-interface-customization-control="true"]')
        || target?.closest('[data-app-navigation]')
        || target?.closest('[data-interface-variant-surface="true"]')
        || target?.closest('[data-global-theme-surface="true"]')
      ) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    },
    [mode],
  );

  const effective = mode === "editing" ? draft : saved;
  const globalThemeId = mode === "editing" ? draftThemeId : savedThemeId;
  const colorThemeId = mode === "editing" ? draftColorThemeId : savedColorThemeId;
  // v866 has document-level token owners as well as shell-level selectors.
  // Mirror the active USER state, then restore the previous document state on
  // route changes/unmount so Shop and frozen Admin do not inherit USER chroma.
  useEffect(() => {
    if (router.pathname.startsWith("/admin") || router.pathname.startsWith("/browser-shop")) return;
    const root = document.documentElement;
    const attributes: Record<string, string> = {
      "data-interface-app-mode": "user",
      "data-customization-mode": mode,
      "data-color-theme-id": colorThemeId,
      "data-global-theme-id": globalThemeId,
      "data-status-color": resolveHeaderThemeComposition(effective.HS).statuses,
    };
    const previous = Object.keys(attributes).map((name) => [name, root.getAttribute(name)] as const);
    for (const [name, value] of Object.entries(attributes)) root.setAttribute(name, value);
    return () => {
      for (const [name, value] of previous) {
        if (value === null) root.removeAttribute(name);
        else root.setAttribute(name, value);
      }
    };
  }, [router.pathname, mode, colorThemeId, globalThemeId, effective.HS]);
  const value = useMemo<ContextValue>(() => ({
    mode,
    saved,
    effective,
    globalThemeId,
    colorThemeId,
    mutationBlocked: mode === "editing",
    buttonVisible: mode === "editing" || buttonVisible,
    activeGroups,
    enter,
    save,
    next,
    previous,
    nextGlobalTheme,
    previousGlobalTheme,
    selectGlobalTheme: applyThemeSelection,
    selectIndividualVariant,
    revealButton,
    isGroupActive,
    registerSurface,
    blockNonCustomizationInteraction,
  }), [
    activeGroups,
    applyThemeSelection,
    blockNonCustomizationInteraction,
    buttonVisible,
    effective,
    enter,
    globalThemeId,
    colorThemeId,
    isGroupActive,
    mode,
    next,
    previous,
    nextGlobalTheme,
    previousGlobalTheme,
    registerSurface,
    revealButton,
    save,
    selectIndividualVariant,
    saved,
  ]);

  return (
    <InterfaceCustomizationContext.Provider value={value}>
      {props.children}
      <InterfaceVariantDotsLayer
        surfaces={surfaces}
        mode={mode}
        effective={effective}
        activeGroups={activeGroups}
      />
    </InterfaceCustomizationContext.Provider>
  );
}
