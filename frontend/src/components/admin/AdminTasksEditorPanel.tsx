import React, { useEffect, useMemo, useState } from "react";

import { useT } from "../../hooks/useT";
import { adminUiErrorMessage } from "../../lib/adminError";
import { ADMIN_ADS_PROVIDERS_PATH } from "../../lib/api/generated/adminSeams";
import { fromScaledBigint, toScaledBigintDown } from "../../lib/format";
import {
  TASK_TEMPLATES,
  taskTemplateForRecord,
  taskTemplateTarget,
  type TaskTemplateDefinition,
  type TaskTemplateId,
} from "../../lib/tasks/templates";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import type { DbId } from "../../types/db-id";
import { Button } from "../ui/Button";

export type AdminTaskEditorItem = {
  id: DbId;
  code: string;
  title: string;
  description: string | null;
  is_active: boolean;
  bonus_efhc: string;
  kind: string;
  price_usd_hint: string | null;
  limit_per_user: number;
  total_limit: number | null;
  performed_count: number;
  proof_type: string | null;
  proof_hint: string | null;
  meta: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AdminTaskEditorPayload = {
  code: string;
  title: string;
  description: string | null;
  is_active: boolean;
  bonus_efhc: string;
  kind: string;
  price_usd_hint: string | null;
  limit_per_user: number;
  total_limit: number | null;
  proof_type: null;
  proof_hint: null;
  meta: Record<string, unknown> | null;
};

type ProviderRow = {
  code: string;
  title?: string;
  display_name?: string;
  enabled: boolean;
  is_configured: boolean;
  rewarded_enabled?: boolean;
};

type Props = {
  mode: "create" | "edit";
  task: AdminTaskEditorItem | null;
  busy: boolean;
  onCreate: (payload: AdminTaskEditorPayload) => Promise<void>;
  onUpdate: (taskId: DbId, payload: Partial<AdminTaskEditorPayload>) => Promise<void>;
  onDone?: () => void;
};

type FormState = {
  templateId: TaskTemplateId;
  bonusEfhc: string;
  totalLimit: string;
  targetUrl: string;
  adPrimaryProvider: string;
  adDailyLimit: string;
  adFallbackEnabled: boolean;
  adPlacement: string;
  adStartsAt: string;
  adEndsAt: string;
  legacyTitle: string;
  legacyDescription: string;
};

const DEFAULT_TEMPLATE_ID: TaskTemplateId = "telegram_join";

const EMPTY_FORM: FormState = {
  templateId: DEFAULT_TEMPLATE_ID,
  bonusEfhc: "0.01000000",
  totalLimit: "",
  targetUrl: "",
  adPrimaryProvider: "",
  adDailyLimit: "10",
  adFallbackEnabled: false,
  adPlacement: "",
  adStartsAt: "",
  adEndsAt: "",
  legacyTitle: "",
  legacyDescription: "",
};

function fieldClass(): string {
  return "efhc-admin-task-modal-control";
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function adsMeta(meta: Record<string, unknown> | null): Record<string, unknown> {
  return record((meta || {}).ads);
}

function normalizeD8(value: string): string {
  const raw = value.trim().replace(",", ".");
  if (!/^\d+(?:\.\d{1,8})?$/.test(raw)) {
    throw new Error("Бонус должен быть положительным числом с точностью не более 8 знаков.");
  }
  const scaled = toScaledBigintDown(raw, 8);
  if (scaled <= 0n) throw new Error("Бонус EFHCb должен быть больше нуля.");
  return fromScaledBigint(scaled, 8);
}

function integerOrNull(value: string, label: string): number | null {
  const raw = value.trim();
  if (!raw) return null;
  if (!/^\d+$/.test(raw)) throw new Error(`${label} должен быть целым неотрицательным числом.`);
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed)) throw new Error(`${label} слишком большой.`);
  return parsed;
}

function generatedCode(template: TaskTemplateDefinition): string {
  return `${template.kind}_${Date.now().toString(36)}`.slice(0, 64);
}

