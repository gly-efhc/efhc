import React from "react";

import { AdminActionGrid } from "../../components/admin/AdminActionGrid";
import { AdminPage } from "../../components/admin/AdminPage";
import { AdminSystemHealthDashboardRuntime } from "../../components/admin/AdminSystemHealthDashboardRuntime";
import { AdminTechnicalDiagnosticsEvidence } from "../../components/admin/AdminTechnicalDiagnosticsEvidence";

export function AdminSystemDiagnosticsPage(props: { routeScope: "/admin/system" | "/admin/diagnostics" }) {
  return (
    <AdminPage title="Система и диагностика" backHref="/admin">
      <div
        className="space-y-4"
        data-admin-system-simple="v192"
        data-admin-system-route={props.routeScope}
        data-eam-family={props.routeScope === "/admin/diagnostics" ? "EAM-ADMIN-027" : "EAM-ADMIN-024"}
      >
        <AdminSystemHealthDashboardRuntime />
        <AdminActionGrid
          title="Следующий шаг"
          subtitle="Для обычной проверки достаточно журнала. Технический Workbench нужен только разработчику."
          items={[
            { href: "/admin/reports", label: "Отчёты и журналы", note: "Скачать системные журналы и посмотреть сводные показатели." },
            { href: "/admin/api-workbench", label: "Admin API Workbench", note: "Точечная техническая проверка конкретного Admin API.", variant: "ghost" },
          ]}
        />
        <AdminTechnicalDiagnosticsEvidence />
      </div>
    </AdminPage>
  );
}
