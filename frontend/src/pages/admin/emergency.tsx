import React, { useEffect, useMemo, useState } from "react";

import { AdminPage } from "../../components/admin/AdminPage";
import { AdminPromptModal } from "../../components/admin/AdminPromptModal";
import { AdminSectionCard } from "../../components/admin/AdminSectionCard";
import { AdminStatCard } from "../../components/admin/AdminStatCard";
import { Button } from "../../components/ui/Button";
import { useT } from "../../hooks/useT";
import { adminUiErrorMessage } from "../../lib/adminError";
import {
  ADMIN_BANK_BALANCE_PATH,
  ADMIN_BANK_BURN_PATH,
  ADMIN_BANK_MINT_PATH,
  type AdminBankBalanceResponse,
  type AdminBankMutationResponse,
} from "../../lib/api/generated/adminSeams";
import {
  ensureAdminBankMutationRequest,
  parseAdminBankBalanceResponse,
  parseAdminBankMutationResponse,
} from "../../lib/api/generated/adminSeamValidators";
import { formatD8ToHuman, sumScaledDown } from "../../lib/format";
import { newIdempotencyKey } from "../../lib/idempotency";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";

type EmergencyMode = "mint" | "burn" | null;

const CONFIRM_PHRASE = "ПОДТВЕРЖДАЮ АВАРИЙНУЮ ОПЕРАЦИЮ";

