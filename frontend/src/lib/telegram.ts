import type { Lang } from "./i18n";
import {
  type TelegramId,
  telegramIdFromProvider,
} from "../types/identity";
import { useEffect } from "react";

declare global {
  interface Window {
    Telegram?: any;
  }
}

let _tg_ready_once = false;

export type TgUser = {
  id: TelegramId;
  username?: string;
  first_name?: string;
  last_name?: string;
  language_code?: string;
  photo_url?: string;
};

export function tg(): any | null {
  return getTelegramWebApp();
}

export function getTelegramWebApp(): any | null {
  try {
    return window.Telegram?.WebApp || null;
  } catch {
    return null;
  }
}


export function isTelegramMiniApp(): boolean {
  const tg = getTelegramWebApp();
  try {
    return Boolean(
      tg?.initData || tg?.initDataUnsafe?.user || tg?.platform,
    );
  } catch {
    return false;
  }
}

function setCssPxVar(
  root: HTMLElement,
  name: string,
  value: unknown,
): void {
  if (typeof value !== "number" || !Number.isFinite(value)) return;
  root.style.setProperty(name, `${Math.max(0, value)}px`);
}

function setCssPositivePxVar(
  root: HTMLElement,
  name: string,
  value: unknown,
): void {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return;
  root.style.setProperty(name, `${value}px`);
}

function setCssStringVar(
  root: HTMLElement,
  name: string,
  value: unknown,
): void {
  if (typeof value !== "string" || !value.trim()) return;
  root.style.setProperty(name, value);
}

export function telegramReady(): void {
  const tg = getTelegramWebApp();
  try {
    tg?.ready?.();
    tg?.expand?.();
  } catch {
    // ignore
  }
}

// Apply minimal Telegram WebApp integration:
// - viewport / safe-area CSS vars
// - keep app background aligned to Telegram (best effort)
export function tgReady(): void {
  if (_tg_ready_once) return;
  _tg_ready_once = true;
  telegramReady();
}

