import React, {
  useEffect,
  useId,
  useMemo,
  useRef,
} from "react";
import type {
  InterfaceVariantGroup,
  VariantDotsPlacement,
} from "../types/interfaceCustomization";
import { getInterfaceVariantSelectionOrder, resolveInterfaceVariantStyle } from "../lib/interfaceVariantRegistry";
import { useInterfaceCustomization } from "./useInterfaceCustomization";

type PointerStart = {
  x: number;
  y: number;
  at: number;
};

export function useInterfaceVariantSurface<T extends HTMLElement>(
  group: InterfaceVariantGroup,
  options?: {
    dotsPlacement?: VariantDotsPlacement;
    registerDots?: boolean;
    interactive?: boolean;
  },
) {
  const customization = useInterfaceCustomization();
  const ref = useRef<T | null>(null);
  const pointerStartRef = useRef<PointerStart | null>(null);
  const suppressClickRef = useRef(false);
  const id = useId();
  const placement = options?.dotsPlacement || "above";
  const registerDots = options?.registerDots !== false;
  const interactive = options?.interactive !== false;

  useEffect(() => {
    const element = ref.current;
    if (!element || !registerDots) return;
    return customization.registerSurface({
      id,
      group,
      element,
      placement,
    });
  }, [customization, group, id, placement, registerDots]);

  const active = interactive
    && customization.mode === "editing"
    && customization.isGroupActive(group);
  const isNestedControl = (event: React.SyntheticEvent<T>) => {
    const target = event.target;
    if (!(target instanceof Element)) return false;
    // Capture runs from the outer surface inward. Only the nearest surface
    // owns a gesture; EG must not consume a tap intended for its nested PB.
    return target.closest('[data-interface-variant-surface="true"][data-interface-selection-active="true"]') !== ref.current
      || target.closest('[data-interface-customization-control="true"], [data-app-navigation]') !== null;
  };

  return useMemo(() => ({
    ref,
    active,
    selection: customization.effective[group],
    variant: resolveInterfaceVariantStyle(group, customization.effective[group]),
    handlers: {
      "data-interface-variant-surface": "true",
      "data-interface-variant-group": group,
      "data-interface-selection-active": active ? "true" : undefined,
      "data-interface-variant-readonly": interactive ? undefined : "true",
      // Interactive surfaces must be keyboard-focusable; indicators are visual
      // only and never become an invisible keyboard trap.
      tabIndex: active ? 0 : undefined,
      role: active ? "button" : undefined,
      "aria-label": active ? `Шаблон: ${getInterfaceVariantSelectionOrder(group).indexOf(customization.effective[group]) + 1} из ${getInterfaceVariantSelectionOrder(group).length}. Enter — следующий, стрелка влево — предыдущий` : undefined,
      onPointerDownCapture: (event: React.PointerEvent<T>) => {
        if (!active) return;
        if (isNestedControl(event)) return;
        pointerStartRef.current = {
          x: event.clientX,
          y: event.clientY,
          at: Date.now(),
        };
      },
      onPointerUpCapture: (event: React.PointerEvent<T>) => {
        if (!active) return;
        if (isNestedControl(event)) return;
        const start = pointerStartRef.current;
        pointerStartRef.current = null;
        if (!start) return;
        const dx = event.clientX - start.x;
        const dy = event.clientY - start.y;
        const elapsed = Date.now() - start.at;
        const width = Math.max(1, ref.current?.getBoundingClientRect().width || 1);
        const threshold = Math.max(18, Math.min(64, width * 0.22));
        const horizontal = Math.abs(dx) > Math.abs(dy) * 1.25;
        const validSwipe = horizontal
          && Math.abs(dx) >= threshold
          && elapsed <= 1_200;
        const validTap = Math.hypot(dx, dy) <= 8;
        if (!validSwipe && !validTap) return;
        event.preventDefault();
        event.stopPropagation();
        suppressClickRef.current = true;
        if (validSwipe) {
          if (dx < 0) customization.next(group);
          else customization.previous(group);
        } else {
          customization.next(group);
        }
        window.setTimeout(() => {
          suppressClickRef.current = false;
        }, 320);
      },
      onClickCapture: (event: React.MouseEvent<T>) => {
        if (!active) return;
        if (isNestedControl(event)) return;
        event.preventDefault();
        event.stopPropagation();
        if (suppressClickRef.current) return;
        customization.next(group);
      },
      onKeyDownCapture: (event: React.KeyboardEvent<T>) => {
        if (!active || event.target !== ref.current) return;
        if (isNestedControl(event)) return;
        if (event.key === "ArrowLeft" || (event.shiftKey && event.key === "Enter")) {
          event.preventDefault();
          event.stopPropagation();
          customization.previous(group);
          return;
        }
        if (
          event.key === "ArrowRight"
          || event.key === "Enter"
          || event.key === " "
        ) {
          event.preventDefault();
          event.stopPropagation();
          customization.next(group);
        }
      },
    } satisfies React.HTMLAttributes<T> & Record<string, unknown>,
  }), [active, customization, group, interactive]);
}
