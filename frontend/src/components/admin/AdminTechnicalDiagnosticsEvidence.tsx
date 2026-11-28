import React from "react";

import { AdminDiagnosticsTechnicalBoundaryPanel } from "./AdminDiagnosticsTechnicalBoundaryPanel";
import { AdminRuntimePosturePanel } from "./AdminRuntimePosturePanel";
import { AdminSectionCard } from "./AdminSectionCard";
import { SurfaceFactsStrip } from "../ui/SurfaceFactsStrip";

/**
 * Secondary developer evidence. It stays collapsed so the normal Admin surface
 * remains human-friendly while release guards keep the technical boundaries
 * available to an engineer during diagnosis.
 */
export function AdminTechnicalDiagnosticsEvidence() {
  return (
    <details className="efhc-admin-system-technical-details rounded-3xl border border-[color:var(--tg-hint)]/20 p-4">
      <summary className="cursor-pointer text-sm font-semibold">
        Технические сведения для разработчика
      </summary>
      <div className="mt-4 space-y-4">
        <AdminSectionCard
          title="Когда открывать этот блок"
          subtitle="Только если понятные карточки состояния показывают проблему и разработчику нужны маршруты и границы release-контуров."
        >
          <p className="text-sm text-[color:var(--tg-hint)]">
            Обычные финансовые действия здесь не выполняются. Не повторяйте денежную операцию только потому, что технический API-маршрут показал предупреждение.
          </p>
        </AdminSectionCard>

        <AdminRuntimePosturePanel />
        <AdminDiagnosticsTechnicalBoundaryPanel />

        <AdminSectionCard
          title="Диагностика HUB и внешнего Магазина"
          subtitle="Техническая граница публичного HUB."
        >
          <SurfaceFactsStrip
            title="Переход HUB"
            items={[
              { label: "переход HUB · /hub/efhc-handoff", tone: "connected" },
              { label: "данные Магазина · /hub/shop-truth", tone: "warning" },
              { label: "публичный HUB · только два действия", tone: "connected" },
            ]}
          />
        </AdminSectionCard>

        <AdminSectionCard
          title="Диагностика оплаты внешнего Магазина"
          subtitle="Техническая граница публичной витрины."
        >
          <SurfaceFactsStrip
            title="API внешнего Магазина"
            items={[
              { label: "каталог · /shopfront/catalog", tone: "connected" },
              { label: "создание оплаты · /shopfront/create-intent", tone: "connected" },
              { label: "статус оплаты · /shopfront/intent-status", tone: "warning" },
              { label: "кошелёк и комментарий · скрыты из публичного интерфейса", tone: "warning" },
            ]}
          />
        </AdminSectionCard>
      </div>
    </details>
  );
}