export function applyTelegramCssVars(): void {
  if (typeof document === "undefined") return;
  const tg = getTelegramWebApp();
  const root = document.documentElement;

  root.dataset.tmaShell = isTelegramMiniApp() ? "telegram" : "browser";
  try {
    const platform = tg?.platform;
    if (typeof platform === "string" && platform.trim()) {
      root.dataset.tgPlatform = platform;
    }
    if (typeof tg?.isExpanded === "boolean") {
      root.dataset.tgViewportState = tg.isExpanded
        ? "expanded"
        : "compact";
    }
  } catch {
    // ignore
  }

  // Telegram WebApp viewport metrics (best effort, depends on client
  // version)
  try {
    setCssPositivePxVar(root, "--tg-viewport-height", tg?.viewportHeight);
    setCssPositivePxVar(
      root,
      "--tg-viewport-stable-height",
      tg?.viewportStableHeight,
    );
  } catch {
    // ignore
  }

  // Safe area insets (newer Telegram clients expose safeAreaInset /
  // contentSafeAreaInset)
  try {
    const safeInset = tg?.safeAreaInset || null;
    const contentInset = tg?.contentSafeAreaInset || null;
    const top = contentInset?.top ?? safeInset?.top;
    const bottom = contentInset?.bottom ?? safeInset?.bottom;
    setCssPxVar(root, "--tg-safe-top", top);
    setCssPxVar(root, "--tg-safe-bottom", bottom);
    setCssPxVar(root, "--tg-content-safe-top", contentInset?.top);
    setCssPxVar(root, "--tg-content-safe-bottom", contentInset?.bottom);
    setCssPxVar(root, "--tg-device-safe-top", safeInset?.top);
    setCssPxVar(root, "--tg-device-safe-bottom", safeInset?.bottom);
  } catch {
    // ignore
  }

  // Theme params (do not override EFHC palette, but expose Telegram
  // colors as CSS vars for better native feel.
  try {
    const tp = tg?.themeParams || {};
    const bg = tp.bg_color;
    const text = tp.text_color;
    const hint = tp.hint_color;
    const link = tp.link_color;
    const btn = tp.button_color;
    const btnText = tp.button_text_color;
    const secondary = tp.secondary_bg_color;

    // Canon Telegram theme tokens.
    if (typeof bg === "string") {
      root.style.setProperty("--tg-bg", bg);
    }
    if (typeof text === "string") {
      root.style.setProperty("--tg-text", text);
    }
    if (typeof hint === "string") {
      root.style.setProperty("--tg-hint", hint);
    }
    if (typeof link === "string") {
      root.style.setProperty("--tg-link", link);
    }
    if (typeof btn === "string") {
      root.style.setProperty("--tg-button", btn);
    }
    if (typeof btnText === "string") {
      root.style.setProperty("--tg-button-text", btnText);
    }
    if (typeof secondary === "string") {
      root.style.setProperty("--tg-secondary-bg", secondary);
    } else if (typeof bg === "string") {
      root.style.setProperty("--tg-secondary-bg", bg);
    }

    // Back-compat vars used by older components.
    const header = tp.header_bg_color;

    if (typeof bg === "string") {
      root.style.setProperty("--tg-bg-color", bg);
    }
    if (typeof header === "string") {
      root.style.setProperty("--tg-header-bg-color", header);
    }
    if (typeof text === "string") {
      root.style.setProperty("--tg-text-color", text);
    }
    if (typeof hint === "string") {
      root.style.setProperty("--tg-hint-color", hint);
    }
    if (typeof link === "string") {
      root.style.setProperty("--tg-link-color", link);
    }
    if (typeof btn === "string") {
      root.style.setProperty("--tg-button-color", btn);
    }
    if (typeof btnText === "string") {
      root.style.setProperty("--tg-button-text-color", btnText);
    }
    if (typeof secondary === "string") {
      root.style.setProperty("--tg-secondary-bg-color", secondary);
    }

    const scheme = tg?.colorScheme;
    if (scheme === "light" || scheme === "dark") {
      root.dataset.tgColorScheme = scheme;
      // Helps native form controls choose correct palette.
      (root.style as any).colorScheme = scheme;
    }
  } catch {
    // ignore
  }
}

export function setTelegramChromeColors(
  bgHex: string,
  headerHex?: string,
): void {
  const tg = getTelegramWebApp();
  try {
    tg?.setBackgroundColor?.(bgHex);
  } catch {
    // ignore
  }
  try {
    tg?.setHeaderColor?.(headerHex || bgHex);
  } catch {
    // ignore
  }
}

export function getTelegramInitData(): string | null {
  const tg = getTelegramWebApp();
  try {
    return typeof tg?.initData === "string" ? tg.initData : null;
  } catch {
    return null;
  }
}

export function getTelegramUser(): TgUser | null {
  const tg = getTelegramWebApp();
  try {
    const u = tg?.initDataUnsafe?.user;
    if (!u) return null;
    const id = telegramIdFromProvider(u.id);
    return {
      id,
      username: u.username,
      first_name: u.first_name,
      last_name: u.last_name,
      language_code: u.language_code,
      photo_url: u.photo_url,
    };
  } catch {
    return null;
  }
}

export function hapticImpact(
  enabled: boolean,
  style: "light" | "medium" | "heavy" | "rigid" | "soft" = "light",
): void {
  if (!enabled) return;
  const tg = getTelegramWebApp();
  try {
    tg?.HapticFeedback?.impactOccurred?.(style);
  } catch {
    // ignore
  }
}

export function hapticSelection(enabled: boolean): void {
  if (!enabled) return;
  const tg = getTelegramWebApp();
  try {
    tg?.HapticFeedback?.selectionChanged?.();
  } catch {
    hapticImpact(enabled, "soft");
  }
}

