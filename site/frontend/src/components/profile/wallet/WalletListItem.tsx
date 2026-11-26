import React from "react";
import { useT } from "../../../hooks/useT";
import { WalletCardAction } from "./WalletCardAction";
import { hapticSelection, hapticSoft } from "../../../lib/telegram";
import type { DbId } from "../../../types/db-id";
import { WalletAddressVerification } from "./WalletAddressVerification";

export type WalletListItemModel = {
  id: DbId;
  wallet_address: string;
  wallet_app: string | null;
  is_primary: boolean;
  is_active: boolean;
  proof_verified?: boolean;
  is_project_test?: boolean;
  created_at: string;
};

type Props = {
  wallet: WalletListItemModel;
  sessionOwned: boolean;
  onMakePrimary: (id: DbId) => void;
  onRemove: (id: DbId) => void;
  hapticsEnabled: boolean;
};

export function WalletListItem(props: Props) {
  const t = useT();
  const { wallet } = props;

  return (
    <div
      className="efhc-wallet-entry"
      data-wallet-role={wallet.is_primary ? "primary" : "additional"}
      data-wallet-id={String(wallet.id)}
      data-wallet-session-owned={props.sessionOwned ? "true" : "false"}
    >
      <div className="efhc-wallet-item_actions standalone-wallet-actions">
        <WalletCardAction
          sizeLabel={t("wallet.primary_badge")}
          disabled={!wallet.is_active || wallet.is_primary}
          onClick={() => {
            hapticSelection(props.hapticsEnabled);
            props.onMakePrimary(wallet.id);
          }}
        >
          {t("wallet.make_primary")}
        </WalletCardAction>
        <WalletCardAction
          sizeLabel={t("wallet.primary_badge")}
          onClick={() => {
            hapticSoft(props.hapticsEnabled);
            props.onRemove(wallet.id);
          }}
        >
          {t("wallet.remove")}
        </WalletCardAction>
      </div>
      <WalletAddressVerification address={wallet.wallet_address} />
    </div>
  );
}
