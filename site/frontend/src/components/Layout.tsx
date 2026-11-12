import React, { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthOwnerGlobalId, useAuthSessionController } from "../auth/AuthSessionProvider";
import type { Dict, Lang } from "../lib/i18n";
import { tFromDicts } from "../lib/i18n";
import type { UserSettings } from "../lib/settings";
import { DepositModal } from "./DepositModal";
import {
  getTelegramWebApp,
  hapticError,
  hapticSelection,
  hapticSuccess,
  hapticTap,
  telegramConfirm,
} from "../lib/telegram";
import {
  useWalletProvider,
  type PreparedWalletProof,
  type WalletConnectionPhase,
  type WalletView,
} from "../lib/wallet-provider";
import { InterfaceIndicators } from "./interface-settings/InterfaceIndicators";
import { GlobalHeader } from "./GlobalHeader";
import { AppNavIcon } from "./icons/AppNavIcon";
import { BrowserTelegramLogin } from "./BrowserTelegramLogin";
import { getUserLevel } from "../lib/skins";
import { useWalletsMe } from "../hooks/useWalletsMe";
import { queryKeys } from "../queries/queryKeys";
import {
  FrontendShellFrame,
  FrontendShellMain,
  FrontendShellRoot,
} from "./shell/FrontendShell";
import { NetworkStatus } from "./NetworkStatus";
import { GlobalThemeControl } from
  "./interface-settings/GlobalThemeControl";
import { InterfaceCustomizationButton } from
  "./interface-settings/InterfaceCustomizationButton";
import { useInterfaceCustomization } from
  "../hooks/useInterfaceCustomization";
import { useInterfaceVariantSurface } from
  "../hooks/useInterfaceVariantSurface";
import type { InterfaceAppMode, InterfaceVariantGroup } from
  "../types/interfaceCustomization";
import { useAvatarPreference } from "../queries/useAvatarPreference";
import { getThemePageDescriptor } from "../lib/themePageRegistry";
import { sameTonAddress } from "../lib/wallet-provider/primaryWalletRouting";
import { isDemoBackendMode } from "../demo/session";

export type LayoutContextValue = {
  lang: Lang;
  t: (k: string) => string;
  td: (k: string) => string;
  isVip: boolean;
  isAdmin: boolean;
  /** Presentation only; TEST API authorization remains server controlled. */
  canRenderAdminPage?: boolean;
  appMode: InterfaceAppMode;
  settings: UserSettings;
  setLang: (l: Lang) => void;
  setSettings: (s: UserSettings) => void;
  confirm: (
    kind:
      | "purchase"
      | "withdraw"
      | "convert"
      | "watch_ad"
      | "generic",
    title: string,
    detail?: string,
  ) => Promise<boolean>;
  toast: (msg: string, kind?: "success" | "error" | "info") => void;
  openProfile: (section?: "wallet" | "history") => void;
  openDeposit: () => void;
  openWalletConnect: (mode?: "binding" | "execution_fallback") => void;
  disconnectWalletSession: () => void;
  walletConnectionPhase: WalletConnectionPhase;
  walletHint: string | null;
  walletSessionConnected: boolean;
  walletSessionAddress: string | null;
  walletSessionRestoring: boolean;
  walletProofAccepted: boolean;
  availableWallets: WalletView[];
  telegramAvatarUrl: string | null;
  avatarUrl: string | null;
  avatarEnergyVariant: string | null;
};