export function hapticTap(enabled: boolean): void {
  hapticImpact(enabled, "light");
}

export function hapticSoft(enabled: boolean): void {
  hapticImpact(enabled, "soft");
}

export function hapticMedium(enabled: boolean): void {
  hapticImpact(enabled, "medium");
}

export function hapticSuccess(enabled: boolean): void {
  hapticNotify(enabled, "success");
}

export function hapticError(enabled: boolean): void {
  hapticNotify(enabled, "error");
}

export function hapticWarning(enabled: boolean): void {
  hapticNotify(enabled, "warning");
}

export function hapticNotify(
  enabled: boolean,
  kind: "success" | "error" | "warning",
): void {
  if (!enabled) return;
  const tg = getTelegramWebApp();
  try {
    tg?.HapticFeedback?.notificationOccurred?.(kind);
  } catch {
    // ignore
  }
}

export function isTelegramConfirmationTest(isDemo: boolean): boolean {
  return isDemo && Boolean(getTelegramWebApp()?.initData);
}

export async function telegramConfirm(
  title: string,
  message?: string,
  testMode = false,
): Promise<boolean> {
  const tg = getTelegramWebApp();
  if (testMode && tg?.initData &&
      (typeof tg.showConfirm === "function" || typeof tg.showPopup === "function")) {
    return new Promise<boolean>((resolve) => {
      const timer = setTimeout(() => resolve(false), 120_000);
      const settle = (approved: boolean) => {
        clearTimeout(timer);
        resolve(approved);
      };
      try {
        if (typeof tg.showConfirm === "function") {
          tg.showConfirm(message ? `${title}\n\n${message}` : title,
            (approved: unknown) => settle(approved === true));
        } else {
          tg.showPopup({
            title,
            message: message || "",
            buttons: [
              { id: "ok", type: "default", text: "OK" },
              { id: "cancel", type: "destructive", text: "Cancel" },
            ],
          }, (buttonId: unknown) => settle(buttonId === "ok"));
        }
      } catch {
        settle(false);
      }
    });
  }
  // Preserve the existing browser and non-TEST behavior.
  try {
    if (typeof tg?.showConfirm === "function") {
      const r = await tg.showConfirm(
        message ? `${title}\n\n${message}` : title,
      );
      return Boolean(r);
    }
  } catch {
    // ignore
  }
  try {
    if (typeof tg?.showPopup === "function") {
      return await new Promise<boolean>((resolve) => {
        tg.showPopup(
          {
            title,
            message: message || "",
            buttons: [
              { id: "ok", type: "default", text: "OK" },
              { id: "cancel", type: "destructive", text: "Cancel" },
            ],
          },
          (btnId: string) => resolve(btnId === "ok"),
        );
      });
    }
  } catch {
    // ignore
  }
  // Fallback.
  if (typeof window !== "undefined") {
    return window.confirm(message ? `${title}\n\n${message}` : title);
  }
  return false;
}

export function telegramAlert(title: string, message?: string): void {
  const tg = getTelegramWebApp();
  try {
    if (typeof tg?.showPopup === "function") {
      tg.showPopup({
        title,
        message: message || "",
        buttons: [{ id: "ok", type: "default", text: "OK" }],
      });
      return;
    }
  } catch {
    // ignore
  }
  try {
    if (typeof tg?.showAlert === "function") {
      tg.showAlert(message ? `${title}\n\n${message}` : title);
      return;
    }
  } catch {
    // ignore
  }
  if (typeof window !== "undefined") {
    window.alert(message ? `${title}\n\n${message}` : title);
  }
}

// BackButton helpers
export function telegramBackButtonShow(
  onClick: () => void,
): () => void {
  const tg = getTelegramWebApp();
  try {
    tg?.BackButton?.show?.();
  } catch {
    // ignore
  }
  try {
    tg?.BackButton?.onClick?.(onClick);
  } catch {
    // ignore
  }
  return () => {
    try {
      tg?.BackButton?.offClick?.(onClick);
    } catch {
      // ignore
    }
    try {
      tg?.BackButton?.hide?.();
    } catch {
      // ignore
    }
  };
}

