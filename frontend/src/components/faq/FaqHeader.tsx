import React from "react";
import { TelegramInfoBlock } from "../ui/telegram/TelegramInfoBlock";

type Props = {
  title: string;
  subtitle: string;
  scope: string;
};

export function FaqHeader(props: Props) {
  return (
    <section className="efhc-energy-hero space-y-3 p-4">
      <div>
        <div className="text-2xl font-bold">{props.title}</div>
        <div className="mt-1 text-sm efhc-text-muted2">
          {props.subtitle}
        </div>
      </div>
      <TelegramInfoBlock>{props.scope}</TelegramInfoBlock>
    </section>
  );
}