export default function AdminEmergencyPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const t = useT();
  const [bank, setBank] = useState<AdminBankBalanceResponse | null>(null);
  const [mode, setMode] = useState<EmergencyMode>(null);
  const [amount, setAmount] = useState("100.00000000");
  const [reason, setReason] = useState("Аварийная корректировка запаса Банка EFHC");
  const [confirm, setConfirm] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function loadBank() {
    try {
      const raw = await adminApiRequest<unknown>(ADMIN_BANK_BALANCE_PATH, "GET");
      setBank(parseAdminBankBalanceResponse(raw));
    } catch (error: unknown) {
      setMessage(adminUiErrorMessage(error, t));
    }
  }

  useEffect(() => {
    void loadBank();
  }, []);

  const balance = useMemo(
    () => formatD8ToHuman(bank?.efhc_main || "0"),
    [bank],
  );

  const projected = useMemo(() => {
    try {
      const delta = mode === "burn" ? `-${amount || "0"}` : amount || "0";
      return formatD8ToHuman(sumScaledDown(balance, delta, 8));
    } catch {
      return balance;
    }
  }, [amount, balance, mode]);

  const amountNumber = Number(String(amount).replace(",", "."));
  const ready = Boolean(
    mode
      && Number.isFinite(amountNumber)
      && amountNumber > 0
      && reason.trim().length >= 3
      && confirm.trim() === CONFIRM_PHRASE
      && idempotencyKey,
  );

  function open(modeValue: Exclude<EmergencyMode, null>) {
    setMode(modeValue);
    setConfirm("");
    setIdempotencyKey(newIdempotencyKey());
    setMessage(null);
  }

  function close() {
    setMode(null);
    setConfirm("");
    setIdempotencyKey("");
  }

  async function execute() {
    if (!ready || !mode) return;
    setBusy(true);
    setMessage(null);
    try {
      const path = mode === "mint" ? ADMIN_BANK_MINT_PATH : ADMIN_BANK_BURN_PATH;
      const body = ensureAdminBankMutationRequest({ amount, reason: reason.trim() });
      const raw = await adminApiRequest<unknown>(path, "POST", {
        idempotencyKey,
        body,
      });
      const result = parseAdminBankMutationResponse(raw) as AdminBankMutationResponse;
      setMessage(`Аварийная операция выполнена. Баланс Банка EFHC: ${result.bank_balance_after}`);
      close();
      await loadBank();
    } catch (error: unknown) {
      setMessage(adminUiErrorMessage(error, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdminPage
      title="Аварийные операции Банка EFHC"
      subtitle="Mint/Burn вынесены из обычной страницы Банка. Использовать только для подтверждённой аварийной корректировки."
      backHref="/admin/bank"
      surfaceBadges={[
        { label: "SUPERADMIN", tone: "warning" },
        { label: "Аварийный контур", tone: "warning" },
      ]}
    >
      <AdminSectionCard
        title="Важно"
        subtitle="Это не обычный перевод пользователю и не способ исправлять пользовательские балансы. Для операций по Global ID используйте раздел «Пользователи»."
      >
        <div className="flex flex-wrap gap-2">
          <Button href="/admin/bank" variant="secondary">Вернуться в Банк</Button>
          <Button href="/admin/users" variant="secondary">Операции пользователя</Button>
        </div>
      </AdminSectionCard>

      <div className="grid gap-3 md:grid-cols-3">
        <AdminStatCard
          label="Текущий баланс Банка"
          value={balance}
          meta="EFHCm"
          hint="Отрицательный баланс Банка разрешён системной моделью."
          tone="neutral"
        />
        <AdminStatCard
          label="Выбранная операция"
          value={mode === "mint" ? "Mint" : mode === "burn" ? "Burn" : "Не выбрана"}
          meta="аварийное действие"
          hint="Операция не выполняется без отдельного подтверждения."
          tone={mode ? "warning" : "neutral"}
        />
        <AdminStatCard
          label="Расчётный баланс"
          value={projected}
          meta="после подтверждения"
          hint="Показывается до отправки запроса."
          tone={mode ? "warning" : "neutral"}
        />
      </div>

      <AdminSectionCard
        title="Выберите аварийное действие"
        subtitle="Каждая попытка получает отдельный Idempotency-Key и требует полной фразы подтверждения."
      >
        <div className="grid gap-3 md:grid-cols-2" data-eam-family="EAM-ADMIN-028" data-admin-emergency-actions="v363">
          <button
            type="button"
            className="efhc-admin-emergency-action rounded-2xl border p-4 text-left"
            data-admin-primitive="card"
            onClick={() => open("mint")}
          >
            <strong className="block">Mint — увеличить запас Банка</strong>
            <span className="mt-1 block text-sm opacity-75">Аварийно увеличить системный запас EFHC.</span>
          </button>
          <button
            type="button"
            className="efhc-admin-emergency-action rounded-2xl border p-4 text-left"
            data-admin-primitive="card"
            onClick={() => open("burn")}
          >
            <strong className="block">Burn — уменьшить запас Банка</strong>
            <span className="mt-1 block text-sm opacity-75">Аварийно уменьшить системный запас EFHC.</span>
          </button>
        </div>
      </AdminSectionCard>

      {message ? (
        <AdminSectionCard title="Результат" subtitle={message}>
          <div className="flex justify-end">
            <Button variant="secondary" onClick={() => void loadBank()}>Обновить баланс</Button>
          </div>
        </AdminSectionCard>
      ) : null}

      <AdminPromptModal
        open={mode !== null}
        title={mode === "mint" ? "Подтвердить аварийный Mint" : "Подтвердить аварийный Burn"}
        submitLabel="Выполнить аварийную операцию"
        fields={[
          { key: "summary", label: "Проверка", type: "textarea" },
          { key: "amount", label: "Сумма EFHC", type: "number" },
          { key: "reason", label: "Причина", type: "textarea" },
          { key: "confirm", label: `Введите: ${CONFIRM_PHRASE}`, placeholder: CONFIRM_PHRASE },
        ]}
        values={{
          summary: `Банк сейчас: ${balance}\nОперация: ${mode || "—"}\nБаланс после: ${projected}`,
          amount,
          reason,
          confirm,
        }}
        busy={busy}
        submitDisabled={!ready}
        onChange={(key, value) => {
          if (key === "amount") setAmount(value);
          if (key === "reason") setReason(value);
          if (key === "confirm") setConfirm(value);
        }}
        onClose={close}
        onSubmit={() => void execute()}
        dataAdminPromptMarker="emergency-v363"
      />
    </AdminPage>
  );
}
