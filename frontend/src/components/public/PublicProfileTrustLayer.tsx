import React, { useMemo, useState } from "react";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { useT } from "../../hooks/useT";
import { hapticSelection } from "../../lib/telegram";

type TrustTab = "profile" | "wallet" | "history";

type PublicProfileTrustLayerProps = {
  username: string;
  level: number;
  isVip: boolean;
  isActive: boolean;
  totalBalance: string;
  mainBalance: string;
  bonusBalance: string;
  walletCount: number;
  walletConnected: boolean;
  primaryWallet: string | null;
  historyCount: number;
  withdrawCount: number;
  latestWithdrawStatus: string | null;
  hideBalances: boolean;
  hapticsEnabled?: boolean;
  onOpenWallet: () => void;
  onOpenHistory: () => void;
  onOpenFaq: () => void;
};

type TrustRow = {
  label: string;
  value: string;
};

function mask(value: string, hidden: boolean): string {
  if (!hidden) return value;
  return "••••";
}

function shortAddress(address: string | null): string {
  if (!address) return "—";
  if (address.length <= 18) return address;
  return `${address.slice(0, 8)}…${address.slice(-8)}`;
}

export function PublicProfileTrustLayer(
  props: PublicProfileTrustLayerProps,
) {
  const t = useT();
  const [tab, setTab] = useState<TrustTab>("profile");
  const selectTab = (next: TrustTab) => {
    hapticSelection(Boolean(props.hapticsEnabled));
    setTab(next);
  };

  const rows = useMemo<TrustRow[]>(() => {
    if (tab === "wallet") {
      return [
        {
          label: t("public_profile_trust.wallet_count"),
          value: String(props.walletCount),
        },
        {
          label: t("public_profile_trust.wallet_state"),
          value: props.walletConnected
            ? t("public_profile_trust.wallet_connected")
            : t("public_profile_trust.wallet_not_connected"),
        },
        {
          label: t("public_profile_trust.primary_wallet"),
          value: shortAddress(props.primaryWallet),
        },
      ];
    }
    if (tab === "history") {
      return [
        {
          label: t("public_profile_trust.history_items"),
          value: String(props.historyCount),
        },
        {
          label: t("public_profile_trust.withdraw_items"),
          value: String(props.withdrawCount),
        },
        {
          label: t("public_profile_trust.latest_withdraw"),
          value: props.latestWithdrawStatus || "—",
        },
      ];
    }
    return [
      {
        label: t("public_profile_trust.total_balance"),
        value: mask(props.totalBalance, props.hideBalances),
      },
      {
        label: t("public_profile_trust.main_balance"),
        value: mask(props.mainBalance, props.hideBalances),
      },
      {
        label: t("public_profile_trust.bonus_balance"),
        value: mask(props.bonusBalance, props.hideBalances),
      },
    ];
  }, [props, tab, t]);

  const action = tab === "wallet"
    ? props.onOpenWallet
    : tab === "history"
      ? props.onOpenHistory
      : props.onOpenFaq;
  const actionLabel = tab === "wallet"
    ? t("public_profile_trust.cta_wallet")
    : tab === "history"
      ? t("public_profile_trust.cta_history")
      : t("public_profile_trust.cta_faq");

  return (
    <section
      className="efhc-public-trust"
      data-public-profile-trust-layer="1351"
      data-public-profile-visual-trust-layer="profile-wallet-history"
      data-public-no-admin-diagnostics="true"
      data-public-no-raw-payload="true"
    >
      <div className="efhc-public-trust_head">
        <div>
          <div className="efhc-public-trust_kicker">
            {t("public_profile_trust.kicker")}
          </div>
          <h2 className="efhc-public-trust_title">
            {t("public_profile_trust.title")}
          </h2>
        </div>
        <Badge>{t("public_profile_trust.safe_badge")}</Badge>
      </div>

      <p className="efhc-public-trust_detail">
        {t("public_profile_trust.detail")}
      </p>

      <div className="efhc-public-trust_hero">
        <div className="efhc-public-trust_avatar" aria-hidden="true">
          ⚡
        </div>
        <div className="min-w-0">
          <strong>{props.username}</strong>
          <span><span data-i18n-fixed-token="Lvl">Lvl</span> {props.level}</span>
        </div>
        <div className="efhc-public-trust_badges">
          <span className={props.isVip ? "is-on" : "is-off"}>
            {t("profile.vip_badge")}
          </span>
          <span className={props.isActive ? "is-on" : "is-off"}>
            {t("profile.active_badge")}
          </span>
        </div>
      </div>

      <div
        className="efhc-public-trust_visual-rail"
        data-public-profile-visual-rail="profile-wallet-history"
      >
        <span className="efhc-public-trust_visual-chip">
          {t("public_profile_trust.flow_profile")}
        </span>
        <span className="efhc-public-trust_visual-chip">
          {t("public_profile_trust.flow_wallet")}
        </span>
        <span className="efhc-public-trust_visual-chip">
          {t("public_profile_trust.flow_history")}
        </span>
      </div>

      <div className="efhc-public-trust_tabs" role="tablist">
        {(["profile", "wallet", "history"] as TrustTab[]).map((item) => (
          <button
            key={item}
            className={
              "efhc-public-trust_tab " +
              (tab === item ? "is-active" : "")
            }
            data-public-profile-trust-tab={item}
            onClick={() => selectTab(item)}
            type="button"
          >
            {t(`public_profile_trust.tab_${item}`)}
          </button>
        ))}
      </div>

      <div className="efhc-public-trust_flow" aria-hidden="true">
        <svg viewBox="0 0 320 92" role="img">
          <path
            d="M42 48 C90 18 120 74 164 48 S232 18 278 48"
            fill="none"
            stroke="currentColor"
            strokeDasharray="7 8"
            strokeWidth="3"
          />
          {[42, 164, 278].map((cx, index) => (
            <g key={cx}>
              <circle cx={cx} cy="48" r="18" />
              <text x={cx} y="53" textAnchor="middle">
                {index + 1}
              </text>
            </g>
          ))}
        </svg>
        <div className="efhc-public-trust_flow-labels">
          <span>{t("public_profile_trust.flow_profile")}</span>
          <span>{t("public_profile_trust.flow_wallet")}</span>
          <span>{t("public_profile_trust.flow_history")}</span>
        </div>
      </div>

      <div className="efhc-public-trust_rows">
        {rows.map((row) => (
          <div className="efhc-public-trust_row" key={row.label}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>

      <div className="efhc-public-trust_note">
        {t(`public_profile_trust.note_${tab}`)}
      </div>

      <Button
        className="w-full"
        onClick={() => {
          hapticSelection(Boolean(props.hapticsEnabled));
          action();
        }}
      >
        {actionLabel}
      </Button>
    </section>
  );
}
