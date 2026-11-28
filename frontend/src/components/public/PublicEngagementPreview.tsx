import React, { useMemo, useState } from "react";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { hapticSelection } from "../../lib/telegram";
import { useT } from "../../hooks/useT";

type EngagementVariant = "tasks" | "referrals" | "ranks";
type EngagementTab = "overview" | "progress" | "action";

type PublicEngagementPreviewProps = {
  variant: EngagementVariant;
  primaryLabel: string;
  primaryValue: string;
  secondaryLabel: string;
  secondaryValue: string;
  progressPct: number;
  actionLabel: string;
  onAction: () => void;
  disabled?: boolean;
  hapticsEnabled?: boolean;
};

function clampPct(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

export function PublicEngagementPreview(
  props: PublicEngagementPreviewProps,
) {
  const t = useT();
  const [tab, setTab] = useState<EngagementTab>("overview");
  const progress = clampPct(props.progressPct);
  const flow = useMemo(() => [
    t(`public_engagement.${props.variant}.flow_start`),
    t(`public_engagement.${props.variant}.flow_middle`),
    t(`public_engagement.${props.variant}.flow_finish`),
  ], [props.variant, t]);
  const rootClass = [
    "efhc-public-engagement",
    `efhc-public-engagement--${props.variant}`,
    `is-${tab}`,
  ].join(" ");

  const selectTab = (next: EngagementTab) => {
    hapticSelection(Boolean(props.hapticsEnabled));
    setTab(next);
  };

  return (
    <section
      className={rootClass}
      data-public-visual-beauty="tasks-referrals-ranks"
      data-public-engagement-preview="1350"
      data-public-engagement-variant={props.variant}
      data-public-no-admin-diagnostics="true"
      data-public-hidden-execution-log="forbidden"
    >
      <div className="efhc-public-engagement_head">
        <div>
          <div className="efhc-public-engagement_kicker">
            {t(`public_engagement.${props.variant}.kicker`)}
          </div>
          <h2 className="efhc-public-engagement_title">
            {t(`public_engagement.${props.variant}.title`)}
          </h2>
        </div>
        <Badge>{t("public_engagement.live_badge")}</Badge>
      </div>

      <p className="efhc-public-engagement_detail">
        {t(`public_engagement.${props.variant}.detail`)}
      </p>

      <div className="efhc-public-engagement_tabs" role="tablist">
        {(["overview", "progress", "action"] as EngagementTab[]).map(
          (item) => (
            <button
              key={item}
              className={
                "efhc-public-engagement_tab " +
                (tab === item ? "is-active" : "")
              }
              data-public-engagement-tab={item}
              onClick={() => selectTab(item)}
              type="button"
            >
              {t(`public_engagement.tab_${item}`)}
            </button>
          ),
        )}
      </div>

      <div className="efhc-public-engagement_grid">
        <div className="efhc-public-engagement_metric">
          <span>{props.primaryLabel}</span>
          <strong>{props.primaryValue}</strong>
        </div>
        <div className="efhc-public-engagement_metric">
          <span>{props.secondaryLabel}</span>
          <strong>{props.secondaryValue}</strong>
        </div>
      </div>

      <div
        className="efhc-public-engagement_visual-rail"
        data-public-engagement-visual-rail="tasks-referrals-ranks"
      >
        <span className="efhc-public-engagement_visual-chip is-active">
          {props.primaryLabel}: {props.primaryValue}
        </span>
        <span className="efhc-public-engagement_visual-chip">
          {props.secondaryLabel}: {props.secondaryValue}
        </span>
        <span className="efhc-public-engagement_visual-chip">
          {progress.toFixed(0)}%
        </span>
      </div>

      <div className="efhc-public-engagement_progress">
        <div className="efhc-public-engagement_progress-top">
          <span>{t(`public_engagement.${props.variant}.progress_label`)}</span>
          <strong>{progress.toFixed(0)}%</strong>
        </div>
        <div className="efhc-public-engagement_track">
          <div
            className="efhc-public-engagement_fill"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <div className="efhc-public-engagement_flow" aria-hidden="true">
        <svg viewBox="0 0 320 92" role="img">
          <path
            d="M42 46 C92 12 128 82 164 46 S236 12 278 46"
            fill="none"
            stroke="currentColor"
            strokeDasharray="6 8"
            strokeWidth="3"
          />
          {[42, 164, 278].map((cx, index) => (
            <g key={cx}>
              <circle cx={cx} cy="46" r="18" />
              <text x={cx} y="51" textAnchor="middle">
                {index + 1}
              </text>
            </g>
          ))}
        </svg>
        <div className="efhc-public-engagement_flow-labels">
          {flow.map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>
      </div>

      <div className="efhc-public-engagement_note">
        {t(`public_engagement.${props.variant}.${tab}`)}
      </div>

      <Button
        className="w-full"
        disabled={props.disabled}
        onClick={() => {
          hapticSelection(Boolean(props.hapticsEnabled));
          props.onAction();
        }}
      >
        {props.actionLabel}
      </Button>
    </section>
  );
}
