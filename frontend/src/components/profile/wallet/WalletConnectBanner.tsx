import React from "react";
import { useT } from "../../../hooks/useT";
import type {
  WalletConnectionPhase,
} from "../../../lib/wallet-provider";
import { Button } from "../../ui/Button";
import {
  hapticSelection,
  hapticSoft,
} from "../../../lib/telegram";

type Props = {
  connected: boolean;
  restoring: boolean;
  proofAccepted: boolean;
  connectionPhase: WalletConnectionPhase;
  walletHint?: string | null;
  onConnect: () => void;
  onDisconnectSession: () => void;
  hapticsEnabled: boolean;
  hasLinkedWallet: boolean;
};

function phaseLabel(
  phase: WalletConnectionPhase,
  t: (key: string) => string,
): string {
  const key = `wallet.phase_${phase}`;
  return t(key);
}

export function WalletConnectBanner(props: Props) {
  const t = useT();
  const busy = [
    "restoring",
    "connecting",
    "verifying",
  ].includes(props.connectionPhase);

  if (!props.connected) {
    return (
      <Button
        className="w-full efhc-wallet-connect-cta"
        data-linked-wallets={props.hasLinkedWallet ? "present" : "empty"}
        disabled={busy}
        data-wallet-provider-action="connect"
        data-wallet-provider-phase={props.connectionPhase}
        data-wallet-provider-ux="restore-proof-reject"
        data-tonconnect-action="connect"
        data-tonconnect-phase={props.connectionPhase}
        data-tonconnect-wallet-ux="restore-proof-reject"
        onClick={() => {
          hapticSelection(props.hapticsEnabled);
          props.onConnect();
        }}
      >
        {busy
          ? t("wallet.connection_waiting")
          : t("wallet.connect_button")}
      </Button>
    );
  }

  const title = t("wallet.session_connected");
  const desc = props.restoring
    ? t("wallet.session_restoring")
    : t("wallet.connection_ready");

  return (
    <div
      className="efhc-wallet-card"
      data-wallet-provider-phase={props.connectionPhase}
      data-wallet-provider-ux="restore-proof-reject"
      data-tonconnect-phase={props.connectionPhase}
      data-tonconnect-wallet-ux="restore-proof-reject"
    >
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="efhc-wallet-card_title">{title}</div>
        <div className="efhc-wallet-card_desc">{desc}</div>
        <div
          className={
            "efhc-tonconnect-phase "
            + `is-${props.connectionPhase}`
          }
          role="status"
          aria-live="polite"
        >
          <span aria-hidden="true" />
          {phaseLabel(props.connectionPhase, t)}
        </div>
        {props.proofAccepted ? (
          <div className="text-xs text-[color:var(--tg-hint)]">
            {t("wallet.proof_received")}
          </div>
        ) : null}
        {props.walletHint ? (
          <div className="text-xs text-[color:var(--tg-hint)]">
            {props.walletHint}
          </div>
        ) : null}
      </div>
      <div className="efhc-wallet-card_actions">
        <Button
          variant="secondary"
          onClick={() => {
            hapticSoft(props.hapticsEnabled);
            props.onDisconnectSession();
          }}
        >
          {t("wallet.disconnect_session")}
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            hapticSelection(props.hapticsEnabled);
            window.location.assign(
              "/faq?section=5&subsection=5.1",
            );
          }}
        >
          {t("wallet.faq_button")}
        </Button>
      </div>
    </div>
  );
}
