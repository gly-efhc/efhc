import React, { useEffect } from "react";
import { useRouter } from "next/router";
import AdminUsersPage from "./users";

export default function AdminUserHistoryPage() {
  const router = useRouter();

  useEffect(() => {
    if (!router.isReady) return;
    const globalId = String(router.query.global_id || "").trim();
    const query: Record<string, string> = { section: "history" };
    if (/^\d{10}$/.test(globalId)) query.global_id = globalId;
    void router.replace({ pathname: "/admin/users", query });
  }, [router]);

  return <AdminUsersPage />;
}
