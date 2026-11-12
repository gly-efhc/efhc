import React from "react";
import { createPortal } from "react-dom";

import { useT } from "../../hooks/useT";
import type { ColorThemeId } from "../../lib/colorThemeRegistry";

const MODAL_TABBABLE_SELECTOR = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=\"hidden\"])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "iframe",
  "[contenteditable=\"true\"]",
  "[tabindex]:not([tabindex=\"-1\"])",
].join(",");

type ModalInertSnapshot = {
  hadAttribute: boolean;
  value: string | null;
};

const modalBackgroundInertSnapshots = new Map<HTMLElement, ModalInertSnapshot>();
let modalBackgroundObserver: MutationObserver | null = null;
let modalBodyScrollLocks = 0;
let modalOriginalBodyOverflow = "";

type ModalDragState = {
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
  originRect: DOMRect;
};

function modalOpenOverlays(): HTMLElement[] {
  return Array.from(
    document.querySelectorAll<HTMLElement>(
      '[data-modal-portal="body"][role="dialog"]',
    ),
  );
}

function restoreModalBackgroundElement(element: HTMLElement, snapshot: ModalInertSnapshot): void {
  if (snapshot.hadAttribute) {
    element.setAttribute("inert", snapshot.value ?? "");
  } else {
    element.removeAttribute("inert");
  }
}

function syncModalBackgroundInert(): void {
  if (typeof document === "undefined") return;

  const top = modalOpenOverlays().at(-1) ?? null;
  const desired = new Set<HTMLElement>();
  if (top) {
    for (const child of Array.from(document.body.children)) {
      // TonConnect renders wallet approval in its own official body portal.
      // Never make that separate consent UI inert behind the EFHC dialog.
      if (child instanceof HTMLElement && child !== top
          && child.id !== "tc-widget-root") desired.add(child);
    }
  }

  for (const [element, snapshot] of modalBackgroundInertSnapshots) {
    if (desired.has(element)) continue;
    restoreModalBackgroundElement(element, snapshot);
    modalBackgroundInertSnapshots.delete(element);
  }

  for (const element of desired) {
    if (!modalBackgroundInertSnapshots.has(element)) {
      modalBackgroundInertSnapshots.set(element, {
        hadAttribute: element.hasAttribute("inert"),
        value: element.getAttribute("inert"),
      });
    }
    element.setAttribute("inert", "");
  }

  if (top && !modalBackgroundObserver) {
    modalBackgroundObserver = new MutationObserver(() => syncModalBackgroundInert());
    modalBackgroundObserver.observe(document.body, { childList: true });
  } else if (!top && modalBackgroundObserver) {
    modalBackgroundObserver.disconnect();
    modalBackgroundObserver = null;
  }
}

function modalTabbables(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(MODAL_TABBABLE_SELECTOR))
    .filter((element) => {
      if (element.matches(":disabled")) return false;
      if (element.closest('[hidden], [aria-hidden="true"]')) return false;
      const style = window.getComputedStyle(element);
      return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
    })
    .map((element, index) => ({ element, index }))
    .sort((a, b) => {
      const aTabIndex = a.element.tabIndex;
      const bTabIndex = b.element.tabIndex;
      const aPositive = aTabIndex > 0;
      const bPositive = bTabIndex > 0;
      if (aPositive && bPositive && aTabIndex !== bTabIndex) return aTabIndex - bTabIndex;
      if (aPositive !== bPositive) return aPositive ? -1 : 1;
      return a.index - b.index;
    })
    .map(({ element }) => element);
}

