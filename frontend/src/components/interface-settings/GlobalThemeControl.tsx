import React, { useRef } from "react";
import { useInterfaceCustomization } from
  "../../hooks/useInterfaceCustomization";

type PointerStart = {
  x: number;
  y: number;
  at: number;
};

export function GlobalThemeControl() {
  const customization = useInterfaceCustomization();
  const pointerStartRef = useRef<PointerStart | null>(null);
  const suppressClickRef = useRef(false);
  if (customization.mode !== "editing") return null;
  return (
    <button
      type="button"
      className="efhc-global-theme-control"
      data-interface-customization-control="true"
      data-color-theme-control="true"
      aria-label="Переключить цветовую тему"
      onPointerDown={(event) => {
        try {
          event.currentTarget.setPointerCapture(event.pointerId);
        } catch {
          // Pointer capture is optional in restricted WebView engines.
        }
        pointerStartRef.current = {
          x: event.clientX,
          y: event.clientY,
          at: Date.now(),
        };
      }}
      onPointerUp={(event) => {
        try {
          event.currentTarget.releasePointerCapture(event.pointerId);
        } catch {
          // The pointer may already be released by the host WebView.
        }
        const start = pointerStartRef.current;
        pointerStartRef.current = null;
        if (!start) return;
        const dx = event.clientX - start.x;
        const dy = event.clientY - start.y;
        const elapsed = Date.now() - start.at;
        const validSwipe = Math.abs(dx) >= 18
          && Math.abs(dx) > Math.abs(dy) * 1.25
          && elapsed <= 1_200;
        if (!validSwipe) return;
        event.preventDefault();
        event.stopPropagation();
        suppressClickRef.current = true;
        if (dx < 0) customization.nextGlobalTheme();
        else customization.previousGlobalTheme();
        window.setTimeout(() => {
          suppressClickRef.current = false;
        }, 320);
      }}
      onPointerCancel={() => {
        pointerStartRef.current = null;
      }}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (suppressClickRef.current) return;
        customization.nextGlobalTheme();
      }}
    >
      <span aria-hidden="true">🌐</span>
    </button>
  );
}
