import React, { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import type { Dict, Lang } from "../lib/i18n";
import { tFromDicts } from "../lib/i18n";
import { CompactLanguagePicker } from "./profile/CompactLanguagePicker";
import type { UserSettings } from "../lib/settings";
import { LayoutContext } from "./Layout";
import { useBrowserShopProfile } from "../queries/useBrowserShop";
import { useAvatarPreference } from "../queries/useAvatarPreference";
import { UnifiedAvatar } from "./profile/UnifiedAvatar";

function ProfileIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M5.5 19c.7-4 2.85-5.9 6.5-5.9s5.8 1.9 6.5 5.9"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function ShopLayout(
  props: React.PropsWithChildren<{
    lang: Lang;
    uiDict: Dict;
    ruDict: Dict;
    descDict: Dict;
    telegramName: string;
    telegramAvatarUrl?: string | null;
    snapshot?: {
      profile: {
        username?: string | null;
        main_balance: string;
        bonus_balance: string;
      };
    } | null;
    isVip: boolean;
    isAdmin: boolean;
    settings: UserSettings;
    setLang: (l: Lang) => void;
    setSettings: (s: UserSettings) => void;
  }>,
) {
  const router = useRouter();
  const [shopToken, setShopToken] = useState("");
  const [shopTheme, setShopTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    let restored = fragment.get("token") || "";
    if (!restored) {
      try {
        restored = window.sessionStorage.getItem("efhc.browserShop.token.v1") || "";
      } catch {
        restored = "";
      }
    }
    setShopToken(restored);
    try {
      const savedTheme = window.localStorage.getItem("efhc.shop.theme.v1");
      setShopTheme(savedTheme === "light" ? "light" : "dark");
    } catch {
      setShopTheme("dark");
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try { window.localStorage.setItem("efhc.shop.theme.v1", shopTheme); } catch { /* no-op */ }
  }, [shopTheme]);

  const shopProfileQ = useBrowserShopProfile(shopToken);
  const shopLinkedGlobalId = shopProfileQ.data?.global_id || "";
  const t = useMemo(
    () => (key: string) => tFromDicts(key, props.uiDict, props.ruDict),
    [props.uiDict, props.ruDict],
  );
  const td = useMemo(
    () => (key: string) => props.descDict[key] || tFromDicts(key, props.uiDict, props.ruDict),
    [props.descDict, props.uiDict, props.ruDict],
  );
  const username = props.snapshot?.profile?.username
    || props.telegramName
    || (shopLinkedGlobalId ? `ID ${shopLinkedGlobalId}` : "EFHC");
  const { avatar } = useAvatarPreference();
  const avatarUrl = avatar.kind === "image" ? avatar.src : null;
  const mainBalance = props.snapshot?.profile?.main_balance || "0";
  const canonicalPath = ["/browser-shop", "/browser-shop/orders", "/browser-shop/profile"].includes(router.pathname)
    ? router.pathname
    : "/browser-shop";
  const canonicalTitle = router.pathname === "/browser-shop/orders"
    ? t("portal.browser_shop.nav_orders")
    : router.pathname === "/browser-shop/profile"
      ? t("portal.browser_shop.nav_profile")
      : t("portal.browser_shop.storefront_title");

  return (
    <LayoutContext.Provider
      value={{
        lang: props.lang,
        t,
        td,
        isVip: props.isVip,
        isAdmin: props.isAdmin,
        appMode: "user",
        settings: props.settings,
        setLang: props.setLang,
        setSettings: props.setSettings,
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
        telegramAvatarUrl: props.telegramAvatarUrl || null,
        avatarUrl,
        avatarEnergyVariant: avatar.kind === "icon" ? avatar.icon : null,
      }}
    >
      <div
        className="efhc-shop-site"
        data-interface-app-mode="shop-landing"
        data-browser-shop-document="canonical-external-vps-page"
        data-browser-shop-host-boundary="same-vps-separate-browser-document"
        data-browser-shop-application-shell="excluded"
        data-browser-shop-layout="standard-internet-landing"
        data-shop-theme={shopTheme}
        data-shop-theme-default="dark"
        data-shop-theme-storage="efhc.shop.theme.v1"
        data-browser-shop-canonical-route={canonicalPath}
      >
        <Head>
          <link rel="stylesheet" href={`${router.basePath}/SHOP_v866.css`} data-efhc-visual-authority="frozen-shop-v866" />
          <link rel="stylesheet" href={`${router.basePath}/frame-thickness-contract.css`} data-efhc-frame-width-contract="1px" />
          <title>{canonicalTitle}</title>
          <meta name="description" content={t("portal.browser_shop.subtitle")} />
          <link rel="canonical" href={`https://efhc.app${canonicalPath}`} />
        </Head>

        <header className="efhc-shop-site_header">
          <div className="efhc-shop-site_header-inner">
            <Link href={canonicalPath} className="efhc-shop-site_brand" aria-label="EFHC">
              <img src="/assets/efhc/efhc_coin_64.png" alt="" />
              <span><strong>EFHC</strong><small>Energy For Humanity</small></span>
            </Link>
            <nav className="efhc-shop-site_nav" aria-label={t("portal.browser_shop.storefront_title")} data-shop-quick-nav={canonicalPath === "/browser-shop" ? "visible" : "hidden"}>
              {canonicalPath === "/browser-shop" ? <>
                <a href="#packages">{t("portal.browser_shop.ready_packages_title")}</a>
                <a href="#vip">VIP NFT</a>
              </> : null}
            </nav>
            <div className="efhc-shop-site_tools">
              <button
                type="button"
                className="efhc-shop-theme-toggle"
                data-shop-theme-toggle="true"
                aria-label={t("portal.browser_shop.theme_toggle")}
                title={t("portal.browser_shop.theme_toggle")}
                onClick={() => setShopTheme((current) => current === "dark" ? "light" : "dark")}
              >
                {shopTheme === "dark" ? t("portal.browser_shop.theme_light") : t("portal.browser_shop.theme_dark")}
              </button>
              <div className="efhc-shop-site_balance">
                <small>EFHC</small>
                <strong>{mainBalance}</strong>
              </div>
              <Link href="/browser-shop/profile" className="efhc-shop-site_profile" aria-label={t("portal.browser_shop.nav_profile")}>
                <span className="efhc-shop-site_avatar">
                  <UnifiedAvatar value={avatar} size={36} alt="" />
                </span>
                <span className="efhc-shop-site_profile-copy">
                  <small>{shopLinkedGlobalId ? `Global ID ${shopLinkedGlobalId}` : t("profile.title")}</small>
                  <strong>{username}</strong>
                </span>
                <ProfileIcon />
              </Link>
              <div className="efhc-shop-site_language-picker" data-shop-language-picker="profile-style-flags-columns">
                <CompactLanguagePicker
                  value={props.lang}
                  label={t("profile.language_title")}
                  getLabel={(lang) => t(`profile.lang.${lang}`)}
                  onChange={props.setLang}
                />
              </div>
            </div>
          </div>
        </header>

        {props.children}

        <footer className="efhc-shop-site_footer">
          <div>
            <strong>EFHC · Energy For Humanity</strong>
            <span>{t("portal.browser_shop.payment_warning_detail")}</span>
          </div>
          <a href="#top">↑ EFHC</a>
        </footer>
      </div>
    </LayoutContext.Provider>
  );
}
