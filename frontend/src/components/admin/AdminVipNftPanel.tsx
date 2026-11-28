import React, { useEffect, useState } from "react";

import { adminUiErrorMessage } from "../../lib/adminError";
import {
  adminPath,
  ADMIN_ACCESS_PATH,
  ADMIN_USERS_GLOBAL_ID_VIP_CHECK_PATH,
  ADMIN_USERS_VIP_CHECK_ALL_PATH,
} from "../../lib/api/generated/adminSeams";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import type { GlobalId } from "../../types/identity";
import { Button } from "../ui/Button";
import { TelegramInfoBlock } from "../ui/telegram/TelegramInfoBlock";
import { TelegramSectionRow } from "../ui/telegram/TelegramSectionRow";
import { TelegramStatusBadge } from "../ui/telegram/TelegramStatusBadge";
import { AdminSectionCard } from "./AdminSectionCard";

export type AdminVipNftUser = {
  global_id: GlobalId;
  is_vip: boolean;
  ton_wallet?: string | null;
  vip_checked_at?: string | null;
  vip_since?: string | null;
};

type CheckResult = {
  ok: boolean;
  state: string;
  global_id: string;
  is_vip: boolean;
  has_admin_nft: boolean;
  message: string;
  checked_at?: string | null;
};

type BatchResult = {
  ok: boolean;
  checked: number;
  changed: number;
  message: string;
};

type AccessResult = {
  access_method?: string;
  access_method_label?: string;
};

function humanDate(value?: string | null): string {
  if (!value) return "Проверка ещё не выполнялась";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Дата недоступна";
  return date.toLocaleString();
}

export function AdminVipNftPanel({
  user,
  onUserUpdated,
}: {
  user: AdminVipNftUser;
  onUserUpdated: () => Promise<void> | void;
}) {
  const request = useAdminLinkedTransport();
  const [busy, setBusy] = useState<"user" | "all" | "">("");
  const [notice, setNotice] = useState("");
  const [lastResult, setLastResult] = useState<CheckResult | null>(null);
  const [accessLabel, setAccessLabel] = useState("Доступ администратора подтверждён");

  useEffect(() => {
    void request<AccessResult>(ADMIN_ACCESS_PATH, "GET")
      .then((result) => {
        if (result.access_method_label) setAccessLabel(result.access_method_label);
      })
      .catch(() => {
        setAccessLabel("Доступ администратора подтверждён");
      });
  }, [request]);

  async function checkSelected() {
    setBusy("user");
    setNotice("");
    try {
      const result = await request<CheckResult>(
        adminPath(ADMIN_USERS_GLOBAL_ID_VIP_CHECK_PATH, {
          global_id: user.global_id,
        }),
        "POST",
        { body: {} },
      );
      setLastResult(result);
      setNotice(result.message);
      await onUserUpdated();
    } catch (caught: unknown) {
      setNotice(adminUiErrorMessage(caught));
    } finally {
      setBusy("");
    }
  }

  async function checkAll() {
    setBusy("all");
    setNotice("");
    try {
      const result = await request<BatchResult>(
        ADMIN_USERS_VIP_CHECK_ALL_PATH,
        "POST",
        { body: {} },
      );
      setNotice(
        `${result.message} Проверено: ${result.checked}. Изменений: ${result.changed}.`,
      );
      await onUserUpdated();
    } catch (caught: unknown) {
      setNotice(adminUiErrorMessage(caught));
    } finally {
      setBusy("");
    }
  }

  return (
    <AdminSectionCard
      title="Проверка VIP и NFT"
      subtitle="Статус определяется по фактическому владению NFT на подключённом TON-кошельке."
    >
      <div className="space-y-3">
        <div className="grid gap-2 md:grid-cols-2">
          <TelegramSectionRow
            compact
            title="VIP"
            subtitle={user.is_vip ? "VIP подтверждён" : "VIP не подтверждён"}
            rightSlot={(
              <TelegramStatusBadge
                label={user.is_vip ? "Активен" : "Не активен"}
                tone={user.is_vip ? "vip" : "neutral"}
              />
            )}
          />
          <TelegramSectionRow
            compact
            title="TON-кошелёк"
            subtitle={user.ton_wallet ? "Подключён" : "Не подключён"}
            rightSlot={(
              <TelegramStatusBadge
                label={user.ton_wallet ? "Готов к проверке" : "Нужен кошелёк"}
                tone={user.ton_wallet ? "connected" : "warning"}
              />
            )}
          />
          <TelegramSectionRow
            compact
            title="Последняя проверка"
            subtitle={humanDate(lastResult?.checked_at || user.vip_checked_at)}
          />
          <TelegramSectionRow
            compact
            title="VIP подтверждён с"
            subtitle={humanDate(user.vip_since)}
          />
          <TelegramSectionRow
            compact
            title="Ваш доступ к админ-панели"
            subtitle={accessLabel}
          />
          <TelegramSectionRow
            compact
            title="Admin NFT у выбранного пользователя"
            subtitle={
              lastResult
                ? lastResult.has_admin_nft
                  ? "Найден специальный Admin NFT"
                  : "Специальный Admin NFT не найден"
                : "Показывается после новой проверки"
            }
          />
        </div>

        <div className="flex flex-wrap gap-2">
          <Button disabled={busy !== ""} onClick={() => void checkSelected()}>
            {busy === "user" ? "Проверяем…" : "Проверить выбранного пользователя"}
          </Button>
          <Button
            variant="secondary"
            disabled={busy !== ""}
            onClick={() => void checkAll()}
          >
            {busy === "all" ? "Проверяем…" : "Проверить всех пользователей сейчас"}
          </Button>
        </div>

        {notice ? (
          <TelegramInfoBlock title="Результат проверки">
            <p className="text-sm">{notice}</p>
          </TelegramInfoBlock>
        ) : null}
      </div>
    </AdminSectionCard>
  );
}
