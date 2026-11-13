import React from "react";
import { GameHero, GamePageShell, GameSection } from "./ui/GameShell";

type Translator = (key: string) => string;

const ROUTE_TITLES: Record<string, string> = {
  "": "energy.title",
  app: "energy.title",
  withdraw: "withdraw.title",
  exchange: "exchange.title",
  panels: "panels.title",
  portfolio: "panels.title",
  referrals: "referrals.title",
  ranks: "ranks.title",
  tasks: "tasks.title",
  hub: "hub.title",
  faq: "faq.title",
  "web-profile": "profile.title",
  "browser-shop": "shop.title",
};

/** A read-only, existing-design page shell, never a fatal error dialog.
 * Rendering failures must not execute a pending financial mutation.
 */
export function QuietPageSurface({pathname, t}: {pathname: string; t: Translator}) {
  const parts = pathname.split("/").filter(Boolean);
  const route = parts[parts.length - 1] || "";
  const withdrawing = route === "withdraw";
  const label = t(ROUTE_TITLES[route] || "common.loading");
  return (
    <GamePageShell
      className={withdrawing ? "efhc-withdraw-trust-shell efhc-withdraw-shell" : ""}
      data-page-recovery="read-only"
      data-recovery-route={route || "home"}
    >
      <GameHero
        className={withdrawing ? "efhc-withdraw-hero" : undefined}
        title={label}
        kicker={withdrawing ? t("withdraw.standalone_kicker") : undefined}
        detail={withdrawing ? t("withdraw.min_hint") : undefined}
      >
        {withdrawing ? (
          <div className="efhc-withdraw-summary-list">
            <div className="efhc-withdraw-summary-row">
              <span className="efhc-withdraw-summary-label">{t("withdraw.available_to_withdraw")}</span>
              <strong className="efhc-withdraw-summary-value efhc-financial-number">— EFHCm</strong>
            </div>
            <div className="efhc-withdraw-summary-row">
              <span className="efhc-withdraw-summary-label">{t("wallet.primary_wallet")}</span>
              <strong className="efhc-withdraw-summary-value">—</strong>
            </div>
          </div>
        ) : null}
      </GameHero>
      {withdrawing ? (
        <>
          <GameSection className="efhc-withdraw-create-card efhc-withdraw-action-card" title={t("withdraw.new_request")}>
            <div className="efhc-exchange-panel efhc-withdraw-create-card_body">
              <label className="efhc-exchange-input-group">
                <span>{t("withdraw.efhc_amount")}</span>
                <input type="text" value="" readOnly disabled aria-label={t("withdraw.efhc_amount")} />
              </label>
              <button type="button" disabled>{t("withdraw.create_request")}</button>
            </div>
          </GameSection>
          <GameSection className="efhc-withdraw-requests-history" title={t("withdraw.my_requests")} />
        </>
      ) : <GameSection />}
    </GamePageShell>
  );
}
