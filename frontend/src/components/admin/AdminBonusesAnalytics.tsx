import React from "react";

import { TelegramStatusBadge } from "../ui/telegram/TelegramStatusBadge";
import { Button } from "../ui/Button";
import { AdminSectionCard } from "./AdminSectionCard";
import {
  formatD8ToHuman,
  fromScaledBigint,
  toScaledBigintDown,
} from "../../lib/format";

export type AdminBonusSource = "tasks" | "referrals" | "manual";

export type AdminBonusSummary = {
  total_amount: string;
  tasks_amount: string;
  referrals_amount: string;
  manual_amount: string;
  total_count: number;
  tasks_count: number;
  referrals_count: number;
  manual_count: number;
};

export type AdminBonusItem = {
  event_key: string;
  source: AdminBonusSource;
  source_label: string;
  global_id: string;
  username?: string | null;
  amount: string;
  reason: string;
  created_at: string;
  admin_global_id?: string | null;
};

export const EMPTY_ADMIN_BONUS_SUMMARY: AdminBonusSummary = {
  total_amount: "0",
  tasks_amount: "0",
  referrals_amount: "0",
  manual_amount: "0",
  total_count: 0,
  tasks_count: 0,
  referrals_count: 0,
  manual_count: 0,
};

type SourceMeta = {
  id: AdminBonusSource;
  label: string;
  amount: string;
  count: number;
  tone: "connected" | "vip" | "warning";
};

function nonNegativeScaled(value: string): bigint {
  try {
    const scaled = toScaledBigintDown(value, 8);
    return scaled > 0n ? scaled : 0n;
  } catch {
    return 0n;
  }
}

function percentHundredths(part: bigint, total: bigint): bigint {
  if (part <= 0n || total <= 0n) return 0n;
  const hundredths = (part * 10_000n) / total;
  return hundredths > 10_000n ? 10_000n : hundredths;
}

function percentLabel(hundredths: bigint): string {
  const safe = hundredths < 0n ? 0n : hundredths > 10_000n ? 10_000n : hundredths;
  return `${safe / 100n},${String(safe % 100n).padStart(2, "0")}%`;
}

function barWidth(hundredths: bigint): string {
  if (hundredths <= 0n) return "0%";
  const basisPoints = hundredths > 10_000n ? 10_000n : hundredths;
  return `${Math.max(1, Number(basisPoints) / 100)}%`;
}

function averageAmount(amount: string, count: number): string {
  if (count <= 0) return "0.00000000";
  const scaled = nonNegativeScaled(amount);
  return fromScaledBigint(scaled / BigInt(count), 8);
}

function sourceRows(summary: AdminBonusSummary): SourceMeta[] {
  return [
    { id: "tasks", label: "За задания", amount: summary.tasks_amount, count: summary.tasks_count, tone: "connected" },
    { id: "referrals", label: "За рефералов", amount: summary.referrals_amount, count: summary.referrals_count, tone: "vip" },
    { id: "manual", label: "Вручную администратором", amount: summary.manual_amount, count: summary.manual_count, tone: "warning" },
  ];
}

export function adminBonusSourceTone(source: AdminBonusSource) {
  if (source === "manual") return "warning" as const;
  if (source === "referrals") return "vip" as const;
  return "connected" as const;
}

export function adminBonusSourceLabel(source: AdminBonusSource): string {
  if (source === "manual") return "Вручную администратором";
  if (source === "referrals") return "За рефералов";
  return "За задания";
}

