import { useCallback, useEffect, useMemo, useState } from "react";

import { parseGlobalId, type GlobalId } from "../../types/identity";

const ADMIN_PAGE_GLOBAL_ID_PREFIX = "efhc:admin:page-global-id:";
const ADMIN_PAGE_GLOBAL_ID_EVENT = "efhc:admin-page-global-id-selection";

type AdminPageGlobalIdSelectionEventDetail = {
  storageKey: string;
  value: string | null;
};

type AdminPageGlobalIdSelectionOptions = {
  storageKey?: string;
};

export function adminPageGlobalIdSelectionStorageKey(pageKey: string): string {
  return `${ADMIN_PAGE_GLOBAL_ID_PREFIX}${pageKey}`;
}

export function useAdminPageGlobalIdSelection(
  pageKey: string,
  options: AdminPageGlobalIdSelectionOptions = {},
) {
  const storageKey = useMemo(
    () => options.storageKey || adminPageGlobalIdSelectionStorageKey(pageKey),
    [options.storageKey, pageKey],
  );
  const [selectedGlobalId, setSelectedGlobalId] = useState<GlobalId | null>(null);
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const restore = (rawValue: string | null) => {
      const raw = String(rawValue || "").trim();
      if (raw) {
        try {
          setSelectedGlobalId(parseGlobalId(raw));
        } catch {
          window.sessionStorage.removeItem(storageKey);
          setSelectedGlobalId(null);
        }
      } else {
        setSelectedGlobalId(null);
      }
      setRestored(true);
    };

    const onSelectionChange = (event: Event) => {
      const detail = (event as CustomEvent<AdminPageGlobalIdSelectionEventDetail>).detail;
      if (!detail || detail.storageKey !== storageKey) return;
      restore(detail.value);
    };

    restore(window.sessionStorage.getItem(storageKey));
    window.addEventListener(ADMIN_PAGE_GLOBAL_ID_EVENT, onSelectionChange);
    return () => window.removeEventListener(ADMIN_PAGE_GLOBAL_ID_EVENT, onSelectionChange);
  }, [storageKey]);

  const rememberGlobalId = useCallback((value: string | GlobalId): GlobalId => {
    const parsed = parseGlobalId(String(value).trim());
    setSelectedGlobalId(parsed);
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(storageKey, String(parsed));
      window.dispatchEvent(new CustomEvent<AdminPageGlobalIdSelectionEventDetail>(
        ADMIN_PAGE_GLOBAL_ID_EVENT,
        { detail: { storageKey, value: String(parsed) } },
      ));
    }
    return parsed;
  }, [storageKey]);

  const clearGlobalId = useCallback(() => {
    setSelectedGlobalId(null);
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem(storageKey);
      window.dispatchEvent(new CustomEvent<AdminPageGlobalIdSelectionEventDetail>(
        ADMIN_PAGE_GLOBAL_ID_EVENT,
        { detail: { storageKey, value: null } },
      ));
    }
  }, [storageKey]);

  return {
    selectedGlobalId,
    restored,
    rememberGlobalId,
    clearGlobalId,
    storageKey,
  } as const;
}
