import React, {
  memo,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/router";
import { useT } from "../hooks/useT";
import { useInterfaceVariantSurface } from
  "../hooks/useInterfaceVariantSurface";
import { StatusIndicator } from "./StatusIndicator";
import { resolveHeaderThemeComposition } from "../lib/headerThemeComposition";
import { EfhcCoinIcon } from "./icons/EfhcCoin";
import { EnergyVariantIcon } from "./icons/EnergyVariantIcon";
import { UnifiedAvatar } from "./profile/UnifiedAvatar";
import type { ResolvedAvatar } from "../lib/avatarPreference";
import { sumScaledDown } from "../lib/format";
import type { InterfaceAppMode } from
  "../types/interfaceCustomization";

type Props = {
  username: string;
  avatarUrl: string | null;
  avatar?: ResolvedAvatar;
  avatarEnergyVariant?: string | null;
  level: number;
  isVip: boolean;
  hasActiv: boolean;
  mainBalance: string;
  bonusBalance: string;
  walletConnected: boolean;
  appMode: InterfaceAppMode;
  onAvatar: () => void;
  onDeposit: () => void;
  onOpenWallet: () => void;
};

function HeaderActionIcon(props: {
  kind: "faq" | "wallet" | "deposit" | "hub";
}) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.9,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (props.kind === "faq") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" />
        <path d="M9.8 9a2.4 2.4 0 1 1 3.7 2c-1 .6-1.5 1.1-1.5 2" />
        <path d="M12 17h.01" />
      </svg>
    );
  }
  if (props.kind === "wallet") {
    return (
      <svg {...common}>
        <path d="M4 7.5h13.5A2.5 2.5 0 0 1 20 10v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7.5Z" />
        <path d="M4 8V6a2 2 0 0 1 2-2h10" />
        <path d="M15 12h5v4h-5a2 2 0 0 1 0-4Z" />
      </svg>
    );
  }
  if (props.kind === "deposit") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v8M8 12h8" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <rect x="4" y="4" width="6" height="6" rx="1.5" />
      <rect x="14" y="4" width="6" height="6" rx="1.5" />
      <rect x="4" y="14" width="6" height="6" rx="1.5" />
      <rect x="14" y="14" width="6" height="6" rx="1.5" />
    </svg>
  );
}

function clampLevel(n: number): number {
  if (!Number.isFinite(n)) return 1;
  return Math.min(12, Math.max(1, Math.floor(n)));
}

function useMeasuredBalanceFont(value: string) {
  const containerRef = useRef<HTMLButtonElement | null>(null);
  const valueRef = useRef<HTMLSpanElement | null>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    const valueNode = valueRef.current;
    if (!container || !valueNode || typeof window === "undefined") return;

    let frame = 0;
    const fit = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const style = window.getComputedStyle(container);
        const icon = container.querySelector("svg") as SVGElement | null;
        const padding =
          (Number.parseFloat(style.paddingLeft) || 0)
          + (Number.parseFloat(style.paddingRight) || 0);
        const gap = Number.parseFloat(style.columnGap || style.gap) || 0;
        const iconWidth = icon?.getBoundingClientRect().width || 0;
        const available = Math.max(
          1,
          container.clientWidth - padding - iconWidth - gap - 1,
        );

        valueNode.style.transition = "none";
        valueNode.style.transform = "none";
        valueNode.style.width = "auto";
        valueNode.style.marginInline = "0";
        valueNode.style.flex = "0 0 auto";

        const measureAt = (fontSize: number) => {
          container.style.setProperty(
            "--efhc-header-balance-fit-size",
            `${fontSize.toFixed(2)}px`,
          );
          return valueNode.getBoundingClientRect().width;
        };

        const minimumFontPx = 11;
        const maximumFontPx = 13;
        let low = minimumFontPx;
        let high = maximumFontPx;
        let best = minimumFontPx;
        let minimumWidth = measureAt(minimumFontPx);

        if (minimumWidth <= available) {
          for (let step = 0; step < 8; step += 1) {
            const mid = (low + high) / 2;
            const measuredWidth = measureAt(mid);
            if (measuredWidth <= available) {
              best = mid;
              low = mid;
            } else {
              high = mid;
            }
          }
          const finalWidth = measureAt(best);
          valueNode.style.width = `${finalWidth.toFixed(2)}px`;
          valueNode.style.marginInline = "0";
          valueNode.style.transform = "none";
          container.dataset.headerBalanceScaleX = "1.000";
        } else {
          best = minimumFontPx;
          minimumWidth = measureAt(minimumFontPx);
          const scaleX = Math.max(0.78, Math.min(1, available / minimumWidth));
          const visualWidth = minimumWidth * scaleX;
          const compensation = (minimumWidth - visualWidth) / 2;
          valueNode.style.width = `${minimumWidth.toFixed(2)}px`;
          valueNode.style.marginInline = `-${compensation.toFixed(2)}px`;
          valueNode.style.transform = `scaleX(${scaleX.toFixed(4)})`;
          container.dataset.headerBalanceScaleX = scaleX.toFixed(3);
        }

        container.style.setProperty(
          "--efhc-header-balance-fit-size",
          `${best.toFixed(2)}px`,
        );
        container.dataset.headerBalanceFontPx = best.toFixed(2);
        window.dispatchEvent(new CustomEvent("efhc:balance-scale-metrics", {
          detail: {
            value,
            fontPx: best,
            scaleX: Number(container.dataset.headerBalanceScaleX || "1"),
            availablePx: available,
          },
        }));
      });
    };

    fit();
    const observer = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(fit)
      : null;
    observer?.observe(container);
    if (document.fonts?.ready) {
      void document.fonts.ready.then(fit).catch(() => undefined);
    }
    return () => {
      observer?.disconnect();
      window.cancelAnimationFrame(frame);
    };
  }, [value]);

  return { containerRef, valueRef };
}