export function AdminBonusesCompactOverview(props: {
  summary: AdminBonusSummary;
  visibleSources: Record<AdminBonusSource, boolean>;
  onToggleSource: (source: AdminBonusSource) => void;
}) {
  const rows = sourceRows(props.summary);
  const totalAmount = nonNegativeScaled(props.summary.total_amount);
  const visibleRows = rows.filter((row) => props.visibleSources[row.id]);

  return (
    <AdminSectionCard
      title="Карта начислений"
      subtitle={`Всего ${props.summary.total_count.toLocaleString("ru-RU")} событий · точные суммы EFHCb`}
    >
      <div className="efhc-bonuses-bank-map" data-eam-family="EAM-ADMIN-012">
        <div className="efhc-admin-bank-map-v154_toggles" aria-label="Источники карты начислений" data-admin-bonuses-checkboxes="admin-bank-parity">
          {rows.map((row) => (
            <label key={row.id}>
              <input
                checked={props.visibleSources[row.id]}
                onChange={() => props.onToggleSource(row.id)}
                type="checkbox"
                aria-label={row.label}
                title={row.label}
              />
            </label>
          ))}
        </div>

        <div className="efhc-bonuses-bank-map-rows">
          <div className="efhc-bonuses-bank-map-row is-total" data-source="total">
            <div className="efhc-bonuses-bank-map-copy">
              <strong>Всего начислено</strong>
              <span>{formatD8ToHuman(props.summary.total_amount)} EFHCb</span>
            </div>
            <div className="efhc-bonuses-bank-map-indicator">
              <div className="efhc-bonuses-bank-map-track" aria-hidden="true"><span style={{ width: totalAmount > 0n ? "100%" : "0%" }} /></div>
              <b>{totalAmount > 0n ? "100,00%" : "0,00%"}</b>
            </div>
            <small>{props.summary.total_count.toLocaleString("ru-RU")} событий</small>
          </div>

          {visibleRows.map((row) => {
            const scaled = nonNegativeScaled(row.amount);
            const share = percentHundredths(scaled, totalAmount);
            return (
              <div className={`efhc-bonuses-bank-map-row is-${row.id}`} data-source={row.id} key={row.id}>
                <div className="efhc-bonuses-bank-map-copy">
                  <strong>{row.label}</strong>
                  <span>{formatD8ToHuman(row.amount)} EFHCb</span>
                </div>
                <div className="efhc-bonuses-bank-map-indicator">
                  <div className="efhc-bonuses-bank-map-track" aria-label={`${row.label}: ${percentLabel(share)}`} role="img">
                    <span style={{ width: barWidth(share) }} />
                  </div>
                  <b>{percentLabel(share)}</b>
                </div>
                <small>
                  {row.count.toLocaleString("ru-RU")} событий · среднее {formatD8ToHuman(averageAmount(row.amount, row.count))} EFHCb
                </small>
              </div>
            );
          })}

          {!visibleRows.length ? (
            <div className="efhc-bonuses-bank-map-empty">Выберите хотя бы один источник.</div>
          ) : null}
        </div>
      </div>
    </AdminSectionCard>
  );
}

export function AdminBonusHistoryCards(props: {
  items: AdminBonusItem[];
  formatDate: (value: string) => string;
}) {
  return (
    <div className="efhc-bonuses-mobile-list">
      {props.items.map((item) => (
        <article className="efhc-bonuses-mobile-item" key={item.event_key}>
          <div className="efhc-bonuses-mobile-head">
            <TelegramStatusBadge
              label={adminBonusSourceLabel(item.source)}
              tone={adminBonusSourceTone(item.source)}
            />
            <strong>{formatD8ToHuman(item.amount)} EFHCb</strong>
          </div>
          <div className="efhc-bonuses-mobile-identity">
            <span>{item.username ? `@${item.username}` : "Пользователь"}</span>
            <strong>Global ID {item.global_id}</strong>
          </div>
          <div className="efhc-bonuses-mobile-reason">{item.reason}</div>
          <div className="efhc-bonuses-mobile-foot">
            <span>
              {item.source === "manual"
                ? item.admin_global_id
                  ? `Администратор · Global ID ${item.admin_global_id}`
                  : "Администратор"
                : "Автоматически"}
            </span>
            <span>{props.formatDate(item.created_at)}</span>
          </div>
          <Button
            href={`/admin/users?global_id=${encodeURIComponent(item.global_id)}`}
            variant="secondary"
          >
            Открыть пользователя
          </Button>
        </article>
      ))}
    </div>
  );
}
