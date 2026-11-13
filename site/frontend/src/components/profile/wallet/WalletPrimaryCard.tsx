import React from "react";
import { useT } from "../../../hooks/useT";
import { TelegramStatusBadge } from "../../ui/telegram/TelegramStatusBadge";
import { Button } from "../../ui/Button";
import { hapticSoft } from "../../../lib/telegram";
import type { WalletListItemModel } from "./WalletListItem";
import type { DbId } from "../../../types/db-id";
import { WalletAddressVerification } from "./WalletAddressVerification";

type Props = {
  wallet: WalletListItemModel | null;
  sessionOwned: boolean;
  onRemove?: (id: DbId) => void;
  hapticsEnabled?: boolean;
};

export function WalletPrimaryCard(props: Props) {
  const t = useT();
  if (!props.wallet) return null;

  const wallet = props.wallet;

  return (
    <div
      className="efhc-wallet-entry"
      data-wallet-role="primary"
      data-wallet-id={String(wallet.id)}
      data-wallet-session-owned={props.sessionOwned ? "true" : "false"}
    >
      <WalletAddressVerification address={wallet.wallet_address} />

      {props.onRemove ? (
        <div className="efhc-wallet-primary-actions standalone-wallet-actions">
          <Button
            variant="secondary"
            className="source-button secondary"
            onClick={() => {
              hapticSoft(Boolean(props.hapticsEnabled));
              props.onRemove?.(wallet.id);
            }}
          >
            {t("wallet.remove")}
          </Button>
        </div>
      ) : null}

      <div className="efhc-wallet-status-zone efhc-wallet-primary-status">
        <TelegramStatusBadge
          label={t("wallet.primary_badge")}
          tone="primary"
          dataStatus="wallet-primary-badge"
        />
      </div>
    </div>
  );
}
