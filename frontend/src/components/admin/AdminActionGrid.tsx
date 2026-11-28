import React from "react";
import { Button } from "../ui/Button";

type ActionItem = {
  href?: string;
  label: string;
  note?: string;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
};

type Props = {
  title: string;
  subtitle?: string;
  items: ActionItem[];
};

export function AdminActionGrid({
  title,
  subtitle,
  items,
}: Props) {
  return (
    <div className="efhc-admin-action-grid rounded-2xl border p-4 space-y-3">
      <div>
        <div className="text-sm font-semibold">{title}</div>
        {subtitle ? (
          <div className="text-xs efhc-text-muted mt-1">{subtitle}</div>
        ) : null}
      </div>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => {
          const content = (
            <span className="flex flex-col items-start gap-1">
              <span>{item.label}</span>
              {item.note ? (
                <span className="text-xs opacity-80 font-normal">
                  {item.note}
                </span>
              ) : null}
            </span>
          );
          if (item.href) {
            return (
              <div key={item.href}>
                <Button
                  href={item.href}
                  variant={item.variant || "secondary"}
                  disabled={item.disabled}
                  className="w-full justify-start text-left min-h-12"
                >
                  {content}
                </Button>
              </div>
            );
          }
          return (
            <div key={item.label}>
              <Button
                variant={item.variant || "secondary"}
                onClick={item.onClick}
                disabled={item.disabled}
                className="w-full justify-start text-left min-h-12"
              >
                {content}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
