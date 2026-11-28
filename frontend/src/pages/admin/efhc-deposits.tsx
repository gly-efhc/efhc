import React from "react";

import { AdminPage } from "../../components/admin/AdminPage";
import { AdminTonInboxHumanPanel } from "../../components/admin/AdminTonInboxHumanPanel";

export default function AdminEfhcDepositsPage() {
  return (
    <AdminPage title="Входящие платежи EFHC" backHref="/admin">
      <div data-admin-efhc-deposits-surface="v348">
        <AdminTonInboxHumanPanel />
      </div>
    </AdminPage>
  );
}
