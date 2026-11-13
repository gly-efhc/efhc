/** Provider status reflects authenticated server session, never simulated toggles. */
import React, { useState } from "react";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { useAuthSessionController } from "../../auth/AuthSessionProvider";
import { isDemoGuestSession } from "../../demo/session";
import { useT } from "../../hooks/useT";
import { getTelegramInitData } from "../../lib/telegram";

export function AccountProviders(): React.JSX.Element {
  const t = useT();
  const auth = useAuthSessionController();
  const [message, setMessage] = useState("");
  const context = auth.status === "authenticated" ? auth.context : null;
  const telegramVerified = context?.provider === "telegram";
  const isGuest = !context || isDemoGuestSession() || /guest|visual/i.test(context.provider);
  const isLinked = Boolean(context && !isGuest);
  const canTelegramLogin = Boolean(getTelegramInitData());
  return (
    <section className="grid gap-3 efhc-account-providers" data-provider-state-source="server-session" data-provider-auth-state={isLinked ? "verified" : "guest"}>
      <Card className="efhc-profile-action-card efhc-account-provider-card p-4">
        <div className="text-lg font-extrabold">{t(isLinked ? "profile.linked_accounts_action" : "profile.sign_in_action")}</div>
        <p className="text-xs efhc-text-muted2">Показываются только подтверждённые сервером данные. Другие подключения не имитируются.</p>
        <p className="text-xs efhc-text-muted2">Global ID: {context?.global_id || "—"}</p>
      </Card>
      <Card className="efhc-profile-action-card efhc-account-provider-card p-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <div className="font-semibold">Telegram</div>
            <div className="text-xs efhc-text-muted2" data-provider-state={telegramVerified ? "verified" : "unverified"}>
              {telegramVerified ? "Вход подтверждён" : "Нет подтверждённой Telegram-сессии"}
            </div>
          </div>
          <Button type="button" variant="secondary" className="source-button secondary efhc-provider-action" disabled={!canTelegramLogin || auth.status === "authenticating"}
            onClick={() => void auth.loginTelegram().then(() => setMessage("Telegram подтверждён сервером")).catch(error => setMessage(error instanceof Error ? error.message : "Ошибка входа"))}>
            {telegramVerified ? "Обновить сессию" : "Подключить Telegram"}
          </Button>
        </div>
      </Card>
      <Card className="efhc-profile-action-card efhc-account-provider-card p-3">
        <div className="font-semibold">TON Connect</div>
        <p className="text-xs efhc-text-muted2">Подключение и проверка TON Proof выполняются в разделе «Кошелёк» через сервер EFHC.</p>
        <Button href="/web-profile?section=wallet" variant="secondary"
          className="source-button secondary efhc-provider-action mt-2"
          data-provider-open-wallet="official-ton-connect">
          {t("wallet.title")}
        </Button>
      </Card>
      {message ? <p role="status" className="text-xs efhc-text-muted2">{message}</p> : null}
    </section>
  );
}
