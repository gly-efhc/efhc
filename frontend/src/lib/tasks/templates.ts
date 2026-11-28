export const TASK_TEMPLATE_IDS = [
  "telegram_join",
  "rewarded_ad",
  "website_visit",
  "partner_webapp",
  "partner_bot",
] as const;

export type TaskTemplateId = (typeof TASK_TEMPLATE_IDS)[number];

export type TaskTemplateDefinition = {
  id: TaskTemplateId;
  kind: string;
  adminLabel: string;
  titleKey: string;
  descriptionKey: string;
  targetKind: "telegram_group" | "website" | "none" | "webapp" | "telegram_bot";
  targetLabel: string | null;
  targetPlaceholder: string | null;
  defaultLimitPerUser: number;
  advertising: boolean;
};

export const TASK_TEMPLATES: readonly TaskTemplateDefinition[] = [
  {
    id: "telegram_join",
    kind: "join_channel",
    adminLabel: "Вступить в Telegram группу/канал",
    titleKey: "tasks.template.telegram_join.title",
    descriptionKey: "tasks.template.telegram_join.description",
    targetKind: "telegram_group",
    targetLabel: "Telegram группа/канал",
    targetPlaceholder: "https://t.me/example",
    defaultLimitPerUser: 1,
    advertising: false,
  },
  {
    id: "rewarded_ad",
    kind: "watch_ad",
    adminLabel: "Просмотр рекламы",
    titleKey: "tasks.template.rewarded_ad.title",
    descriptionKey: "tasks.template.rewarded_ad.description",
    targetKind: "none",
    targetLabel: null,
    targetPlaceholder: null,
    defaultLimitPerUser: 1,
    advertising: true,
  },
  {
    id: "website_visit",
    kind: "visit",
    adminLabel: "Перейти на сайт",
    titleKey: "tasks.template.website_visit.title",
    descriptionKey: "tasks.template.website_visit.description",
    targetKind: "website",
    targetLabel: "Ссылка на сайт",
    targetPlaceholder: "https://example.com",
    defaultLimitPerUser: 1,
    advertising: false,
  },
  {
    id: "partner_webapp",
    kind: "partner_webapp",
    adminLabel: "Открыть приложение и ознакомиться",
    titleKey: "tasks.template.partner_webapp.title",
    descriptionKey: "tasks.template.partner_webapp.description",
    targetKind: "webapp",
    targetLabel: "Ссылка для открытия приложения",
    targetPlaceholder: "https://t.me/example_bot/app",
    defaultLimitPerUser: 1,
    advertising: false,
  },
  {
    id: "partner_bot",
    kind: "partner_bot",
    adminLabel: "Запустить приложение",
    titleKey: "tasks.template.partner_bot.title",
    descriptionKey: "tasks.template.partner_bot.description",
    targetKind: "telegram_bot",
    targetLabel: "Ссылка для запуска приложения",
    targetPlaceholder: "https://t.me/example_bot",
    defaultLimitPerUser: 1,
    advertising: false,
  },
] as const;

export function taskTemplateById(id: string | null | undefined): TaskTemplateDefinition | null {
  return TASK_TEMPLATES.find((item) => item.id === id) || null;
}

export function taskTemplateByKind(kind: string | null | undefined): TaskTemplateDefinition | null {
  return TASK_TEMPLATES.find((item) => item.kind === kind) || null;
}

export function taskTemplateMeta(meta: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const raw = meta?.template;
  return raw && typeof raw === "object" && !Array.isArray(raw)
    ? raw as Record<string, unknown>
    : {};
}

export function taskTemplateIdFromMeta(meta: Record<string, unknown> | null | undefined): TaskTemplateId | null {
  const id = String(taskTemplateMeta(meta).id || "");
  return TASK_TEMPLATE_IDS.includes(id as TaskTemplateId) ? id as TaskTemplateId : null;
}

export function taskTemplateForRecord(_kind: string | null | undefined, meta: Record<string, unknown> | null | undefined): TaskTemplateDefinition | null {
  const explicit = taskTemplateIdFromMeta(meta);
  return explicit ? taskTemplateById(explicit) : null;
}

export function taskTemplateTarget(meta: Record<string, unknown> | null | undefined): string {
  const automatic = meta?.automatic;
  if (automatic && typeof automatic === "object" && !Array.isArray(automatic)) {
    const target = String((automatic as Record<string, unknown>).target_url || "").trim();
    if (target) return target;
  }
  const channels = meta?.channels;
  if (Array.isArray(channels) && channels.length) return String(channels[0] || "").trim();
  return "";
}

export function applyTaskTemplateVariables(text: string, target: string): string {
  return String(text || "").replace(/\{\{target\}\}/g, target || "—");
}
