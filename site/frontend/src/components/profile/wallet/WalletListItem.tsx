import React from "react";
import { useT } from "../../../hooks/useT";
import { Button } from "../../ui/Button";
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
      <WalletAddressVerification address={wallet.wallet_address} />

      <div className="efhc-wallet-item_actions">
        <Button
          variant="secondary"
          disabled={!wallet.is_active || wallet.is_primary}
          onClick={() => {
            hapticSelection(props.hapticsEnabled);
            props.onMakePrimary(wallet.id);
          }}
        >
          {t("wallet.make_primary")}
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            hapticSoft(props.hapticsEnabled);
            props.onRemove(wallet.id);
          }}
        >
          {t("wallet.remove")}
        </Button>
      </div>
    </div>
  );
}
