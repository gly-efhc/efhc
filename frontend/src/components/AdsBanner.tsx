import React from "react";
import Link from "next/link";
import { useT } from "../hooks/useT";
import { Card } from "./ui/Card";
import { TelegramInfoBlock } from "./ui/telegram/TelegramInfoBlock";

type Props = {
  href?: string;
  title?: string;
  detail?: string;
};

export function AdsBanner(props: Props) {
  const t = useT();
  const href = props.href || "/tasks";
  return (
    <Card title={props.title || t("ads.title")}>
      <div className="space-y-3">
        <TelegramInfoBlock title={t("ads.no_campaigns_title")}>
          {props.detail || t("ads.no_campaigns_detail")}
        </TelegramInfoBlock>
        <Link className="efhc-link text-sm" href={href}>
          {t("ads.open_tasks")}
        </Link>
      </div>
    </Card>
  );
}
