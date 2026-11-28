import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import type { Dict, Lang } from "../lib/i18n";
import { tFromDicts } from "../lib/i18n";
import { CompactLanguagePicker } from "./profile/CompactLanguagePicker";
import type { UserSettings } from "../lib/settings";
import { LayoutContext } from "./Layout";
import { useAvatarPreference } from "../queries/useAvatarPreference";

const SHOP_THEME_KEY = "efhc.shop.theme.v1";
const useBeforePaintEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

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
  const topRef = useRef<HTMLDivElement>(null);
  const scrollShopToTop = () => {
    const top = topRef.current;
    if (!top) return;
    top.focus({ preventScroll: true });
    if (typeof top.scrollIntoView === "function") {
      top.scrollIntoView({ block: "start", inline: "nearest", behavior: "instant" });
    } else {
      window.scrollTo(0, 0);
    }
  };
  const [shopTheme, setShopTheme] = useState<"dark" | "light">("dark");
  const [shopThemeReady, setShopThemeReady] = useState(false);
  useBeforePaintEffect(() => {
    try {
      setShopTheme(window.localStorage.getItem(SHOP_THEME_KEY) === "light" ? "light" : "dark");
    } catch { /* Dark is the existing default when storage is unavailable. */ }
    setShopThemeReady(true);
  }, []);

  useBeforePaintEffect(() => {
    // The frozen CSS themes both the external Shop document canvas and the
    // React wrapper. Only this Shop layout owns the document attribute.
    document.documentElement.dataset.shopTheme = shopTheme;
    return () => { delete document.documentElement.dataset.shopTheme; };
  }, [shopTheme]);

  useEffect(() => {
    if (!shopThemeReady) return;
    try { window.localStorage.setItem(SHOP_THEME_KEY, shopTheme); } catch { /* no-op */ }
  }, [shopTheme, shopThemeReady]);

  const t = useMemo(
    () => (key: string) => tFromDicts(key, props.uiDict, props.ruDict),
    [props.uiDict, props.ruDict],
  );
  const td = useMemo(
    () => (key: string) => props.descDict[key] || tFromDicts(key, props.uiDict, props.ruDict),
    [props.descDict, props.uiDict, props.ruDict],
  );
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
        id="top"
        ref={topRef}
        tabIndex={-1}
        className="efhc-shop-site"
        data-interface-app-mode="shop-landing"
        data-browser-shop-document="canonical-external-vps-page"
        data-browser-shop-host-boundary="same-vps-separate-browser-document"
        data-browser-shop-application-shell="excluded"
        data-browser-shop-layout="standard-internet-landing"
        data-shop-theme={shopTheme}
        data-shop-theme-default="dark"
        data-shop-theme-storage={SHOP_THEME_KEY}
        data-browser-shop-canonical-route={canonicalPath}
      >
        <Head>
          <link rel="stylesheet" href={`${router.basePath}/SHOP_v866.css`} data-efhc-visual-authority="frozen-shop-v866" />
          <link rel="stylesheet" href={`${router.basePath}/frame-thickness-contract.css`} data-efhc-frame-width-contract="1px" />
          <link rel="stylesheet" href={`${router.basePath}/browser-shop-light.css`} />
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
            <strong>EFHC · Energy For Humanity Coin</strong>
          </div>
          <button type="button" className="efhc-shop-site_back-top" onClick={scrollShopToTop} aria-label={t("portal.browser_shop.back_to_top")}>↑</button>
        </footer>

        <style jsx>{`
          .efhc-shop-site_footer {
            padding-inline: clamp(.875rem, 3vw, 1.375rem);
          }
          .efhc-shop-site_footer > div {
            min-inline-size: 0;
            overflow-wrap: anywhere;
          }
          .efhc-shop-site_footer .efhc-shop-site_back-top {
            display: grid;
            place-items: center;
            inline-size: 2.75rem;
            min-block-size: 2.75rem;
            flex: none;
            border: 1px solid var(--shop-line);
            border-radius: .72rem;
            background: transparent;
            color: var(--shop-ink);
            cursor: pointer;
            padding: 0;
            line-height: 1;
            font-size: 1rem;
          }
          .efhc-shop-site_back-top:focus-visible {
            outline: 2px solid currentColor;
            outline-offset: 3px;
          }
          @media (prefers-reduced-motion: reduce) {
            :global(html[data-shop-theme]) { scroll-behavior: auto; }
          }
        `}</style>
      </div>
    </LayoutContext.Provider>
  );
}
