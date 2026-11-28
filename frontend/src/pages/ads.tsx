import { useEffect, useMemo } from "react";
import { useRouter } from "next/router";

import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { useT } from "../hooks/useT";
import { useInterfaceVariantSurface } from "../hooks/useInterfaceVariantSurface";

// Canon: Ads is not a standalone player page.
// Keep this route only as a compatibility alias to /tasks.
export default function AdsRedirect() {
  const r = useRouter();
  const t = useT();
  const adsSurface = useInterfaceVariantSurface<HTMLDivElement>("AD", {
    dotsPlacement: "below",
  });

  const targetHref = useMemo(() => {
    const q = r.asPath.split("?")[1];
    return q ? `/tasks?${q}` : "/tasks";
  }, [r.asPath]);

  useEffect(() => {
    if (targetHref === "/tasks") {
      void r.replace("/tasks");
      return;
    }
    void r.replace(targetHref);
  }, [r, targetHref]);

  return (
    <div
      ref={adsSurface.ref}
      {...adsSurface.handlers}
      className="grid gap-4 efhc-ads-trust-shell"
      data-ad={adsSurface.variant}
      data-public-visual-trust="hub-browser-shop-withdraw-ads"
      data-public-surface="ads"
    >
      <section
        className="efhc-ads-trust-rail"
        aria-label={t("ads.compatibility_flow")}
      >
        <span className="is-active">{t("ads.standalone_location")}</span>
        <span>{t("ads.tasks_bridge_title")}</span>
        <span>{t("ads.compatibility_flow")}</span>
      </section>
      <Card title={t("ads.tasks_bridge_title")}>
        <div className="space-y-3 text-sm">
          <div>
            {t("ads.standalone_detail")}
          </div>
          <div className="efhc-text-muted2">
            {t("ads.standalone_query_note")}
          </div>
          <Button href={targetHref}>{t("tasks.title")}</Button>
        </div>
      </Card>
    </div>
  );
}
