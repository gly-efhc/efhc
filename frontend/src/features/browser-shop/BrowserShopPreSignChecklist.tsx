import React from "react";

import { useT } from "../../hooks/useT";

type Props = {
  asset: "TON" | "USDT";
  amount: string;
  ready: boolean;
};

export function BrowserShopPreSignChecklist(props: Props) {
  const t = useT();
  return (
    <div
      className="efhc-browser-shop-presign"
      data-browser-shop-presign="asset-network-recipient-amount"
    >
      <strong>{t("portal.browser_shop.presign_title")}</strong>
      <ul>
        <li>
          <span>{t("portal.browser_shop.presign_asset")}</span>
          <b>{props.asset}</b>
        </li>
        <li>
          <span>{t("portal.browser_shop.presign_network")}</span>
          <b>TON</b>
        </li>
        <li>
          <span>{t("portal.browser_shop.presign_recipient")}</span>
          <b>{t("portal.browser_shop.presign_official_recipient")}</b>
        </li>
        <li>
          <span>{t("portal.browser_shop.presign_amount")}</span>
          <b>{props.amount}</b>
        </li>
      </ul>
      <small>
        {props.ready
          ? t("portal.browser_shop.presign_ready")
          : t("portal.browser_shop.presign_connect")}
      </small>
    </div>
  );
}
