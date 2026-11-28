import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { VariantIndicatorDots } from "./InterfaceIndicators";
import { getInterfaceVariantAuthoredSlotCount } from "../../lib/interfaceVariantRegistry";
import type { InterfaceCustomizationMode, InterfaceVariantGroup, InterfaceVariantSettings, VariantDotsPlacement } from "../../types/interfaceCustomization";

type Surface = { id: string; group: InterfaceVariantGroup; element: HTMLElement; placement: VariantDotsPlacement };
type PositionedSurface = Surface & { left: number; top: number; placementKind: string };
type Box = { left: number; top: number; right: number; bottom: number };
const intersects = (a: Box, b: Box) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;

/** Text and actionable controls are occupied space, including multi-line text. */
function occupied(element: HTMLElement, band: Box, navigationPadding = false): Box[] {
  const boxes: Box[] = [];
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let node: Node | null;
  while ((node = walker.nextNode())) {
    if (!node.textContent?.trim() || node.parentElement?.closest('[aria-hidden="true"]')) continue;
    const parent = node.parentElement;
    if (!parent || !intersects(parent.getBoundingClientRect(), band)) continue;
    const range = document.createRange(); range.selectNodeContents(node);
    boxes.push(...Array.from(range.getClientRects()).filter(rect => rect.width && rect.height).map(rect => ({left:rect.left-1,right:rect.right+1,top:rect.top-1,bottom:rect.bottom+1})));
  }
  element.querySelectorAll(navigationPadding ? 'input,select,textarea,img,svg' : 'button,a,input,select,textarea,img,svg').forEach(control => {
    const rect = control.getBoundingClientRect();
    if (rect.width && rect.height && intersects(rect, band)) boxes.push(rect);
  });
  return boxes;
}

export function InterfaceVariantDotsLayer(props: {
  surfaces: Surface[]; mode: InterfaceCustomizationMode;
  effective: InterfaceVariantSettings; activeGroups: readonly InterfaceVariantGroup[];
}) {
  const [mounted, setMounted] = useState(false);
  const [positions, setPositions] = useState<PositionedSurface[]>([]);
  const nodes = useRef(new Map<string, HTMLDivElement>());
  useEffect(() => setMounted(true), []);
  useEffect(() => {
    if (props.mode !== "editing") { setPositions([]); return; }
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const pageGroups = new Set(Array.from(document.querySelectorAll('[data-indicator-placement="page"]')).map(el => el.getAttribute('data-indicator-group')));
        const next: PositionedSurface[] = [];
        for (const surface of props.surfaces) {
          if (!props.activeGroups.includes(surface.group) || !surface.element.isConnected) continue;
          if (getInterfaceVariantAuthoredSlotCount(surface.group) < 2) continue;
          const el = surface.element;
          const user = Boolean(el.closest('.efhc-independent-shell[data-interface-app-mode="user"]'));
          if (user && pageGroups.has(surface.group)) continue;
          const rect = el.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0 || rect.bottom < 0 || rect.top > innerHeight) continue;
          // Independent Admin/Shop retain their existing indicator positioning.
          if (!user) {
            next.push({ ...surface, left:rect.left + rect.width / 2,
              top:surface.placement === 'below' ? Math.min(innerHeight - 5, rect.bottom + 6) : Math.max(5, rect.top - 8), placementKind:'legacy' });
            continue;
          }
          const main = el.closest('main');
          const clip = main?.getBoundingClientRect() || { left:0, top:0, right:innerWidth, bottom:innerHeight };
          const target = (surface.group === 'PB' || surface.group === 'RP')
            ? el.querySelector('.efhc-energy-progress-track') || el : el;
          const anchor = target.getBoundingClientRect();
          const progress = surface.group === 'PB' || surface.group === 'RP';
          const node = nodes.current.get(surface.id);
          const width = node?.getBoundingClientRect().width || Math.min(rect.width - 4, getInterfaceVariantAuthoredSlotCount(surface.group) * 10);
          const height = node?.getBoundingClientRect().height || (progress ? 4 : 7);
          const left = anchor.left + anchor.width / 2;
          const candidates = progress ? [anchor.bottom + height / 2 + .5, anchor.bottom + height / 2 + 1]
            : surface.group === 'HS' ? [rect.top + height / 2 + 1, rect.top - 8]
            : surface.group === 'BN' ? [rect.top + height / 2 + 1, rect.bottom - height / 2 - 1, rect.bottom + height / 2, rect.top - 8]
            : [rect.top + height / 2 + 3, rect.bottom - height / 2 - 3, rect.top - 8, rect.bottom + 8];
          const band = { left:left - width / 2, right:left + width / 2,
            top:Math.min(...candidates) - height, bottom:Math.max(...candidates) + height };
          const obstacles = occupied(el.parentElement || el, band, surface.group === 'BN');
          for (const top of candidates) {
            const box = {left:left-width/2, right:left+width/2, top:top-height/2, bottom:top+height/2};
            if (box.left < clip.left || box.right > clip.right || box.top < Math.max(0,clip.top) || box.bottom > Math.min(innerHeight,clip.bottom)) continue;
            if (obstacles.some(other => intersects(box, other))) continue;
            // Already placed indicators are occupied space too.
            if (next.some(other => Math.abs(other.top - top) < height + 2 && Math.abs(other.left - left) < width)) continue;
            next.push({...surface,left,top,placementKind:progress?'progress-below':top>rect.top&&top<rect.bottom?'inside':'adjacent'});
            break;
          }
        }
        setPositions(next);
      });
    };
    update();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
    props.surfaces.forEach(surface => observer?.observe(surface.element));
    document.querySelectorAll('[data-user-indicator-dock],.efhc-game-shell_main').forEach(el => observer?.observe(el));
    window.addEventListener('resize',update); window.addEventListener('scroll',update,true);
    return () => {cancelAnimationFrame(frame);observer?.disconnect();window.removeEventListener('resize',update);window.removeEventListener('scroll',update,true)};
  }, [props.mode,props.effective,props.activeGroups,props.surfaces]);
  if (!mounted || props.mode !== 'editing') return null;
  return createPortal(positions.map(surface => <div
    key={surface.id}
    ref={node => { if(node) nodes.current.set(surface.id,node); else nodes.current.delete(surface.id) }}
    className="efhc-interface-variant-dots" aria-hidden="true"
    data-indicator-group={surface.group} data-indicator-placement={surface.placementKind}
    style={{left:surface.left,top:surface.top}}
  ><VariantIndicatorDots group={surface.group} effective={props.effective}/></div>),document.body);
}