function telegramChatFromTarget(value: string): string | null {
  const raw = value.trim();
  if (/^@[A-Za-z0-9_]{4,}$/.test(raw)) return raw;
  if (/^-?\d{5,}$/.test(raw)) return raw;
  const match = raw.match(/^https?:\/\/(?:www\.)?t\.me\/([A-Za-z0-9_]{4,})(?:\/.*)?$/i);
  return match ? `@${match[1]}` : null;
}

function normalizeHttpTarget(value: string, label: string): string {
  const raw = value.trim();
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") throw new Error();
    return parsed.toString();
  } catch {
    throw new Error(`${label}: укажите корректную http/https ссылку.`);
  }
}

function datetimeLocalFromIso(value: unknown): string {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "";
  const shift = parsed.getTimezoneOffset() * 60_000;
  return new Date(parsed.getTime() - shift).toISOString().slice(0, 16);
}

function isoFromDatetimeLocal(value: string, label: string): string | null {
  const raw = value.trim();
  if (!raw) return null;
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) throw new Error(`${label}: укажите корректные дату и время.`);
  return parsed.toISOString();
}

function formFromTask(task: AdminTaskEditorItem): FormState {
  const template = taskTemplateForRecord(task.kind, task.meta);
  const ads = adsMeta(task.meta);
  return {
    templateId: template?.id || DEFAULT_TEMPLATE_ID,
    bonusEfhc: task.bonus_efhc,
    totalLimit: task.total_limit == null ? "" : String(task.total_limit),
    targetUrl: taskTemplateTarget(task.meta),
    adPrimaryProvider: String(ads.primary_provider || ""),
    adDailyLimit: String(ads.daily_limit ?? 10),
    adFallbackEnabled: Boolean(ads.fallback_enabled),
    adPlacement: String(ads.placement || ads.provider_placement || ""),
    adStartsAt: datetimeLocalFromIso(ads.starts_at),
    adEndsAt: datetimeLocalFromIso(ads.ends_at),
    legacyTitle: task.title || "",
    legacyDescription: task.description || "",
  };
}

function providerLabel(provider: ProviderRow): string {
  return String(provider.title || provider.display_name || provider.code);
}