// MainButton helpers
export type TelegramMainButtonOpts = {
  text: string;
  enabled?: boolean;
  color?: string;
  textColor?: string;
  show?: boolean;
};

export function telegramMainButtonSet(
  opts: TelegramMainButtonOpts,
): void {
  const tg = getTelegramWebApp();
  const mb = tg?.MainButton;
  if (!mb) return;
  try {
    if (typeof opts.text === "string" && opts.text.trim()) mb.setText?.(opts.text);
  } catch {
    // ignore
  }
  try {
    if (typeof opts.enabled === "boolean") {
      mb.setParams?.({ is_active: opts.enabled });
    }
  } catch {
    // ignore
  }
  try {
    if (opts.color || opts.textColor) {
      mb.setParams?.({
        color: opts.color,
        text_color: opts.textColor,
      });
    }
  } catch {
    // ignore
  }
  try {
    if (opts.show === false) mb.hide?.();
    if (opts.show === true) mb.show?.();
  } catch {
    // ignore
  }
}

export function telegramMainButtonOnClick(
  onClick: () => void,
): () => void {
  const tg = getTelegramWebApp();
  const mb = tg?.MainButton;
  try {
    mb?.onClick?.(onClick);
  } catch {
    // ignore
  }
  return () => {
    try {
      mb?.offClick?.(onClick);
    } catch {
      // ignore
    }
  };
}

