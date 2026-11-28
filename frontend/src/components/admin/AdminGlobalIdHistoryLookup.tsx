import React, { useEffect, useState } from "react";

import { AdminCompactOperationList } from "./AdminCompactOperationList";
import { AdminListExpandControl, useAdminListWindow } from "./AdminListWindow";
import { AdminPanelChrome } from "./AdminDashboardUiKit";
import { Button } from "../ui/Button";
import { TelegramEmptyState } from "../ui/telegram/TelegramEmptyState";
import {
  adminPath,
  ADMIN_USERS_GLOBAL_ID_HISTORY_PATH,
} from "../../lib/api/generated/adminSeams";
import { adminUiErrorMessage } from "../../lib/adminError";
import { formatD8ToHuman } from "../../lib/format";
import { useT } from "../../hooks/useT";
import { useAdminPageGlobalIdSelection } from "../../hooks/admin/useAdminPageGlobalIdSelection";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import {
  profileHistoryPageSchema,
  type ProfileHistoryItem,
} from "../../services/profile.service";
import { parseGlobalId, type GlobalId } from "../../types/identity";

function historyOperation(item: ProfileHistoryItem): string {
  const source = String(item.source || "Событие");
  const kind = String(item.kind || "операция");
  return `${source} · ${kind}`;
}

function historyAmount(item: ProfileHistoryItem): string {
  if (item.amount_efhc) return `${formatD8ToHuman(item.amount_efhc)} EFHC`;
  if (item.amount_asset) return `${item.amount_asset} ${item.asset || ""}`.trim();
  return "—";
}

export function AdminGlobalIdHistoryLookup() {
  const adminApiRequest = useAdminLinkedTransport();
  const t = useT();
  const { selectedGlobalId, restored, rememberGlobalId, clearGlobalId } = useAdminPageGlobalIdSelection("reports");
  const [input, setInput] = useState("");
  const [searchedId, setSearchedId] = useState<GlobalId | null>(null);
  const [items, setItems] = useState<ProfileHistoryItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const historyWindow = useAdminListWindow(
    items,
    `admin-reports-global-id-history:${searchedId || "none"}`,
  );

  async function loadHistory(globalId: GlobalId, nextCursor: string | null = null, append = false) {
    setLoading(true);
    setError(null);
    try {
      const base = adminPath(
        ADMIN_USERS_GLOBAL_ID_HISTORY_PATH,
        { global_id: globalId },
      );
      const query = new URLSearchParams({ limit: "20" });
      if (nextCursor) query.set("cursor", nextCursor);
      const raw = await adminApiRequest<unknown>(
        `${base}?${query.toString()}`,
        "GET",
      );
      const page = profileHistoryPageSchema.parse(raw);
      setItems((current) => append ? [...current, ...page.items] : page.items);
      setCursor(page.next_cursor);
      setSearchedId(globalId);
      rememberGlobalId(globalId);
      if (append) historyWindow.revealServerPage();
      else historyWindow.collapse();
    } catch (e: unknown) {
      if (!append) {
        setItems([]);
        setCursor(null);
      }
      setError(adminUiErrorMessage(e, t));
    } finally {
      setLoading(false);
    }
  }

  function submit(rawInput?: string) {
    try {
      const globalId = parseGlobalId(String(rawInput ?? input).trim());
      void loadHistory(globalId);
    } catch {
      setSearchedId(null);
      setItems([]);
      setCursor(null);
      setError("Global ID должен содержать ровно 10 цифр.");
    }
  }

  useEffect(() => {
    if (!restored || !selectedGlobalId) return;
    const remembered = String(selectedGlobalId);
    setInput(remembered);
    submit(remembered);
  }, [restored]);

  function resetSearch() {
    clearGlobalId();
    setInput("");
    setSearchedId(null);
    setItems([]);
    setCursor(null);
    setError(null);
    historyWindow.collapse();
  }

  return (
    <AdminPanelChrome
      title="Список только по Global ID"
      subtitle="Общий поток строк скрыт. Точечная история загружается только после поиска конкретного Global ID."
      status={error ? "error" : loading ? "loading" : searchedId ? "success" : "empty"}
      source="GET /admin/users/{global_id}/history"
    >
      <div className="grid grid-cols-2 items-end" data-admin-selected-global-id={selectedGlobalId || "none"} data-admin-search-geometry="v425-v430" style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem" }}>
        <input
          className="efhc-input col-span-2 w-full"
          inputMode="numeric"
          maxLength={10}
          value={input}
          onChange={(event) => setInput(event.target.value.replace(/\D/g, "").slice(0, 10))}
          onKeyDown={(event) => {
            if (event.key === "Enter") submit();
          }}
          placeholder="Global ID — 10 цифр"
          aria-label="Global ID для точечного просмотра истории"
          style={{ minHeight: "2.25rem", padding: ".52rem .62rem", borderRadius: ".68rem" }}
        />
        <Button
          className="w-full min-w-0"
          variant="secondary"
          disabled={loading || (!input && !selectedGlobalId)}
          onClick={resetSearch}
          style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
        >
          Сбросить
        </Button>
        <Button
          className="w-full min-w-0"
          variant="secondary"
          disabled={loading || input.length !== 10}
          onClick={() => submit()}
          style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
        >
          {loading ? "Поиск…" : "Найти"}
        </Button>
      </div>

      {error ? <TelegramEmptyState title="Не удалось получить историю" detail={error} /> : null}
      {!searchedId && !error ? (
        <p className="mt-3 text-sm text-slate-400">
          Полный экранный список отключён. Для операционной проверки введите Global ID.
        </p>
      ) : null}

      {searchedId && !loading && !error && items.length === 0 ? (
        <TelegramEmptyState title={`Для Global ID ${searchedId} событий не найдено`} />
      ) : null}

      {searchedId && items.length ? (
        <div className="mt-3">
          <AdminCompactOperationList
            rows={historyWindow.visibleItems.map((item) => ({
              id: String(item.id),
              operation: historyOperation(item),
              amount: historyAmount(item),
              subject: item.reason || `Global ID ${searchedId}`,
              time: item.occurred_at,
            }))}
          />
          <AdminListExpandControl
            shown={historyWindow.visibleCount}
            total={historyWindow.totalCount}
            hasServerMore={Boolean(cursor)}
            loadingMore={loading}
            onExpand={() => {
              if (historyWindow.hasMore) historyWindow.expand();
              else if (cursor) void loadHistory(searchedId, cursor, true);
            }}
            onCollapse={historyWindow.collapse}
          />
        </div>
      ) : null}
    </AdminPanelChrome>
  );
}
