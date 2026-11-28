import dynamic from "next/dynamic";
import React from "react";

type AdminPageComponent = React.ComponentType<Record<string, unknown>>;

function proofPage(
  loader: () => Promise<{ default: AdminPageComponent }>,
): AdminPageComponent {
  return dynamic(loader, {
    ssr: false,
    loading: () => (
      <div className="efhc-admin-proof-loading">
        Загрузка раздела администратора…
      </div>
    ),
  }) as AdminPageComponent;
}

const ADMIN_PROOF_COMPONENTS: Record<string, AdminPageComponent> = {
  "/admin": proofPage(() => import("../pages/admin")),
  "/admin/ads": proofPage(() => import("../pages/admin/ads")),
  "/admin/api-workbench": proofPage(() => import("../pages/admin/api-workbench")),
  "/admin/emergency": proofPage(() => import("../pages/admin/emergency")),
  "/admin/bonuses": proofPage(() => import("../pages/admin/bonuses")),
  "/admin/bank": proofPage(() => import("../pages/admin/bank")),
  "/admin/diagnostics": proofPage(
    () => import("../pages/admin/diagnostics"),
  ),
  "/admin/efhc-deposits": proofPage(
    () => import("../pages/admin/efhc-deposits"),
  ),
  "/admin/hub": proofPage(() => import("../pages/admin/hub")),
  "/admin/logs": proofPage(() => import("../pages/admin/logs")),
  "/admin/panels": proofPage(
    () => import("../pages/admin/panels"),
  ),
  "/admin/referrals": proofPage(
    () => import("../pages/admin/referrals"),
  ),
  "/admin/reports": proofPage(
    () => import("../pages/admin/reports"),
  ),
  "/admin/sale-packages": proofPage(
    () => import("../pages/admin/sale-packages"),
  ),
  "/admin/shop": proofPage(() => import("../pages/admin/shop")),
  "/admin/system": proofPage(
    () => import("../pages/admin/system"),
  ),
  "/admin/tasks": proofPage(() => import("../pages/admin/tasks")),
  "/admin/users": proofPage(() => import("../pages/admin/users")),
  "/admin/vip-nft": proofPage(() => import("../pages/admin/vip-nft")),
  "/admin/user-history": proofPage(() => import("../pages/admin/user-history")),
  "/admin/withdrawals": proofPage(
    () => import("../pages/admin/withdrawals"),
  ),
};

export function AdminVisualProofRouter(props: {
  path: string;
  pageProps: Record<string, unknown>;
}) {
  const Component = ADMIN_PROOF_COMPONENTS[props.path]
    || ADMIN_PROOF_COMPONENTS["/admin"];
  return (
    <div
      data-admin-visual-proof-route={props.path}
      data-admin-visual-proof-harness="managed-urlblocklist"
      data-efhc-admin-readonly-demo={process.env.NEXT_PUBLIC_EFHC_PAGES_PREVIEW === "1" ? "true" : undefined}
    >
      <Component {...props.pageProps} />
    </div>
  );
}