// Open external link in Telegram (or fallback to window.open).
export function openTelegramLink(url: string): void {
  try {
    const tg = getTelegramWebApp();
    if (tg?.openLink) {
      tg.openLink(url);
      return;
    }
  } catch {
    // ignore
  }
  if (typeof window !== "undefined") {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

// ADS compatibility capability probe.
//
// ВАЖНО ДЛЯ БУДУЩИХ АУДИТОВ:
// исторически здесь предпринималась попытка вызвать неофициальные
// `tg.showAd` / `tg.AdController.show`. Эти методы не являются production
// provider contract EFHC и не входят в AdProviderRegistry. Удалять сам
// public helper нельзя без отдельного compatibility-решения, но возвращать
// через него rewarded flow или EFHCb запрещено. Если Telegram когда-либо
// опубликует официальный rewarded Mini Apps API, его подключение требует
// отдельного утверждённого adapter и документационного evidence.
export async function showTelegramAd(): Promise<"unsupported"> {
  return "unsupported";
}

// CloudStorage LOCK (MUST): UI-only cache.
// Allowed: onboarding, lastTab, filters, selected skin.
// Forbidden: balances, rights, VIP, panels, rates, amounts,
// and any operation status or financial state.

function _cloud_storage_key_allowed(key: string): boolean {
  const k = String(key || "").toLowerCase();
  const banned = [
    "balance",
    "main_balance",
    "available",
    "withdraw",
    "exchange",
    "wallet",
    "wallets",
    "address",
    "connected",
    "tonconnect",
  ];
  return !banned.some((b) => k.includes(b));
}

export async function telegramCloudStorageGet(
  key: string,
): Promise<string | null> {
  if (!_cloud_storage_key_allowed(key)) return null;
  const tg = getTelegramWebApp();
  // SDK object exists on ordinary webpages but CloudStorage is unsupported there.
  if (tg?.platform === "unknown" || tg?.platform === "web" && !tg?.initData) return null;
  const cs = tg?.CloudStorage;
  if (!cs?.getItem) return null;
  return await new Promise((resolve) => {
    try {
      cs.getItem(key, (err: any, value: any) => {
        if (err) return resolve(null);
        resolve(typeof value === "string" ? value : null);
      });
    } catch {
      resolve(null);
    }
  });
}

export async function telegramCloudStorageSet(
  key: string,
  value: string,
): Promise<boolean> {
  if (!_cloud_storage_key_allowed(key)) return false;
  const tg = getTelegramWebApp();
  if (tg?.platform === "unknown" || tg?.platform === "web" && !tg?.initData) return false;
  const cs = tg?.CloudStorage;
  if (!cs?.setItem) return false;
  return await new Promise((resolve) => {
    try {
      cs.setItem(key, value, (err: any) => resolve(!err));
    } catch {
      resolve(false);
    }
  });
}

export function getTelegramLang(): Lang | null {
  const u = getTelegramUser();
  return (u?.language_code || null) as any;
}

export function getTelegramColorScheme(): "light" | "dark" | null {
  const tg = getTelegramWebApp();
  try {
    const s = tg?.colorScheme;
    if (s === "light" || s === "dark") return s;
    return null;
  } catch {
    return null;
  }
}

export function onTelegramThemeChanged(cb: () => void): () => void {
  const tg = getTelegramWebApp();
  try {
    tg?.onEvent?.("themeChanged", cb);
    return () => {
      try {
        tg?.offEvent?.("themeChanged", cb);
      } catch {
        // ignore
      }
    };
  } catch {
    return () => undefined;
  }
}

export function onTelegramViewportChanged(cb: () => void): () => void {
  const tg = getTelegramWebApp();
  const handler = () => {
    applyTelegramCssVars();
    cb();
  };
  try {
    tg?.onEvent?.("viewportChanged", handler);
    return () => {
      try {
        tg?.offEvent?.("viewportChanged", handler);
      } catch {
        // ignore
      }
    };
  } catch {
    return () => undefined;
  }
}

// React hooks: Telegram WebApp integration.
// MUST NOT touch SSOT finance values.
export function useTelegramThemeSync(onApply: () => void): void {
  useEffect(() => {
    onApply();
    const offTheme = onTelegramThemeChanged(() => {
      onApply();
    });
    const offVp = onTelegramViewportChanged(() => {
      applyTelegramCssVars();
    });
    return () => {
      offTheme();
      offVp();
    };
  }, [onApply]);
}

export type TelegramButtonsState = {
  showBack?: boolean;
  onBack?: (() => void) | null;
  main?: TelegramMainButtonOpts | null;
  onMain?: (() => void) | null;
};

export function useTelegramButtons(state: TelegramButtonsState): void {
  useEffect(() => {
    let offBack: (() => void) | null = null;
    let offMain: (() => void) | null = null;
    let offTheme: (() => void) | null = null;

    if (state.showBack && state.onBack) {
      offBack = telegramBackButtonShow(state.onBack);
    }

    const applyMain = () => {
      if (!state.main) return;
      const tp = getTelegramWebApp()?.themeParams || {};
      const color = state.main.color || tp.button_color;
      const textColor = state.main.textColor || tp.button_text_color;
      telegramMainButtonSet({
        ...state.main,
        color: typeof color === "string" ? color : state.main.color,
        textColor:
          typeof textColor === "string"
            ? textColor
            : state.main.textColor,
      });
    };

    if (state.main) {
      applyMain();
      if (state.onMain) {
        offMain = telegramMainButtonOnClick(state.onMain);
      }

      offTheme = onTelegramThemeChanged(() => {
        applyMain();
      });
    } else {
      telegramMainButtonSet({ text: "", show: false });
    }

    return () => {
      try {
        offBack?.();
      } catch {
        // ignore
      }
      try {
        offMain?.();
      } catch {
        // ignore
      }
      try {
        offTheme?.();
      } catch {
        // ignore
      }
      telegramMainButtonSet({ text: "", show: false });
    };
  }, [
    state.showBack,
    state.onBack,
    state.onMain,
    state.main?.text,
    state.main?.enabled,
    state.main?.color,
    state.main?.textColor,
    state.main?.show,
  ]);
}