export function AdminTasksEditorPanel(props: Props) {
  const t = useT();
  const adminApiRequest = useAdminLinkedTransport();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [localError, setLocalError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderRow[]>([]);

  useEffect(() => {
    let alive = true;
    void adminApiRequest<ProviderRow[]>(ADMIN_ADS_PROVIDERS_PATH, "GET")
      .then((rows) => { if (alive) setProviders(Array.isArray(rows) ? rows : []); })
      .catch(() => { if (alive) setProviders([]); });
    return () => { alive = false; };
  }, [adminApiRequest]);

  useEffect(() => {
    if (props.mode === "edit" && props.task) setForm(formFromTask(props.task));
    else setForm({ ...EMPTY_FORM });
    setLocalError(null);
  }, [props.mode, props.task]);

  const selectedTemplate = useMemo(
    () => TASK_TEMPLATES.find((item) => item.id === form.templateId) || TASK_TEMPLATES[0],
    [form.templateId],
  );
  const taskTemplate = props.task ? taskTemplateForRecord(props.task.kind, props.task.meta) : null;
  const legacyTask = Boolean(props.mode === "edit" && props.task && !taskTemplate);
  const isAdTask = selectedTemplate.advertising;

  function update<K extends keyof FormState>(key: K, value: FormState[K]): void {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function changeTemplate(templateId: TaskTemplateId): void {
    setForm((current) => ({ ...EMPTY_FORM, templateId, bonusEfhc: current.bonusEfhc }));
    setLocalError(null);
  }

  function buildTemplateMeta(template: TaskTemplateDefinition): Record<string, unknown> {
    const meta: Record<string, unknown> = {
      template: {
        id: template.id,
        version: 1,
        title_key: template.titleKey,
        description_key: template.descriptionKey,
      },
    };

    if (template.advertising) {
      const dailyLimit = integerOrNull(form.adDailyLimit, "Дневной лимит рекламы");
      if (!dailyLimit || dailyLimit < 1) throw new Error("Дневной лимит рекламы должен быть не меньше 1.");
      if (!form.adPrimaryProvider.trim()) throw new Error("Выберите рекламный сервис.");
      const startsAt = isoFromDatetimeLocal(form.adStartsAt, "Начало показа");
      const endsAt = isoFromDatetimeLocal(form.adEndsAt, "Окончание показа");
      if (startsAt && endsAt && Date.parse(startsAt) >= Date.parse(endsAt)) {
        throw new Error("Окончание показа должно быть позже начала.");
      }
      meta.ads = {
        primary_provider: form.adPrimaryProvider.trim(),
        daily_limit: dailyLimit,
        fallback_enabled: form.adFallbackEnabled,
        required_format: "rewarded",
        ...(form.adPlacement.trim() ? { placement: form.adPlacement.trim() } : {}),
        ...(startsAt ? { starts_at: startsAt } : {}),
        ...(endsAt ? { ends_at: endsAt } : {}),
      };
      return meta;
    }

    const target = form.targetUrl.trim();
    if (!target) throw new Error(`Укажите: ${selectedTemplate.targetLabel || "цель задания"}.`);

    if (template.id === "telegram_join") {
      const chat = telegramChatFromTarget(target);
      if (!chat) {
        throw new Error("Для Telegram укажите t.me ссылку, @username или числовой chat ID, доступный боту.");
      }
      meta.channels = [chat];
      meta.automatic = { target_url: target, platform: "telegram" };
      return meta;
    }

    const normalizedTarget = normalizeHttpTarget(target, selectedTemplate.targetLabel || "Ссылка");
    meta.automatic = {
      target_url: normalizedTarget,
      platform: template.id === "partner_bot" ? "telegram" : "web",
      action: template.id === "website_visit"
        ? "visit"
        : template.id === "partner_webapp"
          ? "open_webapp"
          : "start_bot",
    };
    return meta;
  }

  function payloadFromForm(): AdminTaskEditorPayload {
    if (legacyTask && props.task) {
      return {
        code: props.task.code,
        title: form.legacyTitle.trim() || props.task.title,
        description: form.legacyDescription.trim() || null,
        is_active: props.task.is_active,
        bonus_efhc: normalizeD8(form.bonusEfhc),
        kind: props.task.kind,
        price_usd_hint: props.task.price_usd_hint,
        limit_per_user: props.task.limit_per_user,
        total_limit: props.task.total_limit,
        proof_type: null,
        proof_hint: null,
        meta: props.task.meta,
      };
    }

    const template = selectedTemplate;
    const totalLimit = template.advertising ? null : integerOrNull(form.totalLimit, "Общий лимит");
    const bonus = normalizeD8(form.bonusEfhc);
    const code = props.mode === "edit" && props.task ? props.task.code : generatedCode(template);
    const meta = buildTemplateMeta(template);

    return {
      code,
      title: template.adminLabel,
      description: null,
      is_active: props.mode === "edit" && props.task ? props.task.is_active : false,
      bonus_efhc: bonus,
      kind: template.kind,
      price_usd_hint: props.task?.price_usd_hint ?? null,
      limit_per_user: template.defaultLimitPerUser,
      total_limit: template.advertising ? null : totalLimit,
      proof_type: null,
      proof_hint: null,
      meta,
    };
  }

  async function submit(): Promise<void> {
    setLocalError(null);
    try {
      const payload = payloadFromForm();
      if (props.mode === "create") await props.onCreate(payload);
      else if (props.task) await props.onUpdate(props.task.id, payload);
      props.onDone?.();
    } catch (error) {
      setLocalError(adminUiErrorMessage(error, t));
    }
  }

  return (
    <div className="efhc-admin-task-modal-editor" data-admin-task-editor="minimal-v368" data-eam-family="EAM-ADMIN-018">
      {legacyTask ? (
        <div className="efhc-admin-task-modal-fields" data-admin-task-template-fields>
          <label className="efhc-admin-task-modal-field efhc-admin-task-modal-field-wide">
            <span>Тип задания</span>
            <input className={fieldClass()} value="Наследственное задание" disabled />
          </label>
          <label className="efhc-admin-task-modal-field">
            <span>Награда · EFHCb</span>
            <input className={fieldClass()} inputMode="decimal" value={form.bonusEfhc} onChange={(event) => update("bonusEfhc", event.target.value)} />
          </label>
          <label className="efhc-admin-task-modal-field">
            <span>Название</span>
            <input className={fieldClass()} value={form.legacyTitle} onChange={(event) => update("legacyTitle", event.target.value)} />
          </label>
          <label className="efhc-admin-task-modal-field efhc-admin-task-modal-field-wide">
            <span>Описание</span>
            <textarea className={`${fieldClass()} efhc-admin-task-modal-textarea`} value={form.legacyDescription} onChange={(event) => update("legacyDescription", event.target.value)} />
          </label>
        </div>
      ) : (
        <div className="efhc-admin-task-modal-fields" data-admin-task-template-fields>
          <label className="efhc-admin-task-modal-field efhc-admin-task-modal-field-wide">
            <span>Тип задания</span>
            <select
              className={fieldClass()}
              value={form.templateId}
              onChange={(event) => changeTemplate(event.target.value as TaskTemplateId)}
              disabled={props.mode === "edit"}
            >
              {TASK_TEMPLATES.map((template) => <option key={template.id} value={template.id}>{template.adminLabel}</option>)}
            </select>
          </label>

          <label className="efhc-admin-task-modal-field">
            <span>Награда · EFHCb</span>
            <input className={fieldClass()} inputMode="decimal" value={form.bonusEfhc} onChange={(event) => update("bonusEfhc", event.target.value)} />
          </label>

          {isAdTask ? (
            <>
              <label className="efhc-admin-task-modal-field">
                <span>Рекламный сервис</span>
                <select className={fieldClass()} value={form.adPrimaryProvider} onChange={(event) => update("adPrimaryProvider", event.target.value)}>
                  <option value="">Выберите сервис</option>
                  {providers.filter((provider) => provider.enabled).map((provider) => (
                    <option key={provider.code} value={provider.code}>
                      {providerLabel(provider)}{provider.code === "builtin_timer" ? " — только для проверки" : provider.is_configured ? "" : " — не настроен"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="efhc-admin-task-modal-field">
                <span>Просмотров в сутки</span>
                <input className={fieldClass()} inputMode="numeric" value={form.adDailyLimit} onChange={(event) => update("adDailyLimit", event.target.value)} />
              </label>
              <label className="efhc-admin-task-modal-field">
                <span>Placement</span>
                <input className={fieldClass()} value={form.adPlacement} onChange={(event) => update("adPlacement", event.target.value)} />
              </label>
              <label className="efhc-admin-task-modal-field">
                <span>Начало показа</span>
                <input className={fieldClass()} type="datetime-local" value={form.adStartsAt} onChange={(event) => update("adStartsAt", event.target.value)} />
              </label>
              <label className="efhc-admin-task-modal-field">
                <span>Окончание показа</span>
                <input className={fieldClass()} type="datetime-local" value={form.adEndsAt} onChange={(event) => update("adEndsAt", event.target.value)} />
              </label>
              <label className="efhc-admin-task-modal-check efhc-admin-task-modal-field-wide">
                <input type="checkbox" checked={form.adFallbackEnabled} onChange={(event) => update("adFallbackEnabled", event.target.checked)} />
                <span>Резервные рекламные сервисы</span>
              </label>
            </>
          ) : (
            <>
              <label className="efhc-admin-task-modal-field efhc-admin-task-modal-field-wide">
                <span>{selectedTemplate.targetLabel}</span>
                <input className={fieldClass()} value={form.targetUrl} onChange={(event) => update("targetUrl", event.target.value)} placeholder={selectedTemplate.targetPlaceholder || ""} />
              </label>
              <label className="efhc-admin-task-modal-field">
                <span>Общий лимит</span>
                <input className={fieldClass()} inputMode="numeric" value={form.totalLimit} onChange={(event) => update("totalLimit", event.target.value)} placeholder="Без лимита" />
              </label>
            </>
          )}
        </div>
      )}

      {localError ? <div className="efhc-admin-task-modal-error" role="alert">{localError}</div> : null}

      <div className="efhc-admin-task-modal-action">
        <Button onClick={() => void submit()} disabled={props.busy}>
          {props.busy ? "Сохранение…" : props.mode === "create" ? "Создать" : "Сохранить"}
        </Button>
      </div>
    </div>
  );
}
