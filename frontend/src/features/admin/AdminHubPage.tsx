import React, { useEffect, useMemo, useState } from "react";

import { AdminPage } from "../../components/admin/AdminPage";
import { AdminSectionCard } from "../../components/admin/AdminSectionCard";
import { TelegramInfoBlock } from "../../components/ui/telegram/TelegramInfoBlock";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import {
  adminPath,
  ADMIN_HUB_LINKS_LINK_ID_PATH,
  ADMIN_HUB_LINKS_LINK_ID_TOGGLE_PATH,
  ADMIN_HUB_LINKS_PATH,
  ADMIN_HUB_LINKS_REORDER_PATH,
  type AdminHubLink,
} from "../../lib/api/generated/adminSeams";
import { adminSafeLoadError } from "../../lib/adminError";
import { newIdempotencyKey } from "../../lib/idempotency";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import { useT } from "../../hooks/useT";
import type { DbId } from "../../types/db-id";

type HubForm = { title: string; url: string };
type HubMutationMode = "create" | "edit" | null;

const EMPTY_FORM: HubForm = { title: "", url: "" };
const FIXED_HUB_TITLES: Record<string, string> = {
  efhc_buy: "Магазин", vip_getgems: "EFHC VIP NFT",
  efhc_ceo: "CEO EFHC", efhc_admin: "Админ",
};
const isFixedHub = (item: AdminHubLink) => Object.prototype.hasOwnProperty.call(FIXED_HUB_TITLES, item.code);
const fixedHubOrder = (item: AdminHubLink) => ["efhc_buy", "vip_getgems", "efhc_ceo", "efhc_admin"].indexOf(item.code);


function isAllowedHubUrl(value: string): boolean {
  const url = value.trim();
  return url.startsWith("/") || /^https:\/\//i.test(url);
}

function transportForUrl(url: string): {
  target_kind: string;
  open_mode: string;
} {
  if (url === "/hub/efhc-handoff") {
    return { target_kind: "backend_handoff", open_mode: "same_app" };
  }
  if (url.startsWith("/")) {
    return { target_kind: "internal_route", open_mode: "same_app" };
  }
  return { target_kind: "external_url", open_mode: "external_browser" };
}

