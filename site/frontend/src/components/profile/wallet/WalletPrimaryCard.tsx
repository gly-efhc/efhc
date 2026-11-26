import React from "react";
import { useT } from "../../../hooks/useT";
import { WalletCardAction } from "./WalletCardAction";
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

      <div className="efhc-wallet-primary-actions standalone-wallet-actions">
        {props.onRemove ? (
          <WalletCardAction
            sizeLabel={t("wallet.primary_badge")}
            onClick={() => {
              hapticSoft(Boolean(props.hapticsEnabled));
              props.onRemove?.(wallet.id);
            }}
          >
            {t("wallet.remove")}
          </WalletCardAction>
        ) : null}
        <WalletCardAction
          sizeLabel={t("wallet.primary_badge")}
          status="wallet-primary-badge"
        >
          {t("wallet.primary_badge")}
        </WalletCardAction>
      </div>
    </div>
  );
}