export const LayoutContext = React.createContext<LayoutContextValue>({
  lang: "en",
  t: (k) => k,
  td: (k) => k,
  isVip: false,
  isAdmin: false,
  appMode: "user",
  settings: {
    lang: "en",
    theme_mode: "auto",
    avatar_source: "telegram",
    avatar_url: null,
    avatar_social_provider: null,
    avatar_social_url: null,
    sfx_enabled: true,
    music_enabled: true,
    sfx_volume: 0.6,
    sfx_pack: "default",
    haptics_enabled: true,
    reduce_motion: false,
    hide_balances: false,
    show_decimal_detail: false,
    interface_settings_version: 4,
    color_theme_id: "CT-01",
    global_theme_id: "01",
    theme_overrides: {},
    interface_variants: {
      SC: "SC-02", HB: "HB-01", HS: "HS-03", EG: "EG-01", BN: "BN-01", EI: "EI-07", PB: "PB-01", RP: "PB-01",
      PH: "PH-01", PT: "PT-01", PC: "PC-01", PA: "PA-01",
      XH: "XH-01", XS: "XS-01", XC: "XC-01", XA: "XA-01",
      TG: "TG-01", RG: "RG-01", KG: "KG-01", WG: "WG-01",
      HU: "HU-01", FQ: "FQ-01", PM: "PM-01", HI: "HI-01",
      WD: "WD-01", AD: "AD-01", BS: "BS-01", ER: "ER-01", AM: "AM-01",
    },
    confirm_actions: true,
    confirm_purchase: true,
    confirm_withdraw: true,
    confirm_convert: true,
    confirm_watch_ad: true,
    toasts_enabled: true,
    important_alerts_only: false,
  },
  setLang: () => undefined,
  setSettings: () => undefined,
  confirm: async () => true,
  toast: () => undefined,
  openProfile: () => undefined,
  openDeposit: () => undefined,
  openWalletConnect: () => undefined,
  disconnectWalletSession: () => undefined,
  walletConnectionPhase: "disconnected",
  walletHint: null,
  walletSessionConnected: false,
  walletSessionAddress: null,
  walletSessionRestoring: false,
  walletProofAccepted: false,
  availableWallets: [],
  telegramAvatarUrl: null,
  avatarUrl: null,
  avatarEnergyVariant: null,
});

function NavItem(props: {
  href: string;
  active: boolean;
  visualLabel: string;
  navKey: string;
  slot: number;
  icon: React.ReactNode;
  onNav: () => void;
}) {
  const stateCls = "text-[var(--tg-text)]";
  return (
    <Link
      href={props.href}
      aria-current={props.active ? "page" : undefined}
      aria-label={props.visualLabel}
      data-active={props.active ? "true" : "false"}
      data-nav-key={props.navKey}
      data-nav-slot={props.slot}
      title={props.visualLabel}
      onClick={(event) => {
        props.onNav();
        if (props.active && window.location.pathname === props.href) event.preventDefault();
      }}
      className={
        "flex flex-col items-center justify-center transition " +
        "text-xs font-semibold efhc-game-nav-button " +
        "efhc-game-nav_item " +
        stateCls
      }
    >
      <span className="efhc-game-nav_icon">{props.icon}</span>
      <span className="efhc-game-nav_label">{props.visualLabel}</span>
    </Link>
  );
}

