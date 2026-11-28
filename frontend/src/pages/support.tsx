import React from "react";

import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { useT } from "../hooks/useT";
import { useSupportLinks } from "../queries/useSupport";
import { openTelegramLink } from "../lib/telegram";

export default function SupportPage() {
  const t = useT();
  const links = useSupportLinks();

  return (
    <Card title={t("profile.support_chat")}>
      <p className="mb-3 text-sm efhc-text-muted">{t("profile.support_chat_desc")}</p>
      {links.isPending ? <p role="status">{t("common.loading")}</p> : null}
      {links.isError ? (
        <div role="alert">
          <p>{t("common.error")}</p>
          <Button variant="secondary" onClick={() => void links.refetch()}>
            {t("common.refresh")}
          </Button>
        </div>
      ) : null}
      {links.isSuccess && !links.data.length ? <p>{t("common.empty")}</p> : null}
      <div className="grid gap-3">
        {links.data?.map((link) => (
          <a
            key={link.id}
            href={link.url}
            target={link.open_mode === "same_app" ? undefined : "_blank"}
            rel="noopener noreferrer"
            className="efhc-card p-3"
            onClick={(event) => {
              if (link.url.startsWith("https:") && link.open_mode !== "same_app") {
                event.preventDefault();
                openTelegramLink(link.url);
              }
            }}
          >
            <strong>{link.title}</strong>
            {link.subtitle ? <p className="text-sm efhc-text-muted">{link.subtitle}</p> : null}
          </a>
        ))}
      </div>
    </Card>
  );
}
