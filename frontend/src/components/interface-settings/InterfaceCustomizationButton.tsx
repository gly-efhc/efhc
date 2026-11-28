import React from "react";
import { useInterfaceCustomization } from
  "../../hooks/useInterfaceCustomization";

function GearIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 15.25A3.25 3.25 0 1 0 12 8.75a3.25 3.25 0 0 0 0 6.5Z"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.86 2.86-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .62 1.7 1.7 0 0 0-.38 1.08V21h-4v-.1a1.7 1.7 0 0 0-1.38-1.66 1.7 1.7 0 0 0-1.62.5l-.06.06-2.86-2.86.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.62-1 1.7 1.7 0 0 0-1.08-.38H3v-4h.1A1.7 1.7 0 0 0 4.76 8.24a1.7 1.7 0 0 0-.5-1.62l-.06-.06L7.06 3.7l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.62A1.7 1.7 0 0 0 10.38 2.9V3h4v-.1A1.7 1.7 0 0 0 15.76 4.56a1.7 1.7 0 0 0 1.62-.5l.06-.06 2.86 2.86-.06.06A1.7 1.7 0 0 0 19.4 9c.1.38.32.72.62 1 .3.24.68.38 1.08.38h.1v4h-.1A1.7 1.7 0 0 0 19.4 15Z"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="m5.5 12.5 4.1 4.1L18.8 7.4"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function InterfaceCustomizationButton(props: {
  hasBottomNav: boolean;
}) {
  const customization = useInterfaceCustomization();
  const editing = customization.mode === "editing";
  return (
    <button
      type="button"
      className="efhc-interface-customization-button"
      data-interface-customization-control="true"
      data-visible={customization.buttonVisible ? "true" : "false"}
      data-mode={customization.mode}
      data-has-bottom-nav={props.hasBottomNav ? "true" : "false"}
      aria-label={editing ? "Сохранить оформление" : "Настроить оформление"}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (editing) customization.save();
        else customization.enter();
      }}
    >
      {editing ? <CheckIcon /> : <GearIcon />}
    </button>
  );
}
