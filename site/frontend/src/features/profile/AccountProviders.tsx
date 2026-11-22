/** Provider state comes from the auth session and verified server wallet list. */
import React, { useContext, useState } from "react";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { useAuthSessionController } from "../../auth/AuthSessionProvider";
import { isDemoGuestSession } from "../../demo/session";
import { LayoutContext } from "../../components/Layout";
import { openTelegramApp } from "../../components/BrowserTelegramLogin";
import { getTelegramInitData } from "../../lib/telegram";
import { accountProviderLabels } from "./account-provider-labels";
import styles from "./account-providers.module.css";

type Props = {
  hasVerifiedWallet: boolean;
  walletStatusPending: boolean;
  walletStatusUnavailable: boolean;
  walletActionPending: boolean;
  onOpenWallet: () => void;
  onConnectWallet: () => void;
};

export function AccountProviders(props: Props): React.JSX.Element {
  const { lang, t } = useContext(LayoutContext);
  const connectLabel = accountProviderLabels["profile.provider_connect_action"][lang];
  const auth = useAuthSessionController();
  const [message, setMessage] = useState("");

  const context = auth.status === "authenticated" ? auth.context : null;
  const isGuest = !context || isDemoGuestSession() || /guest|visual/i.test(context.provider || "");
  const isLinked = Boolean(context && !isGuest);
  const telegramVerified = isLinked && context?.provider === "telegram";
  const providersPending = auth.status === "authenticating" || auth.status === "restoring";
  const providerActionClass = "source-button secondary efhc-provider-action";

  function connectTelegram() {
    if (providersPending || isLinked) return;
    setMessage("");
    if (!getTelegramInitData()) {
      openTelegramApp();
      return;
    }
    void auth.loginTelegram().catch(() => setMessage(t("common.action_not_available_now")));
  }

  return (
    <div className="grid gap-3 efhc-account-providers" data-provider-state-source="server-session" data-provider-auth-state={isLinked ? "verified" : "guest"}>
      <h2 className={`source-card-title ${styles.panelTitle}`}>{t(isLinked ? "profile.linked_accounts_action" : "profile.sign_in_action")}</h2>
      <Card className="efhc-profile-action-card efhc-account-provider-card p-3">
        <div className={styles.providerRow} data-provider-row="telegram">
          <div className={`min-w-0 ${styles.providerCopy}`}>
            <div className="font-semibold">Telegram</div>
            <p className="text-xs efhc-text-muted2" data-provider="telegram" data-provider-state={telegramVerified ? "verified" : "unverified"}>
              {telegramVerified
                ? t("wallet.state_connected")
                : isLinked
                  ? t("common.action_not_available_now")
                  : t("wallet.state_not_connected")}
            </p>
          </div>
          {!isLinked ? (
            <Button type="button" variant="secondary" className={providerActionClass}
              data-provider-action="connect" disabled={providersPending} onClick={connectTelegram}>
              {connectLabel}
            </Button>
          ) : null}
        </div>
      </Card>

      <Card className="efhc-profile-action-card efhc-account-provider-card p-3">
        <div className={styles.providerRow} data-provider-row="ton-connect">
          <div className={`min-w-0 ${styles.providerCopy}`}>
            <div className="font-semibold">TON Connect</div>
            <p className="text-xs efhc-text-muted2" data-provider="ton-connect" data-provider-state={props.hasVerifiedWallet ? "verified" : "unverified"}>
              {props.hasVerifiedWallet ? t("wallet.state_bound") : props.walletStatusPending
                ? t("wallet.connection_waiting") : props.walletStatusUnavailable
                  ? t("wallet.error_title") : t("wallet.state_not_connected")}
            </p>
          </div>
          <Button type="button" variant="secondary" className={providerActionClass}
            data-provider-open-wallet="official-ton-connect"
            data-provider-action={props.hasVerifiedWallet ? "view" : isLinked ? "bind" : "connect"}
            disabled={providersPending || props.walletActionPending}
            onClick={props.hasVerifiedWallet ? props.onOpenWallet : props.onConnectWallet}>
            {props.hasVerifiedWallet ? t("wallet.title") : connectLabel}
          </Button>
        </div>
      </Card>
      {message ? <p role="status" className="text-xs efhc-text-muted2">{message}</p> : null}
    </div>
  );
}