const BALANCE_SCALE_TEST_VALUES = Object.freeze([
  "1.00000000",
  "1234.56789012",
  "12345678.12345678",
]);

export const GlobalHeader = memo(function GlobalHeader(props: Props) {
  const router = useRouter();
  const t = useT();
  const [balanceScaleTestIndex, setBalanceScaleTestIndex] = useState(-1);
  const lvl = clampLevel(props.level);
  const headerThemeSurface = useInterfaceVariantSurface<HTMLDivElement>(
    "HS",
    { dotsPlacement: "above", interactive: true },
  );
  const headerThemeVariant = props.appMode === "admin"
    ? "HS-03"
    : headerThemeSurface.selection;
  const headerComposition = resolveHeaderThemeComposition(headerThemeVariant);

  const total = useMemo(
    () => sumScaledDown(props.mainBalance, props.bonusBalance, 8),
    [props.mainBalance, props.bonusBalance],
  );

  useEffect(() => {
    const onTest = (event: Event) => {
      const detail = (event as CustomEvent<{ index?: number }>).detail;
      const requested = Number(detail?.index);
      setBalanceScaleTestIndex(
        Number.isInteger(requested)
          && requested >= -1
          && requested < BALANCE_SCALE_TEST_VALUES.length
          ? requested
          : -1,
      );
    };
    window.addEventListener("efhc:balance-scale-test", onTest);
    return () => window.removeEventListener("efhc:balance-scale-test", onTest);
  }, []);

  const displayedTotal = balanceScaleTestIndex >= 0
    ? BALANCE_SCALE_TEST_VALUES[balanceScaleTestIndex] || total
    : total;
  const balanceFit = useMeasuredBalanceFont(displayedTotal);

  // OWNER 2026-10-30: Admin entry belongs in Profile, NEVER in Header.
  // RBAC and DEMO preview routing are owned by Profile/_app and are unchanged.
  const username = props.username || "TG";
  const balanceDensity =
    displayedTotal.length >= 19
      ? "very-dense"
      : displayedTotal.length >= 15
        ? "dense"
        : displayedTotal.length >= 12
          ? "compact"
          : "normal";

  const onHub = () => {
    router.push("/hub").catch(() => undefined);
  };

  const onFaq = () => {
    router.push("/faq").catch(() => undefined);
  };

  const onDepositClick = () => {
    props.onDeposit();
  };

  return (
    <div className="sticky top-0 z-40 w-full efhc-header-divider">
      <div
        ref={headerThemeSurface.ref}
        {...headerThemeSurface.handlers}
        className="efhc-game-header"
        data-hs={headerComposition.shell}
        data-header-theme-variant={headerThemeVariant}
        data-canon-header="true"
        data-header-theme-owner="global-theme-plus-individual-override"
        data-header-shell-source={headerComposition.shell}
      >
        {/* DOM hierarchy restored from frozen FRONTEND_v866.html:
            container > avatar button + copy > name button + statuses.
            Preserve the same onAvatar action on both controls. */}
        <div
          className="efhc-game-header_profile"
          data-profile-layout="username-then-lvl-activ-vip"
        >
          <button
            type="button"
            className="efhc-game-header_profile-avatar-button"
            onClick={props.onAvatar}
            aria-label={t("profile.menu_button")}
          >
            <span className="efhc-game-header_avatar">
              {props.avatar ? (
                <UnifiedAvatar value={props.avatar} size={36} alt="" />
              ) : props.avatarUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={props.avatarUrl}
                  alt=""
                  className="h-full w-full object-cover"
                  referrerPolicy="no-referrer"
                />
              ) : props.avatarEnergyVariant && (process.env.NEXT_PUBLIC_EFHC_PAGES_PREVIEW !== "1" || process.env.NEXT_PUBLIC_EFHC_DATA_SOURCE === "demo_backend") ? (
                <span className="efhc-game-header_avatar-energy" aria-hidden="true">
                  <span className="efhc-energy-stage_coin" data-ei={props.avatarEnergyVariant}>
                    <EnergyVariantIcon variant={props.avatarEnergyVariant} size={22} />
                  </span>
                </span>
              ) : (
                <span className="efhc-game-header_avatar-canon-fallback" aria-hidden="true">
                  <svg width="30" height="30" viewBox="0 0 36 36" fill="none">
                    <circle cx="18" cy="12.2" r="7.1" fill="currentColor" />
                    <path d="M4.1 32c1.5-8.8 6.5-12.7 13.9-12.7S30.4 23.2 31.9 32" fill="currentColor" />
                  </svg>
                </span>
              )}
            </span>
          </button>
          <div className="efhc-game-header_profile-copy">
            <button
              type="button"
              className="efhc-game-header_profile-name-button"
              onClick={props.onAvatar}
              title={username}
              aria-label={t("profile.menu_button")}
            >
              <span className="profile-name">
                {username}
              </span>
            </button>
            <div
              className="efhc-game-header_statuses efhc-status-indicator-context"
              data-sc={headerComposition.statuses}
              data-header-theme-owned="statuses"
              aria-label="User level and statuses"
            >
              <span className="level-label" data-i18n-fixed-token="Lvl">
                Lvl {lvl}
              </span>
              <StatusIndicator
                kind="activ"
                active={props.hasActiv}
                label={t("profile.activ_badge")}
              />
              <StatusIndicator
                kind="vip"
                active={props.isVip}
                label={t("profile.vip_badge")}
              />
            </div>
          </div>
        </div>

        <button
          type="button"
          ref={balanceFit.containerRef}
          className="efhc-game-header_balance"
          data-header-balance-navigation="/web-profile?section=history"
          onClick={() => { void router.push("/web-profile?section=history"); }}
          aria-label={t("common.efhc_balance_aria")}
          title={displayedTotal}
          data-balance-scope="global-header"
          data-energy-balance-boundary="header-only"
          data-header-balance-label="EFHC"
          data-header-balance-source="EFHCm-plus-EFHCb"
          data-header-balance-layout="single-line"
          data-header-balance-density={balanceDensity}
          data-hb={headerComposition.balance}
          data-header-theme-owned="balance"
        >
          <EfhcCoinIcon size={16} />
          <span
            ref={balanceFit.valueRef}
            className="efhc-game-header_balance-value"
            data-header-balance-value={displayedTotal}
            data-header-balance-test={balanceScaleTestIndex >= 0 ? "true" : "false"}
          >
            {displayedTotal}
          </span>
        </button>

        <div
          className="efhc-game-header_actions"
          data-header-action-layout="balanced-grid"
          data-action-count="4"
          data-admin-entry-owner="profile-only"
        >
          <button
            type="button"
            onClick={onFaq}
            className="efhc-header-action efhc-btn-secondary"
            data-action="FAQ"
            aria-label={t("faq.title")}
            title={t("faq.title")}
          >
            <HeaderActionIcon kind="faq" />
            <span>{t("faq.title")}</span>
          </button>
          <button
            type="button"
            onClick={props.onOpenWallet}
            className="efhc-header-action efhc-btn-secondary"
            data-action="Wallet"
            aria-label={t("wallet.title")}
            title={t("wallet.title")}
          >
            <HeaderActionIcon kind="wallet" />
            <span>{t("wallet.title")}</span>
          </button>
          <button
            type="button"
            onClick={onDepositClick}
            className="efhc-header-action efhc-btn-secondary"
            data-action="Deposit"
            aria-label={t("deposit.direct_title")}
            title={t("deposit.direct_title")}
          >
            <HeaderActionIcon kind="deposit" />
            <span>+ EFHC</span>
          </button>
          <button
            type="button"
            onClick={onHub}
            className="efhc-header-action efhc-btn-primary"
            data-action="HUB"
            aria-label="Hub"
            title="Hub"
            data-i18n-fixed-token="Hub"
          >
            <HeaderActionIcon kind="hub" />
            <span>HUB</span>
          </button>
        </div>
      </div>
    </div>
  );
});

/* WalletGate action marker: Пополнить */