export function Layout(
  props: React.PropsWithChildren<{
    lang: Lang;
    uiDict: Dict;
    ruDict: Dict;
    descDict: Dict;
    telegramProviderId: number | null;
    telegramName: string;
    telegramAvatarUrl?: string | null;
    snapshot?: {
      profile: {
        username?: string | null;
        is_vip?: boolean;
        has_activ?: boolean;
        main_balance: string;
        bonus_balance: string;
        total_generated_kwh: string;
      };
    } | null;
    isVip: boolean;
    isAdmin: boolean;
    settings: UserSettings;
    setLang: (l: Lang) => void;
    setSettings: (s: UserSettings) => void;
    shopSkinBgUrl?: string | null;
  }>,
) {
  const router = useRouter();
  const customization = useInterfaceCustomization();
  const navSurface = useInterfaceVariantSurface<HTMLDivElement>("BN");
  const t = useMemo(
    () => (k: string) => tFromDicts(k, props.uiDict, props.ruDict),
    [props.uiDict, props.ruDict],
  );
  const td = useMemo(
    () => (k: string) =>
      props.descDict[k] || tFromDicts(k, props.uiDict, props.ruDict),
    [props.descDict, props.uiDict, props.ruDict],
  );
  const [depositOpen, setDepositOpen] = useState(false);
  const [walletHint, setWalletHint] = useState<string | null>(null);
  const [availableWallets, setAvailableWallets] = useState<WalletView[]>([]);
  const [proofState, setProofState] = useState<
    PreparedWalletProof | null
  >(null);
  const [proofAccepted, setProofAccepted] = useState(false);
  const [connectionPhase, setConnectionPhase] = useState<
    WalletConnectionPhase
  >("restoring");
  const [walletModalOpened, setWalletModalOpened] = useState(false);
  const bindingAttemptRef = useRef("");
  const [toasts, setToasts] = useState<
    {
      id: string;
      msg: string;
      kind: "success" | "error" | "info";
      createdAt: number;
    }[]
  >([]);

  const globalId = useAuthOwnerGlobalId();
  const authSession = useAuthSessionController();
  // Public flags never grant Admin access. Protected API checks remain server-owned.
  const canRenderAdminPage = Boolean(props.isAdmin) || (
    isDemoBackendMode() && authSession.status === "authenticated" &&
    authSession.context?.roles.includes("test_visual") === true
  );
  const { avatar: resolvedAvatar } = useAvatarPreference();

  const qc = useQueryClient();
  const {
    activeAdapterId,
    session: walletSession,
    restoreSettled,
    modalOpened: providerModalOpened,
    listWallets,
    prepareProof,
    connect: connectWallet,
    bindWallet,
    disconnect: disconnectWallet,
    isUserRejected,
  } = useWalletProvider();
  const sessionConnected = Boolean(walletSession);
  const walletsMe = useWalletsMe();
  const boundSessionWallet = useMemo(
    () => (walletsMe.data?.wallets || []).find((wallet) => (
      wallet.is_active
      && wallet.proof_verified
      && sameTonAddress(wallet.wallet_address, walletSession?.address)
    )) || null,
    [walletSession?.address, walletsMe.data?.wallets],
  );
  const hasBoundWallet = Boolean(boundSessionWallet);
  const walletConnected = Boolean(walletsMe.data?.is_connected);
  const isAdminRoute = router.pathname.startsWith("/admin");
  const appMode: InterfaceAppMode = isAdminRoute ? "admin" : "user";
  const [bottomNavViewportHeight, setBottomNavViewportHeight] = useState<
    number | null
  >(null);
  const bottomNavElementRef = useRef<HTMLElement | null>(null);
  const themePage = getThemePageDescriptor(router.pathname);
  const shellBottomPadding = isAdminRoute
    ? "var(--efhc-safe-bottom)"
    // The measured nav height is already reserved by marginBottom below.
    // Keep only the content gap here, rather than reserving the nav twice.
    : "calc(.5rem + var(--efhc-pwa-floating-height, 0px))";

  useEffect(() => {
    if (isAdminRoute) {
      setBottomNavViewportHeight(null);
      return;
    }
    const nav = bottomNavElementRef.current;
    if (!nav) return;

    let animationFrame = 0;
    const syncBottomNavViewport = () => {
      cancelAnimationFrame(animationFrame);
      animationFrame = requestAnimationFrame(() => {
        const height = nav.getBoundingClientRect().height;
        if (height <= 0) return;
        const roundedHeight = Math.ceil(height * 100) / 100;
        setBottomNavViewportHeight((current) => (
          current !== null && Math.abs(current - roundedHeight) < 0.25
            ? current
            : roundedHeight
        ));
      });
    };

    syncBottomNavViewport();
    const observer = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(syncBottomNavViewport);
    observer?.observe(nav);
    window.addEventListener("resize", syncBottomNavViewport, { passive: true });
    return () => {
      cancelAnimationFrame(animationFrame);
      observer?.disconnect();
      window.removeEventListener("resize", syncBottomNavViewport);
    };
  }, [isAdminRoute]);
  const showBrowserTelegramLogin = process.env.NEXT_PUBLIC_EFHC_PAGES_PREVIEW !== "1" && !props.telegramProviderId &&
    router.pathname !== "/browser-shop" &&
    !isAdminRoute;

  const avatarUrl = resolvedAvatar.kind === "image" ? resolvedAvatar.src : null;
  const avatarEnergyVariant = resolvedAvatar.kind === "icon" ? resolvedAvatar.icon : null;
  const username =
    props.snapshot?.profile?.username || props.telegramName || "";
  const level = getUserLevel(
    props.snapshot?.profile?.total_generated_kwh || "0",
  );

  useEffect(() => {
    if (!restoreSettled) {
      setConnectionPhase("restoring");
      return;
    }
    if (!walletSession) {
      bindingAttemptRef.current = "";
      setConnectionPhase("disconnected");
      setProofAccepted(false);
      return;
    }
    if (hasBoundWallet) {
      setConnectionPhase("connected");
      setProofAccepted(true);
      setWalletHint(t("wallet.session_restored"));
      return;
    }
    // A connected wallet is not an authenticated, verified account wallet.
    // Keep wallet discovery available while the server proof is unavailable.
    setConnectionPhase("connected");
    setProofAccepted(false);
    setWalletHint(t("wallet.restore_requires_proof"));
  }, [hasBoundWallet, restoreSettled, t, walletSession]);

  useEffect(() => {
    setWalletModalOpened(providerModalOpened);
  }, [providerModalOpened]);

  useEffect(() => {
    listWallets()
      .then(setAvailableWallets)
      .catch(() => setAvailableWallets([]));
  }, [activeAdapterId, listWallets]);

  // Acquire TON Proof only for the explicit wallet connection action below.
  // Background refreshes while a wallet is connecting would replace its
  // challenge and make the signed envelope fail server verification.

  useEffect(() => {
    if (
      !walletSession
      || !proofState
      || hasBoundWallet
      || walletsMe.isLoading
    ) {
      return;
    }
    const proofKey = String(
      (proofState.value as { payload_token?: unknown } | null)
        ?.payload_token ?? "proof",
    );
    const attemptKey = [
      activeAdapterId,
      walletSession.address,
      proofKey,
    ].join(":");
    if (bindingAttemptRef.current === attemptKey) return;
    bindingAttemptRef.current = attemptKey;

    if (globalId) {
      qc.invalidateQueries({
        queryKey: queryKeys.profile.wallets(globalId),
      }).catch(() => undefined);
    }
    setConnectionPhase("verifying");
    setWalletHint(t("wallet.proof_verifying"));
    bindWallet(proofState)
      .then((bound) => {
        if (!bound?.is_connected) {
          setConnectionPhase("error");
          setWalletHint(t("wallet.restore_requires_proof"));
          return;
        }
        setWalletModalOpened(false);
        restoreTelegramMainButtonAfterWalletModal();
        setProofAccepted(true);
        setConnectionPhase("connected");
        setWalletHint(t("wallet.proof_received"));
        toast(t("wallet.proof_received"), "success");
        if (globalId) {
          qc.invalidateQueries({
            queryKey: queryKeys.profile.wallets(globalId),
          }).catch(() => undefined);
        }
      })
      .catch(() => {
        setConnectionPhase("error");
        setWalletHint(t("wallet.proof_failed"));
      });
  }, [
    activeAdapterId,
    bindWallet,
    hasBoundWallet,
    proofState,
    props.telegramProviderId,
    qc,
    t,
    walletSession,
    walletsMe.isLoading,
  ]);

  useEffect(() => {
    if (walletModalOpened) {
      hideTelegramMainButtonForWalletModal();
      return;
    }
    restoreTelegramMainButtonAfterWalletModal();
  }, [depositOpen, walletModalOpened]);


  function toast(
    msg: string,
    kind: "success" | "error" | "info" = "info",
  ) {
    if (!props.settings.toasts_enabled) return;
    if (kind === "success") {
      hapticSuccess(props.settings.haptics_enabled);
    }
    if (kind === "error") hapticError(props.settings.haptics_enabled);
    const createdAt = Date.now();
    const id = `${createdAt}:${Math.random().toString(16).slice(2)}`;
    setToasts((prev) => {
      const duplicate = prev.some(
        (item) =>
          item.msg === msg &&
          item.kind === kind &&
          createdAt - item.createdAt < 2500,
      );
      if (duplicate) return prev;
      return [...prev, { id, msg, kind, createdAt }].slice(-3);
    });
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, 3200);
  }

  async function confirm(
    kind:
      | "purchase"
      | "withdraw"
      | "convert"
      | "watch_ad"
      | "generic",
    title: string,
    detail?: string,
  ): Promise<boolean> {
    if (!props.settings.confirm_actions) return true;
    const gate = {
      purchase: props.settings.confirm_purchase,
      withdraw: props.settings.confirm_withdraw,
      convert: props.settings.confirm_convert,
      watch_ad: props.settings.confirm_watch_ad,
      generic: true,
    }[kind];
    if (!gate) return true;
    return await telegramConfirm(title, detail);
  }

  const bottom = [
    {
      href: "/",
      key: "nav.energy",
      visualLabel: "Energy",
      kind: "energy" as const,
    },
    {
      href: "/panels",
      key: "nav.panels",
      visualLabel: "Panels",
      kind: "panels" as const,
    },
    {
      href: "/exchange",
      key: "nav.exchange",
      visualLabel: "Exchange",
      kind: "exchange" as const,
    },
    {
      href: "/tasks",
      key: "nav.tasks",
      visualLabel: "Tasks",
      kind: "tasks" as const,
    },
    {
      href: "/referrals",
      key: "nav.referrals",
      visualLabel: "Referrals",
      kind: "referrals" as const,
    },
    {
      href: "/ranks",
      key: "nav.ranks",
      visualLabel: "Ranks",
      kind: "ranks" as const,
    },
  ];

  const onTap = (kind: "tap" | "nav") => {
    if (props.settings.sfx_enabled) {
      void import("../lib/sfx").then(({ playSfx }) => {
        playSfx(
          kind,
          props.settings.sfx_enabled,
          props.settings.sfx_volume,
        );
      });
    }
    if (kind === "nav") {
      hapticSelection(props.settings.haptics_enabled);
      return;
    }
    hapticTap(props.settings.haptics_enabled);
  };

  function hideTelegramMainButtonForWalletModal() {
    try {
      getTelegramWebApp()?.MainButton?.hide?.();
    } catch {
      // noop
    }
  }

  function restoreTelegramMainButtonAfterWalletModal() {
    try {
      if (!depositOpen) return;
      getTelegramWebApp()?.MainButton?.show?.();
    } catch {
      // noop
    }
  }

  function openProfile(section?: "wallet" | "history") {
    const query = section ? { section } : undefined;
    void router.push({ pathname: "/web-profile", query });
  }

  async function openWalletConnect(mode: "binding" | "execution_fallback" = "binding") {
    hideTelegramMainButtonForWalletModal();
    setWalletModalOpened(true);
    setConnectionPhase("connecting");
    setWalletHint(t("wallet.connection_waiting"));
    const prepared = mode === "binding"
      ? await prepareProof().catch(() => null)
      : null;
    setProofState(prepared);
    if (mode === "binding" && !prepared) {
      // Binding requires a fresh server-issued TON Proof challenge. Never
      // offer a wallet connection that cannot be verified by the backend.
      setWalletModalOpened(false);
      restoreTelegramMainButtonAfterWalletModal();
      setConnectionPhase("error");
      setWalletHint(t("wallet.restore_requires_proof"));
      return;
    }
    // Connection and cryptographic owner verification remain separate.
    // The official TonConnect UI owns wallet selection and return/deep links.
    setWalletHint(prepared
      ? t("wallet.proof_ready")
      : mode === "binding"
        ? t("wallet.restore_requires_proof")
        : t("wallet.connection_ready"));
    try {
      await connectWallet();
      // openModal resolves when opened, not when a wallet is connected.
      // React hooks + backend TON Proof determine connection state.
    } catch (error) {
      setWalletModalOpened(false);
      restoreTelegramMainButtonAfterWalletModal();
      setConnectionPhase(isUserRejected(error) ? "rejected" : "error");
      const key = isUserRejected(error)
        ? "wallet.connection_rejected" : "wallet.connection_failed";
      setWalletHint(t(key));
      toast(t(key), isUserRejected(error) ? "info" : "error");
    }
  }

  async function disconnectWalletSession() {
    await disconnectWallet().catch(() => undefined);
    if (globalId) {
      qc.invalidateQueries({
        queryKey: queryKeys.profile.wallets(globalId),
      }).catch(() => undefined);
    }
    setProofAccepted(false);
    setConnectionPhase("disconnected");
    setWalletHint(t("wallet.session_disconnected"));
    toast(t("wallet.session_disconnected"), "info");
  }

  function openDeposit() {
    setDepositOpen(true);
  }

  return (
    <LayoutContext.Provider
      value={{
        lang: props.lang,
        t,
        td,
        isVip: props.isVip,
        isAdmin: props.isAdmin,
        canRenderAdminPage,
        appMode,
        settings: props.settings,
        setLang: props.setLang,
        setSettings: props.setSettings,
        confirm,
        toast,
        openProfile,
        openDeposit,
        openWalletConnect: (mode) => {
          void openWalletConnect(mode);
        },
        disconnectWalletSession: () => {
          void disconnectWalletSession();
        },
        walletConnectionPhase: connectionPhase,
        walletHint,
        walletSessionConnected: sessionConnected,
        walletSessionAddress: walletSession?.address ?? null,
        walletSessionRestoring: !restoreSettled,
        walletProofAccepted: proofAccepted,
        availableWallets,
        telegramAvatarUrl: props.telegramAvatarUrl || null,
        avatarUrl,
        avatarEnergyVariant,
      }}
    >
      <FrontendShellRoot
        data-tma-shell-polish="viewport-theme-backbutton-safe-area"
        data-public-shell-route={isAdminRoute ? "admin" : "public"}
        data-interface-app-mode={appMode}
        data-efhc-source-styles={appMode === "user" ? "true" : undefined}
        data-interface-customization-mode={customization.mode}
        data-global-theme-id={isAdminRoute ? undefined : customization.globalThemeId}
        data-color-theme-id={isAdminRoute ? undefined : customization.colorThemeId}
        data-theme-chroma-canon={isAdminRoute ? undefined : "theme-03-tonal"}
        data-theme-page-surface="true"
        data-theme-page-marker={themePage.marker}
        data-theme-page-route={router.pathname}
        data-theme-page-groups={themePage.groups.join(",")}
        data-public-color-system={
          isAdminRoute ? undefined : "soft-muted"
        }
        data-public-ui-polish={
          isAdminRoute ? undefined : "route-harmony"
        }
        className={
          "bg-[var(--tg-bg)] efhc-shell efhc-game-shell " +
          "efhc-independent-shell efhc-tma-shell"
        }
        onClickCapture={customization.blockNonCustomizationInteraction}
        onSubmitCapture={customization.blockNonCustomizationInteraction}
        style={{
          height: "var(--tg-viewport-height)",
          minHeight: 0,
          paddingBottom: 0,
        }}
      >
        <a className="efhc-skip-link" href="#efhc-main-content">
          {t("onboarding.skip")}
        </a>
        <NetworkStatus t={t} />
        <FrontendShellFrame className="efhc-independent-shell_frame">
        <GlobalHeader
          username={username}
          avatarUrl={avatarUrl}
          avatarEnergyVariant={avatarEnergyVariant}
          avatar={resolvedAvatar}
          level={level}
          isVip={props.snapshot?.profile?.is_vip || props.isVip}
          hasActiv={props.snapshot?.profile?.has_activ || false}
          mainBalance={props.snapshot?.profile?.main_balance || "0"}
          bonusBalance={props.snapshot?.profile?.bonus_balance || "0"}
          walletConnected={walletConnected}
          appMode={appMode}
          onAvatar={() => {
            onTap("tap");
            openProfile();
          }}
          onDeposit={() => openDeposit()}
          onOpenWallet={() => {
            void openWalletConnect();
          }}
        />


        {!isAdminRoute && <InterfaceIndicators
          pageGroup={themePage.groups.find(group => group !== "HS" && group !== "BN") as InterfaceVariantGroup | undefined}
        />}

        <FrontendShellMain
          id="efhc-main-content"
          tabIndex={-1}
          className="efhc-main efhc-game-shell_main"
          data-user-bottom-nav-boundary={
            isAdminRoute ? undefined : "shared-layout"
          }
          style={{
            marginBottom: isAdminRoute
              ? undefined
              : bottomNavViewportHeight === null
                ? "var(--efhc-user-bottom-nav-viewport-reserve)"
                : `${bottomNavViewportHeight}px`,
            paddingBottom: shellBottomPadding,
            scrollPaddingBottom: isAdminRoute
              ? undefined
              : "var(--efhc-user-bottom-nav-boundary)",
          }}
        >
          {showBrowserTelegramLogin ? <BrowserTelegramLogin t={t} /> : null}
          {isAdminRoute && !canRenderAdminPage ? (
            <section aria-label="Admin access required" data-admin-access="denied" style={{maxWidth:640,margin:"24px auto",padding:20}}>
              <h1>EFHC Admin</h1>
              <p>Доступ к административным страницам закрыт. Для временного просмотра войдите по ключу.</p>
              <Link href="/dev/neon/">Ввести ключ просмотра Admin</Link>
            </section>
          ) : props.children}
        </FrontendShellMain>
        </FrontendShellFrame>

        {!isAdminRoute && (
          <nav
            ref={bottomNavElementRef}
            data-regression-nav-canon="v888"
            className={
              "fixed bottom-0 left-0 right-0 z-30 " +
              "efhc-nav efhc-game-nav"
            }
            style={{ paddingBottom: "var(--efhc-safe-bottom)" }}
          >
            <div className="efhc-game-nav_inner">
              <div
                ref={navSurface.ref}
                {...navSurface.handlers}
                className={
                  "efhc-pill efhc-game-nav_grid"
                }
                data-bn={navSurface.variant}
                data-global-static-nav="true"
                data-nav-geometry="wide-rounded-six"
                data-nav-icon-system="rounded-outline-v2"
                data-nav-language-policy="english-fixed"
              >
                {bottom.map((item, index) => (
                  <NavItem
                    key={item.key}
                    href={item.href}
                    active={
                      item.href === "/"
                        ? router.pathname === "/"
                        : router.pathname === item.href ||
                          router.pathname.startsWith(`${item.href}/`)
                    }
                    visualLabel={item.visualLabel}
                    navKey={item.key}
                    slot={index + 1}
                    icon={<AppNavIcon kind={item.kind} />}
                    onNav={() => onTap("nav")}
                  />
                ))}
              </div>
            </div>
          </nav>
        )}

        <div
          className="efhc-customization-control-dock"
          data-regression-dock-canon="v888"
          data-has-bottom-nav={!isAdminRoute ? "true" : "false"}
          style={{
            bottom: !isAdminRoute && bottomNavViewportHeight !== null
              ? `${bottomNavViewportHeight + 9}px`
              : undefined,
          }}
          data-user-floating-boundary={
            isAdminRoute ? undefined : "shared-shell"
          }
        >
          {!isAdminRoute ? <GlobalThemeControl /> : null}
          <InterfaceCustomizationButton hasBottomNav={!isAdminRoute} />
        </div>

        {toasts.length ? (
          <div
            className={
              "fixed left-0 right-0 bottom-24 z-40 " +
              "pointer-events-none"
            }
          >
            <div className="max-w-xl mx-auto px-4 grid gap-2">
              {toasts.map((item) => (
                <div
                  key={item.id}
                  role={item.kind === "error" ? "alert" : "status"}
                  aria-live={item.kind === "error" ? "assertive" : "polite"}
                  aria-atomic="true"
                  className={
                    "pointer-events-none rounded-2xl px-4 py-3 " +
                    "text-sm backdrop-blur " +
                    "bg-[var(--tg-secondary-bg)] " +
                    "text-[var(--tg-text)] border " +
                    "border-[color:var(--tg-hint)]"
                  }
                >
                  {item.msg}
                </div>
              ))}
            </div>
          </div>
        ) : null}


        <DepositModal
          open={depositOpen}
          onClose={() => setDepositOpen(false)}
        />
      </FrontendShellRoot>
    </LayoutContext.Provider>
  );
}
