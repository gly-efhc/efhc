import React from "react";

import { Button } from "../ui/Button";

export type AdminAppCategory =
  | "finance"
  | "analytics"
  | "commerce"
  | "engagement"
  | "system";

export type AdminAppItem = {
  href?: string;
  label: string;
  category: AdminAppCategory;
  disabled?: boolean;
};

type Props = {
  items: AdminAppItem[];
};


export function AdminAppButtonGrid(props: Props) {
  return (
    <div className="efhc-admin-app-grid" data-eam-family="EAM-ADMIN-003">
      {props.items.map((item, index) => (
        <Button
          key={item.href || `${item.label}-${index}`}
          {...(item.href ? { href: item.href } : {})}
          disabled={Boolean(item.disabled || !item.href)}
          aria-label={item.label}
          data-admin-category={item.category}
          variant="secondary"
          className="efhc-admin-app-button"
        >
          <strong className="efhc-admin-app-button_title">{item.label}</strong>
        </Button>
      ))}
    </div>
  );
}