function generatedHubCode(): string {
  return `hub_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export default function AdminHubPage() {
  const t = useT();
  const adminApiRequest = useAdminLinkedTransport();
  const [items, setItems] = useState<AdminHubLink[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<HubMutationMode>(null);
  const [selectedId, setSelectedId] = useState<DbId | null>(null);
  const [form, setForm] = useState<HubForm>(EMPTY_FORM);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const rows = await adminApiRequest<AdminHubLink[]>(ADMIN_HUB_LINKS_PATH, "GET");
      setItems(Array.isArray(rows) ? rows : []);
    } catch (e: any) {
      setError(adminSafeLoadError(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const activeItems = useMemo(
    () => items
      .filter((item) => item.title.trim() && item.url.trim())
      .sort((a, b) => {
        const af = fixedHubOrder(a), bf = fixedHubOrder(b);
        if (af >= 0 && bf >= 0) return af - bf;
        if (af >= 0) return -1;
        if (bf >= 0) return 1;
        return a.sort_order - b.sort_order || Number(a.id) - Number(b.id);
      }),
    [items],
  );

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId],
  );

  function openCreate() {
    setSelectedId(null);
    setForm(EMPTY_FORM);
    setMode("create");
  }

  function openEdit(item: AdminHubLink) {
    setSelectedId(item.id);
    setForm({ title: isFixedHub(item) ? FIXED_HUB_TITLES[item.code] : item.title, url: item.url });
    setMode("edit");
  }

  const formReady = Boolean(form.title.trim() && isAllowedHubUrl(form.url));

  async function submit() {
    if (!formReady) return;
    setBusy(true);
    setError(null);
    try {
      const title = form.title.trim();
      const url = form.url.trim();
      const transport = transportForUrl(url);
      if (mode === "create") {
        const maxOrder = Math.max(0, ...items.map((item) => Number(item.sort_order || 0)));
        await adminApiRequest<AdminHubLink>(ADMIN_HUB_LINKS_PATH, "POST", {
          body: {
            code: generatedHubCode(),
            title,
            subtitle: null,
            url,
            ...transport,
            sort_order: maxOrder + 10,
            is_active: true,
            icon_key: "link",
          },
          idempotencyKey: newIdempotencyKey(),
        });
      } else if (mode === "edit" && selected) {
        await adminApiRequest<AdminHubLink>(
          adminPath(ADMIN_HUB_LINKS_LINK_ID_PATH, { link_id: selected.id }),
          "PUT",
          {
            body: {
              title,
              subtitle: selected.subtitle,
              url,
              ...transport,
              sort_order: selected.sort_order,
              is_active: selected.is_active,
              icon_key: selected.icon_key || "link",
            },
            idempotencyKey: newIdempotencyKey(),
          },
        );
      }
      setMode(null);
      await load();
    } catch (e: any) {
      setError(adminSafeLoadError(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(item: AdminHubLink) {
    if (typeof window !== "undefined" && !window.confirm(`Удалить «${item.title}» из HUB?`)) return;
    setBusy(true);
    setError(null);
    try {
      if (isFixedHub(item)) throw new Error("Защищённые ссылки нельзя удалять");
      await adminApiRequest<void>(
        adminPath(ADMIN_HUB_LINKS_LINK_ID_PATH, { link_id: item.id }),
        "DELETE",
        { idempotencyKey: newIdempotencyKey() },
      );
      setMode(null);
      await load();
    } catch (e: any) {
      setError(adminSafeLoadError(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggleVisibility(item: AdminHubLink) {
    setBusy(true);
    setError(null);
    try {
      await adminApiRequest<AdminHubLink>(
        adminPath(ADMIN_HUB_LINKS_LINK_ID_TOGGLE_PATH, { link_id: item.id }),
        "POST", { body: { is_active: !item.is_active }, idempotencyKey: newIdempotencyKey() },
      );
      await load();
    } catch (e: any) { setError(adminSafeLoadError(e)); }
    finally { setBusy(false); }
  }

  async function moveToPosition(item: AdminHubLink, rawPosition: number) {
    if (isFixedHub(item)) return;
    const from = activeItems.findIndex((row) => row.id === item.id);
    const to = Math.max(4, Math.min(activeItems.length - 1, rawPosition - 1));
    if (from < 0 || from === to || busy) return;
    const reordered = [...activeItems];
    const [moved] = reordered.splice(from, 1);
    reordered.splice(to, 0, moved);
    setBusy(true);
    setError(null);
    try {
      await adminApiRequest<AdminHubLink[]>(ADMIN_HUB_LINKS_REORDER_PATH, "POST", {
        body: { items: reordered.map((row, index) => ({ id: row.id, sort_order: isFixedHub(row) ? (fixedHubOrder(row) + 1) * 10 : Math.max(50, (index + 1) * 10) })) },
        idempotencyKey: newIdempotencyKey(),
      });
      await load();
    } catch (e: any) {
      setError(adminSafeLoadError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdminPage title={t("admin.hub")} backHref="/admin">
      <div
        className="space-y-4"
        data-admin-hub-surface="shop-style-list-modal-v252"
        data-admin-hub-fields="title-url-only"
        data-admin-hub-position-control="number-in-list"
        data-admin-hub-empty-slots="forbidden"
      >
        <AdminSectionCard
          title="Центр ссылок"
          subtitle="Нажмите строку ссылки — редактор откроется отдельным окном. Номер позиции определяет порядок кнопок в HUB."
          actions={(
            <Button onClick={openCreate} disabled={busy || loading}>
              + Добавить ссылку
            </Button>
          )}
        >
          {error ? <TelegramInfoBlock title="Статус раздела">{error}</TelegramInfoBlock> : null}

          <div className="efhc-admin-hub-list-v252" data-admin-hub-active-list="true">
            {activeItems.map((item, index) => (
              <div className="efhc-admin-hub-row-v252" key={String(item.id)}>
                <button
                  type="button"
                  className="efhc-admin-hub-row-main-v252"
                  onClick={() => openEdit(item)}
                  disabled={busy}
                  aria-label={`Редактировать ${item.title}`}
                >
                  <span className="efhc-admin-hub-row-copy-v252">
                    <strong>{isFixedHub(item) ? FIXED_HUB_TITLES[item.code] : item.title}{!item.is_active ? " (скрыта)" : ""}</strong>
                    <small>{item.url}</small>
                  </span>
                  <span aria-hidden="true" className="efhc-admin-hub-row-chevron-v252">›</span>
                </button>
                <label className="efhc-admin-hub-position-v252">
                  <span>Позиция</span>
                  <select
                    value={index + 1}
                    onChange={(event) => { void moveToPosition(item, Number(event.target.value)); }}
                    disabled={busy || isFixedHub(item) || activeItems.length < 5}
                    aria-label={`Позиция ссылки ${item.title}`}
                  >
                    {activeItems.map((_, optionIndex) => (
                      <option key={optionIndex + 1} value={optionIndex + 1} disabled={!isFixedHub(item) && optionIndex < 4}>
                        {String(optionIndex + 1).padStart(2, "0")}
                      </option>
                    ))}
                  </select>
                </label>
                <Button variant="secondary" onClick={() => { void toggleVisibility(item); }} disabled={busy}>
                  {item.is_active ? "Скрыть" : "Показать"}
                </Button>
              </div>
            ))}
            {!loading && activeItems.length === 0 ? (
              <div className="py-4 text-center text-xs efhc-text-muted">Ссылок пока нет. Добавьте первую кнопку HUB.</div>
            ) : null}
            {loading ? <div className="py-4 text-center text-xs efhc-text-muted">{t("common.loading")}</div> : null}
          </div>
        </AdminSectionCard>
      </div>

      <Modal
        open={mode !== null}
        onClose={() => { if (!busy) setMode(null); }}
        closeDisabled={busy}
        title={mode === "create" ? "Добавить ссылку" : selected ? `Редактор: ${selected.title}` : "Редактор ссылки"}
      >
        <div className="grid gap-3" data-admin-hub-editor-modal="v252">
          <label className="grid gap-1">
            <span className="text-xs text-[color:var(--tg-hint)]">Название</span>
            <input className="efhc-input" readOnly={Boolean(selected && isFixedHub(selected))} value={form.title} onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))} placeholder="Название кнопки" />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-[color:var(--tg-hint)]">Ссылка</span>
            <input className="efhc-input" value={form.url} onChange={(event) => setForm((prev) => ({ ...prev, url: event.target.value }))} placeholder="https://… или /раздел" />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => { void submit(); }} disabled={!formReady || busy}>
              {mode === "create" ? "Добавить" : "Сохранить"}
            </Button>
            {mode === "edit" && selected && !isFixedHub(selected) ? (
              <Button variant="secondary" onClick={() => { void remove(selected); }} disabled={busy}>Удалить</Button>
            ) : null}
            <Button variant="secondary" onClick={() => setMode(null)} disabled={busy}>Закрыть</Button>
          </div>
        </div>
      </Modal>
    </AdminPage>
  );
}
