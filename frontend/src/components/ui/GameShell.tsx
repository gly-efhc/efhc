import React from "react";

import { Button } from "./Button";

type HeroProps = React.PropsWithChildren<
  React.HTMLAttributes<HTMLElement> & {
    kicker?: string;
    title: string;
    detail?: string;
    icon?: React.ReactNode;
    right?: React.ReactNode;
  }
>;

type GamePageShellProps = React.PropsWithChildren<
  React.HTMLAttributes<HTMLDivElement> & { className?: string }
>;

export const GamePageShell = React.forwardRef<
  HTMLDivElement,
  GamePageShellProps
>(function GamePageShell(props, ref) {
  const { children, className, ...rest } = props;
  return (
    <div
      {...rest}
      ref={ref}
      data-canon-template="v866"
      className={`efhc-game-page ${className || ""}`}
    >
      {children}
    </div>
  );
});

export const GameHero = React.forwardRef<HTMLElement, HeroProps>(
  function GameHero(props, ref) {
    const {
      kicker,
      title,
      detail,
      icon,
      right,
      children,
      className,
      ...rest
    } = props;
    return (
      <section
        {...rest}
        ref={ref}
        data-canon-frame="source-game-hero"
        className={`efhc-game-hero ${className || ""}`}
      >
        <div className="efhc-game-hero_glow" aria-hidden="true" />
        <div className="efhc-game-hero_content">
          <div className="efhc-game-hero_head">
            <div className="min-w-0">
              {kicker ? (
                <div className="efhc-game-kicker">
                  {kicker}
                </div>
              ) : null}
              <h1 className="efhc-game-title">{title}</h1>
              {detail ? (
                <p className="efhc-game-detail">{detail}</p>
              ) : null}
            </div>
            {icon || right ? (
              <div className="efhc-game-hero_side">
                {icon ? (
                  <div className="efhc-game-hero_icon">
                    {icon}
                  </div>
                ) : null}
                {right}
              </div>
            ) : null}
          </div>
          {children ? (
            <div className="efhc-game-hero_body">
              {children}
            </div>
          ) : null}
        </div>
      </section>
    );
  },
);

export function GameStatsGrid(
  props: React.PropsWithChildren<{ compact?: boolean }>,
) {
  return (
    <div
      data-canon-frame="source-stats"
      className={
        props.compact ? "efhc-game-stats compact" : "efhc-game-stats"
      }
    >
      {props.children}
    </div>
  );
}

export function GameStat(props: {
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
}) {
  return (
    <div className="efhc-game-stat" data-canon-frame="source-stat">
      <div className="efhc-game-stat_label">{props.label}</div>
      <div className="efhc-game-stat_value">{props.value}</div>
      {props.note ? (
        <div className="efhc-game-stat_note">{props.note}</div>
      ) : null}
    </div>
  );
}

export function GameSection(
  props: React.PropsWithChildren<
    React.HTMLAttributes<HTMLElement> & {
      title?: string;
      className?: string;
    }
  >,
) {
  const { title, className, children, ...rest } = props;
  return (
    <section
      {...rest}
      data-canon-frame="source-card"
      className={`efhc-game-section ${className || ""}`}
    >
      {title ? (
        <div className="efhc-game-section_title">
          {title}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function GameNotice(props: {
  title: string;
  detail?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="efhc-game-notice" data-canon-frame="source-notice">
      <div className="efhc-game-notice_title">{props.title}</div>
      {props.detail ? (
        <div className="efhc-game-notice_detail">
          {props.detail}
        </div>
      ) : null}
      {props.actionLabel && props.onAction ? (
        <div className="mt-3">
          <Button onClick={props.onAction}>
            {props.actionLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function GameActionCard(props: {
  title: string;
  detail?: string;
  primaryLabel: string;
  icon?: React.ReactNode;
  disabled?: boolean;
  pending?: boolean;
  onPrimary: () => void;
}) {
  return (
    <article className="efhc-game-action-card" data-canon-frame="source-card">
      <div className="efhc-game-action-card_icon" aria-hidden="true">
        {props.icon || "⚡"}
      </div>
      <div className="min-w-0">
        <div className="efhc-game-action-card_title">
          {props.title}
        </div>
        {props.detail ? (
          <p className="efhc-game-action-card_detail">
            {props.detail}
          </p>
        ) : null}
      </div>
      <Button
        onClick={props.onPrimary}
        disabled={props.disabled || props.pending}
      >
        {props.primaryLabel}
      </Button>
    </article>
  );
}

export function GameProductCard(props: {
  title: string;
  detail?: string;
  price: string;
  badge?: string;
  imageUrl?: string | null;
  imageFallbackUrl?: string | null;
  quantityValue?: string | null;
  quantityAsset?: string | null;
  primaryLabel: string;
  disabled?: boolean;
  onPrimary: () => void;
}) {
  return (
    <article
      className="efhc-game-product-card"
      data-canon-frame="source-card"
      data-game-product-card="web3-large"
      data-product-card-no-raw-payment="true"
      data-product-card-has-image={props.imageUrl ? "true" : "false"}
    >
      <div
        className="efhc-game-product-card_image"
        data-product-card-image-frame="large"
        aria-hidden="true"
      >
        {props.imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={props.imageUrl}
            alt=""
            onError={(event) => {
              const fallback = props.imageFallbackUrl || "";
              if (fallback && event.currentTarget.src !== fallback) {
                event.currentTarget.src = fallback;
              }
            }}
          />
        ) : (
          <span>EFHC</span>
        )}
      </div>
      <div className="efhc-game-product-card_body">
        {props.badge ? (
          <span className="efhc-game-product-card_badge">
            {props.badge}
          </span>
        ) : null}
        <h3>{props.title}</h3>
        {props.quantityValue ? (
          <div className="efhc-game-product-card_quantity">
            <span>{props.quantityAsset || "EFHCm"}</span>
            <strong className="efhc-financial-number">{props.quantityValue}</strong>
          </div>
        ) : null}
        {props.detail ? <p>{props.detail}</p> : null}
      </div>
      <div className="efhc-game-product-card_footer">
        <strong>{props.price}</strong>
        <Button onClick={props.onPrimary} disabled={props.disabled}>
          {props.primaryLabel}
        </Button>
      </div>
    </article>
  );
}

export function GameDetails(
  props: React.PropsWithChildren<{
    summary: string;
    className?: string;
  }>,
) {
  return (
    <details data-canon-frame="source-card" className={`efhc-game-details ${props.className || ""}`}>
      <summary>
        <span>{props.summary}</span>
      </summary>
      <div className="efhc-game-details_body">
        {props.children}
      </div>
    </details>
  );
}

export function GameStatusPill(props: {
  label: string;
  tone?: "ok" | "warn" | "error" | "info";
}) {
  return (
    <span className={`efhc-game-status-pill ${props.tone || "info"}`}>
      {props.label}
    </span>
  );
}
