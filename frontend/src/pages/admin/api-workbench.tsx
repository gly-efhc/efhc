import React, { useMemo, useState } from "react";

import { AdminPage } from "../../components/admin/AdminPage";
import { AdminListExpandControl, useAdminListWindow } from "../../components/admin/AdminListWindow";
import { AdminSectionCard } from "../../components/admin/AdminSectionCard";
import { AdminStatCard } from "../../components/admin/AdminStatCard";
import { Button } from "../../components/ui/Button";
import {
  ADMIN_ROUTE_CATALOG,
  ADMIN_ROUTE_CATALOG_COUNT,
  type AdminRouteCatalogItem,
} from "../../lib/adminRouteCatalog";
import { adminUiErrorMessage } from "../../lib/adminError";
import { newIdempotencyKey } from "../../lib/idempotency";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";

const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function defaultBody(method: string): string {
  return WRITE_METHODS.has(method) ? "{}" : "";
}

export default function AdminApiWorkbenchPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const selected = ADMIN_ROUTE_CATALOG[selectedIndex] || ADMIN_ROUTE_CATALOG[0];
  const [pathValue, setPathValue] = useState(selected?.path || "");
  const [bodyValue, setBodyValue] = useState(defaultBody(selected?.method || "GET"));
  const [allowWrite, setAllowWrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState("Выберите маршрут и выполните запрос.");
  const [filter, setFilter] = useState("all");

  const modules = useMemo(
    () => ["all", ...Array.from(new Set(ADMIN_ROUTE_CATALOG.map((row) => row.module)))],
    [],
  );
  const visible = useMemo(
    () => filter === "all" ? ADMIN_ROUTE_CATALOG : ADMIN_ROUTE_CATALOG.filter((row) => row.module === filter),
    [filter],
  );
  const routeWindow = useAdminListWindow(visible, filter);

  function selectRoute(row: AdminRouteCatalogItem) {
    const index = ADMIN_ROUTE_CATALOG.indexOf(row);
    setSelectedIndex(index);
    setPathValue(row.path);
    setBodyValue(defaultBody(row.method));
    setAllowWrite(false);
  }

  async function execute() {
    if (!selected) return;
    const isWrite = WRITE_METHODS.has(selected.method);
    if (isWrite && !allowWrite) {
      setResult("Запись заблокирована. Подтвердите разрешение на изменение данных для этого запроса.");
      return;
    }
    if (/\{[^}]+\}/.test(pathValue)) {
      setResult("Замените параметры в фигурных скобках реальными значениями перед выполнением.");
      return;
    }
    if (
      selected.method === "PATCH"
      && /^\/admin\/panels\/\d+\/(?:activate|deactivate)$/.test(pathValue)
    ) {
      setResult(
        "Запрос заблокирован правилом безопасности v184: EFHC_Bot_v174.63 не принимает обязательную причину администратора для защитного изменения состояния Панели. Используйте Admin → Панели; операция остаётся заблокированной до обновления основного API.",
      );
      return;
    }
    let body: unknown = undefined;
    if (isWrite) {
      try {
        body = bodyValue.trim() ? JSON.parse(bodyValue) : {};
      } catch {
        setResult("Body должен быть корректным JSON.");
        return;
      }
    }
    setBusy(true);
    try {
      const out = await adminApiRequest<unknown>(pathValue, selected.method, {
        ...(isWrite ? { body } : {}),
        ...(isWrite ? { idempotencyKey: newIdempotencyKey() } : {}),
      });
      setResult(JSON.stringify(out, null, 2));
    } catch (error) {
      setResult(adminUiErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdminPage
      title="API Workbench — техническая лаборатория"
      subtitle="Инструмент для разработчика или точечной диагностики: позволяет проверить один известный Admin API напрямую. Для обычной ежедневной работы администратора не нужен."
      backHref="/admin"
    >
      <div className="contents" data-admin-api-workbench-surface="v352" data-eam-family="EAM-ADMIN-025">
      <AdminSectionCard
        title="Зачем нужен этот раздел"
        subtitle="Workbench похож на встроенный безопасный Postman: он помогает проверить, отвечает ли конкретная административная функция, когда обычная кнопка или страница ведёт себя непонятно."
      >
        <div className="grid gap-2 text-sm">
          <div><strong>Что показывает:</strong> реальные Admin API contracts из зафиксированной схемы OpenAPI — метод, путь и ответ.</div>
          <div><strong>Когда использовать:</strong> только при технической диагностике конкретной функции.</div>
          <div><strong>Когда не использовать:</strong> для обычных переводов, выплат, магазина и пользователей есть отдельные понятные страницы.</div>
          <div><strong>Write-запросы:</strong> по умолчанию заблокированы и требуют отдельного разрешения на каждый запрос.</div>
        </div>
      </AdminSectionCard>

      <div className="grid gap-3 md:grid-cols-3">
        <AdminStatCard label="Контракты Admin API" value={String(ADMIN_ROUTE_CATALOG_COUNT)} meta="из зафиксированной схемы OpenAPI" tone="success" />
        <AdminStatCard label="Текущий метод" value={selected?.method || "—"} meta="выбранный contract" tone="neutral" />
        <AdminStatCard label="Режим записи" value={allowWrite ? "РАЗРЕШЁН" : "ЗАБЛОКИРОВАН"} meta="включается отдельно для каждого write-запроса" tone={allowWrite ? "warning" : "success"} />
      </div>

      <AdminSectionCard title="Известные функции Admin API" subtitle="Выберите модуль и конкретную функцию. Список строится только из зафиксированной схемы OpenAPI и не принимает произвольные маршруты.">
        <div className="flex flex-wrap gap-2 mb-3">
          {modules.map((module) => (
            <Button key={module} variant={filter === module ? "primary" : "secondary"} onClick={() => setFilter(module)}>
              {module === "all" ? "Все" : module}
            </Button>
          ))}
        </div>
        <div className="grid gap-2 max-h-[28rem] overflow-auto">
          {routeWindow.visibleItems.map((row) => (
            <button
              key={`${row.method} ${row.path}`}
              type="button"
              onClick={() => selectRoute(row)}
              data-selected={String(ADMIN_ROUTE_CATALOG.indexOf(row) === selectedIndex)}
              className="efhc-admin-api-route-row rounded-2xl border border-white/10 bg-white/[0.035] p-3 text-left hover:bg-white/[0.06]"
            >
              <div className="flex items-center gap-2 text-xs"><strong>{row.method}</strong><span>{row.module}</span></div>
              <code className="mt-1 block break-all text-xs text-[color:var(--tg-hint)]">{row.path}</code>
            </button>
          ))}
        </div>
        <AdminListExpandControl
          shown={routeWindow.visibleCount}
          total={routeWindow.totalCount}
          onExpand={routeWindow.expand}
          onCollapse={routeWindow.collapse}
          className="mt-3"
        />
      </AdminSectionCard>

      <AdminSectionCard title="Техническая проверка" subtitle="Подставьте реальный ID вместо параметра в скобках. Изменяющие запросы требуют отдельного подтверждения и не предназначены для обычного операторского сценария.">
        <div className="grid gap-3">
          <label className="grid gap-1 text-sm">
            <span>HTTP path</span>
            <input className="efhc-input" value={pathValue} onChange={(event) => setPathValue(event.target.value)} />
          </label>
          {selected && WRITE_METHODS.has(selected.method) ? (
            <>
              <label className="grid gap-1 text-sm">
                <span>JSON body</span>
                <textarea className="efhc-input min-h-32 font-mono text-xs" value={bodyValue} onChange={(event) => setBodyValue(event.target.value)} />
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={allowWrite} onChange={(event) => setAllowWrite(event.target.checked)} />
                Разрешить изменение данных этим запросом
              </label>
            </>
          ) : null}
          <div><Button onClick={() => void execute()} disabled={busy}>{busy ? "Выполняется…" : "Выполнить"}</Button></div>
          <pre className="efhc-admin-api-result max-h-96 overflow-auto rounded-2xl border border-white/10 bg-black/20 p-3 text-xs whitespace-pre-wrap break-words">{result}</pre>
        </div>
      </AdminSectionCard>
      </div>
    </AdminPage>
  );
}
