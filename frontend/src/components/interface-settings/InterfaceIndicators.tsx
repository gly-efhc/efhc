import React from "react";
import { COLOR_THEME_CATALOG } from "../../lib/colorThemeRegistry";
import {
  getInterfaceVariantAuthoredSlotCount,
  INTERFACE_VARIANT_REGISTRY,
  INTERFACE_VARIANT_SLOT_REGISTRY,
} from "../../lib/interfaceVariantRegistry";
import type { InterfaceVariantGroup, InterfaceVariantSettings } from "../../types/interfaceCustomization";
import { useInterfaceCustomization } from "../../hooks/useInterfaceCustomization";

export function VariantIndicatorDots(props: {
  group: InterfaceVariantGroup;
  effective: InterfaceVariantSettings;
}) {
  const compact = props.group === "HI" || props.group === "XH";
  const variants = compact
    ? INTERFACE_VARIANT_REGISTRY[props.group]
    : INTERFACE_VARIANT_SLOT_REGISTRY[props.group];
  const count = compact ? variants.length : getInterfaceVariantAuthoredSlotCount(props.group);
  if (count < 2) return null;
  return <>{Array.from({ length: count }, (_, index) => {
    const variant = variants[index] ?? null;
    return <span
      key={variant || `empty-${index + 1}`}
      data-active={variant && variant === props.effective[props.group] ? "true" : "false"}
      data-slot-state={variant ? "available" : "empty"}
    />;
  })}</>;
}

/** Informational USER-only rows; Header is outside the scrolling main. */
export function InterfaceIndicators(props: { pageGroup?: InterfaceVariantGroup }) {
  const customization = useInterfaceCustomization();
  if (customization.mode !== "editing") return null;
  return <div className="efhc-user-indicator-dock" data-user-indicator-dock="true" aria-hidden="true">
    <div className="efhc-energy-frame-theme-slots" data-color-theme-indicators={COLOR_THEME_CATALOG.length}>
      {COLOR_THEME_CATALOG.map(theme => <span
        key={theme.id}
        data-color-theme-id={theme.id}
        data-active={customization.colorThemeId === theme.id ? "true" : "false"}
        style={{ "--efhc-indicator-color": theme.accent } as React.CSSProperties}
      />)}
    </div>
    {props.pageGroup && getInterfaceVariantAuthoredSlotCount(props.pageGroup) > 1 && <div
      className="efhc-interface-variant-dots efhc-page-variant-dots"
      data-indicator-group={props.pageGroup}
      data-indicator-placement="page"
    ><VariantIndicatorDots group={props.pageGroup} effective={customization.effective} /></div>}
  </div>;
}
