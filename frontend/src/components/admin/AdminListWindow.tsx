import React, { useEffect, useMemo, useState } from "react";

import { Button } from "../ui/Button";

export const ADMIN_LIST_PAGE_SIZE = 20;

export function useAdminListWindow<T>(
  items: readonly T[],
  resetKey: string = "default",
) {
  const [visibleCount, setVisibleCount] = useState(ADMIN_LIST_PAGE_SIZE);

  useEffect(() => {
    setVisibleCount(ADMIN_LIST_PAGE_SIZE);
  }, [resetKey]);

  const visibleItems = useMemo(
    () => items.slice(0, visibleCount),
    [items, visibleCount],
  );

  return {
    visibleItems,
    visibleCount: visibleItems.length,
    totalCount: items.length,
    hasMore: visibleCount < items.length,
    canCollapse: visibleCount > ADMIN_LIST_PAGE_SIZE,
    expand: () =>
      setVisibleCount((current) =>
        Math.min(items.length, current + ADMIN_LIST_PAGE_SIZE),
      ),
    revealServerPage: () =>
      setVisibleCount((current) => current + ADMIN_LIST_PAGE_SIZE),
    collapse: () => setVisibleCount(ADMIN_LIST_PAGE_SIZE),
  };
}

export function AdminListExpandControl(props: {
  shown: number;
  total: number;
  onExpand: () => void;
  onCollapse?: () => void;
  hasServerMore?: boolean;
  loadingMore?: boolean;
  className?: string;
}) {
  const hasLocalMore = props.shown < props.total;
  const hasMore = hasLocalMore || Boolean(props.hasServerMore);
  const canCollapse = props.shown > ADMIN_LIST_PAGE_SIZE && !hasMore;
  if (!hasMore && !canCollapse) return null;

  return (
    <div
      className={`efhc-admin-list-window-control mt-3 flex flex-wrap items-center justify-between gap-2 ${props.className || ""}`.trim()}
      data-eam-family="EAM-ADMIN-006"
      data-admin-list-page-size={ADMIN_LIST_PAGE_SIZE}
    >
      <span className="text-xs efhc-text-muted">
        Показано {props.shown}{props.hasServerMore ? "+" : ` из ${props.total}`}
      </span>
      <div className="flex flex-wrap gap-2">
        {hasMore ? (
          <Button variant="secondary" onClick={props.onExpand} disabled={props.loadingMore}>
            {props.loadingMore ? "Загрузка…" : `Ещё ${ADMIN_LIST_PAGE_SIZE}`}
          </Button>
        ) : null}
        {canCollapse && props.onCollapse ? (
          <Button variant="ghost" onClick={props.onCollapse}>
            Свернуть до {ADMIN_LIST_PAGE_SIZE}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
