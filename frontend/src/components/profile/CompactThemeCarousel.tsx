import React from "react";

import { COLOR_THEME_CATALOG } from "../../lib/colorThemeRegistry";

type Props = {
  currentThemeId: string;
  label: string;
  onSelect: (themeId: string) => void;
};

export function CompactThemeCarousel(props: Props) {
  return (
    <div className="efhc-compact-theme-picker">
      <div className="efhc-compact-theme-picker_label">{props.label}</div>
      <div
        className="efhc-compact-theme-carousel"
        role="listbox"
        aria-label={props.label}
      >
        {COLOR_THEME_CATALOG.map((theme) => {
          const active = props.currentThemeId === theme.id;
          const indicatorStyle = {
            "--efhc-indicator-color": theme.accent,
          } as React.CSSProperties;
          return (
            <button
              key={theme.id}
              type="button"
              role="option"
              aria-selected={active}
              aria-label={`${theme.id}: ${theme.nameRu}`}
              className="efhc-compact-theme-carousel_item"
              data-active={active ? "true" : "false"}
              data-color-theme-id={theme.id}
              style={indicatorStyle}
              onClick={() => props.onSelect(theme.id)}
            >
              <span className="efhc-compact-theme-carousel_swatch" aria-hidden="true" />
              <span className="efhc-compact-theme-carousel_copy">
                <small>{theme.id}</small>
                <strong>{theme.nameRu}</strong>
              </span>
              <span className="efhc-compact-theme-carousel_mark" aria-hidden="true">
                {active ? "✓" : ""}
              </span>
            </button>
          );
        })}
      </div>
      <div
        className="efhc-compact-theme-dots"
        aria-hidden="true"
        data-color-theme-dots={COLOR_THEME_CATALOG.length}
      >
        {COLOR_THEME_CATALOG.map((theme) => (
          <span
            key={theme.id}
            data-color-theme-id={theme.id}
            data-active={props.currentThemeId === theme.id ? "true" : "false"}
            style={{ "--efhc-indicator-color": theme.accent } as React.CSSProperties}
          />
        ))}
      </div>
    </div>
  );
}
