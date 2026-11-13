import React from "react";
import { useRouter } from "next/router";
import { QuietPageSurface } from "../components/QuietPageSurface";
import { useT } from "../hooks/useT";

/** No technical error page may replace the app's navigation and layout. */
export default function ServerFallbackPage() {
  const router = useRouter();
  const t = useT();
  const pathname = router.pathname === "/500" ? "/" : router.pathname;
  return <QuietPageSurface pathname={pathname} t={t} />;
}