export function Modal(
  props: React.PropsWithChildren<{
    open: boolean;
    onClose: () => void;
    title: string;
    closeDisabled?: boolean;
    portalColorThemeId?: ColorThemeId;
  }>,
) {
  const t = useT();
  const overlayRef = React.useRef<HTMLDivElement>(null);
  const sheetRef = React.useRef<HTMLDivElement>(null);
  const closeButtonRef = React.useRef<HTMLButtonElement>(null);
  const initiatorRef = React.useRef<HTMLElement | null>(null);
  const wasOpenRef = React.useRef(false);
  const dragRef = React.useRef<ModalDragState | null>(null);
  const dragOffsetRef = React.useRef({ x: 0, y: 0 });

  // Lock only background scrolling. Long dialogs remain independently scrollable.
  React.useEffect(() => {
    if (!props.open || typeof document === "undefined") return;
    if (modalBodyScrollLocks === 0) {
      modalOriginalBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    modalBodyScrollLocks += 1;
    return () => {
      modalBodyScrollLocks = Math.max(0, modalBodyScrollLocks - 1);
      if (modalBodyScrollLocks === 0) {
        document.body.style.overflow = modalOriginalBodyOverflow;
      }
    };
  }, [props.open]);

  React.useEffect(() => {
    if (!props.open) {
      dragRef.current = null;
      dragOffsetRef.current = { x: 0, y: 0 };
      return;
    }
    const reset = () => {
      dragRef.current = null;
      dragOffsetRef.current = { x: 0, y: 0 };
      if (sheetRef.current) sheetRef.current.style.transform = "";
    };
    // Layout viewport may change when the keyboard opens or device rotates.
    window.addEventListener("resize", reset);
    return () => window.removeEventListener("resize", reset);
  }, [props.open]);

  const onDragStart = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || event.target instanceof Element &&
      event.target.closest("button, a, input, select, textarea, [data-no-modal-drag]")) return;
    const sheet = sheetRef.current;
    if (!sheet) return;
    const rect = sheet.getBoundingClientRect();
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: dragOffsetRef.current.x,
      originY: dragOffsetRef.current.y,
      originRect: rect,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };

  const onDragMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const sheet = sheetRef.current;
    if (!sheet) return;
    const rect = drag.originRect;
    const dx = Math.max(-rect.left, Math.min(
      window.innerWidth - rect.right,
      event.clientX - drag.startX,
    ));
    // A virtual keyboard can shrink the visible viewport without changing
    // window.innerHeight. Never drag a sheet behind the keyboard or OS chrome.
    const viewportTop = window.visualViewport?.offsetTop ?? 0;
    const viewportBottom = window.visualViewport
      ? viewportTop + window.visualViewport.height
      : window.innerHeight;
    const dy = Math.max(viewportTop - rect.top, Math.min(
      window.innerHeight - rect.bottom,
      viewportBottom - rect.bottom,
      event.clientY - drag.startY,
    ));
    const x = drag.originX + dx;
    const y = drag.originY + dy;
    dragOffsetRef.current = { x, y };
    sheet.style.transform = `translate3d(${x}px, ${y}px, 0)`;
  };

  const onDragEnd = (event: React.PointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  React.useEffect(() => {
    if (typeof document === "undefined") return;

    if (props.open && !wasOpenRef.current) {
      initiatorRef.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      syncModalBackgroundInert();
      const initialTarget =
        sheetRef.current?.querySelector<HTMLElement>("[data-modal-initial-focus]") ??
        closeButtonRef.current;
      initialTarget?.focus({ preventScroll: true });
    }

    if (!props.open && wasOpenRef.current) {
      syncModalBackgroundInert();
      const initiator = initiatorRef.current;
      initiatorRef.current = null;
      if (initiator?.isConnected) {
        initiator.focus({ preventScroll: true });
      }
    }

    wasOpenRef.current = props.open;
  }, [props.open]);

  React.useEffect(() => {
    if (!props.open || typeof document === "undefined") return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab" && event.key !== "Escape") return;

      // Official TON Connect approval has its own focus and Escape handling.
      // Do not trap a wallet approval back inside the EFHC amount editor.
      const walletRoot = document.getElementById("tc-widget-root");
      if (walletRoot && (walletRoot.contains(document.activeElement)
        || walletRoot.querySelector('[data-tc-modal="true"],[data-tc-actions-modal-container="true"],[data-tc-wallets-modal-container="true"]'))) {
        return;
      }
      const overlay = overlayRef.current;
      const sheet = sheetRef.current;
      if (!overlay || !sheet) return;

      const openModals = Array.from(
        document.querySelectorAll<HTMLElement>('[data-modal-portal="body"][role="dialog"]'),
      );
      if (openModals.at(-1) !== overlay) return;

      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (!props.closeDisabled) props.onClose();
        return;
      }

      const tabbables = modalTabbables(sheet);
      if (tabbables.length === 0) {
        event.preventDefault();
        overlay.focus({ preventScroll: true });
        return;
      }

      const first = tabbables[0];
      const last = tabbables[tabbables.length - 1];
      const active = document.activeElement;
      if (!(active instanceof HTMLElement) || !sheet.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus({ preventScroll: true });
        return;
      }
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [props.closeDisabled, props.onClose, props.open]);

  if (!props.open || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={overlayRef}
      className={props.portalColorThemeId ? "fixed inset-0 efhc-modal-overlay efhc-user-direct-deposit-portal" : "fixed inset-0 efhc-modal-overlay"}
      data-interface-app-mode={props.portalColorThemeId ? "user" : undefined}
      data-color-theme-id={props.portalColorThemeId}
      aria-modal="true"
      role="dialog"
      aria-label={props.title}
      data-modal-portal="body"
      tabIndex={-1}
      onClick={() => { if (!props.closeDisabled) props.onClose(); }}
    >
      <div
        ref={sheetRef}
        className="efhc-modal efhc-modal-sheet w-full"
        onClick={(event) => event.stopPropagation()}
      >
        <div
          className="efhc-modal-header"
          data-modal-drag-handle="true"
          onPointerDown={onDragStart}
          onPointerMove={onDragMove}
          onPointerUp={onDragEnd}
          onPointerCancel={onDragEnd}
        >
          <div className="efhc-modal-title">{props.title}</div>
          <button
            ref={closeButtonRef}
            type="button"
            className="efhc-modal-close"
            aria-label={t("common.close")}
            disabled={props.closeDisabled}
            onClick={props.onClose}
          >
            ×
          </button>
        </div>
        <div className="efhc-modal-body">{props.children}</div>
      </div>
    </div>,
    document.body,
  );
}
