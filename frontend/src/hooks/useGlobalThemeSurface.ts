import React, { useMemo, useRef } from "react";
import { useInterfaceCustomization } from "./useInterfaceCustomization";

type PointerStart = { x: number; y: number; at: number };

export function useGlobalThemeSurface<T extends HTMLElement>() {
  const customization = useInterfaceCustomization();
  const ref = useRef<T | null>(null);
  const pointerStartRef = useRef<PointerStart | null>(null);
  const suppressClickRef = useRef(false);
  const active = customization.mode === "editing";

  const isNestedLocalSurface = (event: React.SyntheticEvent<T>) => {
    const target = event.target;
    return target instanceof Element
      && target.closest('[data-interface-variant-surface="true"]') !== null;
  };

  return useMemo(() => ({
    ref,
    active,
    globalThemeId: customization.globalThemeId,
    handlers: {
      "data-global-theme-surface": "true",
      "data-interface-selection-active": active ? "true" : undefined,
      onPointerDownCapture: (event: React.PointerEvent<T>) => {
        if (!active || isNestedLocalSurface(event)) return;
        pointerStartRef.current = {
          x: event.clientX,
          y: event.clientY,
          at: Date.now(),
        };
      },
      onPointerUpCapture: (event: React.PointerEvent<T>) => {
        if (!active || isNestedLocalSurface(event)) return;
        const start = pointerStartRef.current;
        pointerStartRef.current = null;
        if (!start) return;
        const dx = event.clientX - start.x;
        const dy = event.clientY - start.y;
        const elapsed = Date.now() - start.at;
        const width = Math.max(1, ref.current?.getBoundingClientRect().width || 1);
        const threshold = Math.max(18, Math.min(64, width * 0.22));
        const horizontal = Math.abs(dx) > Math.abs(dy) * 1.25;
        const validSwipe = horizontal && Math.abs(dx) >= threshold && elapsed <= 1_200;
        const validTap = Math.hypot(dx, dy) <= 8;
        if (!validSwipe && !validTap) return;
        event.preventDefault();
        event.stopPropagation();
        suppressClickRef.current = true;
        if (validSwipe) {
          if (dx < 0) customization.nextGlobalTheme();
          else customization.previousGlobalTheme();
        } else {
          customization.nextGlobalTheme();
        }
        window.setTimeout(() => {
          suppressClickRef.current = false;
        }, 320);
      },
      onPointerCancelCapture: () => {
        pointerStartRef.current = null;
      },
      onClickCapture: (event: React.MouseEvent<T>) => {
        if (!active || isNestedLocalSurface(event)) return;
        event.preventDefault();
        event.stopPropagation();
        if (suppressClickRef.current) return;
        customization.nextGlobalTheme();
      },
      onKeyDownCapture: (event: React.KeyboardEvent<T>) => {
        if (!active || isNestedLocalSurface(event)) return;
        if (event.key === "ArrowLeft" || (event.shiftKey && event.key === "Enter")) {
          event.preventDefault();
          event.stopPropagation();
          customization.previousGlobalTheme();
          return;
        }
        if (event.key === "ArrowRight" || event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          customization.nextGlobalTheme();
        }
      },
    } satisfies React.HTMLAttributes<T> & Record<string, unknown>,
  }), [active, customization]);
}
