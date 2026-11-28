import React from "react";

import { AdminPage } from "../../components/admin/AdminPage";
import { AdminVipNftRequestsPanel } from "../../components/admin/AdminVipNftRequestsPanel";

export default function AdminVipNftPage() {
  return (
    <AdminPage title="Выдача / VIP NFT" backHref="/admin">
      <div className="space-y-4" data-admin-vip-nft-page="payout-modal-v211">
        <AdminVipNftRequestsPanel />
      </div>
    </AdminPage>
  );
}
