import React from "react";
import { useT } from "../../../hooks/useT";
import { Button } from "../Button";
import { TelegramBadgeGroup } from "./TelegramBadgeGroup";
import { TelegramStatusBadge } from "./TelegramStatusBadge";

export function TelegramProductCard(props: {
  title: string;
  description: string;
  price: string;
  secondaryPrice?: string;
  imageUrl?: string | null;
  badges?: Array<{ label: string; tone?: "primary" | "neutral" | "connected" | "warning" | "vip" }>;
  active?: boolean;
  disabled?: boolean;
  onSelect?: () => void;
  onPrimary?: () => void;
  primaryLabel: string;
}) {
  const t = useT();
  return (
    <div
      className={[
        "rounded-3xl border p-4 transition",
        props.active
          ? "border-[var(--tg-link)]/40 bg-[var(--tg-link)]/5"
          : "border-[color:var(--tg-hint)]/20 bg-[var(--tg-secondary-bg)]",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{props.title}</div>
          <div className="mt-1 text-sm text-[color:var(--tg-hint)]">{props.description}</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <TelegramStatusBadge label={props.price} tone="primary" />
          {props.secondaryPrice ? (
            <TelegramStatusBadge label={props.secondaryPrice} tone="neutral" />
          ) : null}
        </div>
      </div>
      <div className="mt-3 overflow-hidden rounded-2xl border border-[color:var(--tg-hint)]/15 bg-[var(--tg-bg)] text-xs text-[color:var(--tg-hint)]">
        {props.imageUrl ? (
          <img
            src={props.imageUrl}
            alt={props.title}
            className="aspect-square w-full object-cover"
            onError={(event) => {
              const image = event.currentTarget;
              if (image.dataset.fallback === "true") return;
              image.dataset.fallback = "true";
              image.src = "/assets/efhc/efhc_coin_256.png";
            }}
          />
        ) : (
          <div className="grid aspect-square place-items-center p-3">{t("common.image_placeholder")}</div>
        )}
      </div>
      {props.badges?.length ? (
        <div className="mt-3">
          <TelegramBadgeGroup>
            {props.badges.map((badge) => (
              <TelegramStatusBadge key={badge.label} label={badge.label} tone={badge.tone || "neutral"} />
            ))}
          </TelegramBadgeGroup>
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        {props.onSelect ? (
          <Button variant="secondary" onClick={props.onSelect} disabled={props.disabled}>
            {t("common.details")}
          </Button>
        ) : null}
        <Button onClick={props.onPrimary} disabled={props.disabled}>
          {props.primaryLabel}
        </Button>
      </div>
    </div>
  );
}
