import React from "react";
import { useRouter } from "next/router";
import { LayoutContext } from "../Layout";
import { Button } from "../ui/Button";
import { TelegramInfoBlock } from "../ui/telegram/TelegramInfoBlock";
import { TelegramStatusBadge } from "../ui/telegram/TelegramStatusBadge";
import { useT } from "../../hooks/useT";
import { useInterfaceVariantSurface } from "../../hooks/useInterfaceVariantSurface";
import { getAdminThemePageMarker } from "../../lib/adminThemePageRegistry";
import { navigateBackWithinApp, navigateHomeWithinApp } from "../../lib/appBackNavigation";
import { ADMIN_REPORTS_OVERVIEW_PATH } from "../../lib/api/generated/adminSeams";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";

export function AdminPage(
  props: React.PropsWithChildren<{
    title: string;
    subtitle?: string | null;
    backHref?: string;
    actions?: React.ReactNode;
    surfaceBadges?: Array<{
      label: string;
      tone:
        | "primary"
        | "connected"
        | "warning"
        | "neutral"
        | "inactive"
        | "active"
        | "vip";
    }>;
    infoBlock?: {
      title: string;
      description: string;
    } | null;
    refreshBankSnapshot?: boolean;
  }>,
) {
  const t = useT();
  const router = useRouter();
  const adminApiRequest = useAdminLinkedTransport();
  const ctx = React.useContext(LayoutContext);
  const adminThemeSurface = useInterfaceVariantSurface<HTMLDivElement>(
    "AM",
    { dotsPlacement: "above" },
  );
  const pageMarker = getAdminThemePageMarker(router.pathname);

  React.useEffect(() => {
    if (props.refreshBankSnapshot === false || ctx.isAdmin !== true) return;
    void adminApiRequest<unknown>(ADMIN_REPORTS_OVERVIEW_PATH, "GET").catch(() => undefined);
  }, [adminApiRequest, ctx.isAdmin, props.refreshBankSnapshot, router.pathname]);

  if (!ctx.canRenderAdminPage && typeof ctx.isAdmin === "boolean" && !ctx.isAdmin) {
    return (
      <div
        ref={adminThemeSurface.ref}
        {...adminThemeSurface.handlers}
        className="efhc-admin-shell grid gap-4"
        data-am={adminThemeSurface.variant}
        data-admin-page-marker={pageMarker}
        data-admin-route={router.pathname}
        data-admin-primitive="page"
        data-eam-family="EAM-ADMIN-001"
        data-admin-theme-surface="true"
        data-admin-bottom-nav-policy="player-nav-excluded"
      >
        <div className="efhc-admin-header" data-admin-primitive="chrome" data-admin-instance="page-chrome">
          <div className="min-w-0">
            <div className="efhc-admin-eyebrow">EFHC Admin</div>
            <h1 className="text-2xl font-bold leading-tight">
              {props.title}
            </h1>
            <p className="mt-2 text-sm efhc-text-muted">
              Доступ запрещён.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={adminThemeSurface.ref}
      {...adminThemeSurface.handlers}
      className="efhc-admin-shell grid gap-4"
      data-am={adminThemeSurface.variant}
      data-admin-page-marker={pageMarker}
        data-admin-route={router.pathname}
      data-admin-primitive="page"
      data-eam-family="EAM-ADMIN-001"
      data-admin-theme-surface="true"
      data-admin-bottom-nav-policy="player-nav-excluded"
    >
      <div className="efhc-admin-header" data-admin-primitive="chrome" data-admin-instance="page-chrome">
        <div className="min-w-0">
          <div className="efhc-admin-eyebrow">{t("admin.title")}</div>
          <h1 className="text-2xl font-bold leading-tight">
            {props.title}
          </h1>
          {props.subtitle ? (
            <div className="mt-1 text-xs efhc-text-muted">
              {props.subtitle}
            </div>
          ) : null}
          {props.surfaceBadges?.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {props.surfaceBadges.map((item) => (
                <TelegramStatusBadge
                  key={`${props.title}-${item.label}`}
                  label={item.label}
                  tone={item.tone}
                />
              ))}
            </div>
          ) : null}
        </div>
        <div className="efhc-admin-actions" data-admin-navigation="back-menu">
          {props.actions}
          {props.backHref ? (
            <Button
              variant="secondary"
              data-app-navigation="back"
              onClick={() => navigateBackWithinApp(router, props.backHref)}
            >
              ← Назад
            </Button>
          ) : null}
          {router.pathname !== "/admin" ? (
            <Button href="/admin" variant="secondary" data-app-navigation="admin-menu">
              ☰ Меню
            </Button>
          ) : null}
          <Button variant="secondary" data-app-navigation="exit-admin" onClick={() => void navigateHomeWithinApp(router)}>
            В приложение
          </Button>
        </div>
      </div>
      {props.infoBlock ? (
        <TelegramInfoBlock title={props.infoBlock.title}>
          {props.infoBlock.description}
        </TelegramInfoBlock>
      ) : null}
      {props.children}
    </div>
  );
}
