import React, { useEffect, useMemo, useState } from "react";

import {
  AdminActionGrid,
} from "../../components/admin/AdminActionGrid";
import {
  AdminDetailShell,
} from "../../components/admin/AdminDetailShell";
import { AdminListShell } from "../../components/admin/AdminListShell";
import { AdminListExpandControl, useAdminListWindow } from "../../components/admin/AdminListWindow";
import { AdminPage } from "../../components/admin/AdminPage";
import {
  AdminPromptModal,
} from "../../components/admin/AdminPromptModal";
import { AdminStatCard } from "../../components/admin/AdminStatCard";
import {
  TelegramInfoBlock,
} from "../../components/ui/telegram/TelegramInfoBlock";
import {
  TelegramSectionRow,
} from "../../components/ui/telegram/TelegramSectionRow";
import {
  TelegramStatusBadge,
} from "../../components/ui/telegram/TelegramStatusBadge";
import { Button } from "../../components/ui/Button";
import {
  adminPath,
  ADMIN_SALE_PACKAGES_PACKAGE_ID_PATH,
  ADMIN_SALE_PACKAGES_PACKAGE_ID_TOGGLE_PATH,
  ADMIN_SALE_PACKAGES_PATH,
} from "../../lib/api/generated/adminSeams";
import { newIdempotencyKey } from "../../lib/idempotency";
import {
  adminSafeLoadError,
  adminUiErrorMessage,
} from "../../lib/adminError";
import {
  useAdminLinkedTransport,
} from "../../queries/useAdminLinkedTransport";
import type { DbId } from "../../types/db-id";

type SalePackage = {
  id: DbId;
  title: string;
  asset: string;
  price_asset_d8: string;
  efhc_amount_d8: string;
  is_active: boolean;
};

type SalePackagesOut = { items: SalePackage[] };

type PackageFilter = "all" | "active" | "inactive";
type PackageMutationMode = "create" | "edit" | null;
type PackageConfirmAction = {
  kind: "toggle";
  item: SalePackage;
} | null;
type SalePackageForm = {
  title: string;
  asset: string;
  price_asset_d8: string;
  efhc_amount_d8: string;
};

const emptyPackageForm: SalePackageForm = {
  title: "",
  asset: "TON",
  price_asset_d8: "",
  efhc_amount_d8: "",
};

function formFromPackage(item: SalePackage | null): SalePackageForm {
  if (!item) return emptyPackageForm;
  return {
    title: item.title,
    asset: item.asset,
    price_asset_d8: item.price_asset_d8,
    efhc_amount_d8: item.efhc_amount_d8,
  };
}

function hasRequiredFormValues(form: SalePackageForm): boolean {
  return Boolean(
    form.title.trim() &&
      form.asset.trim() &&
      form.price_asset_d8.trim() &&
      form.efhc_amount_d8.trim(),
  );
}

export default function AdminSalePackagesPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const [items, setItems] = useState<SalePackage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<PackageFilter>("all");
  const [selectedId, setSelectedId] = useState<DbId | null>(null);
  const [mutationMode, setMutationMode] =
    useState<PackageMutationMode>(null);
  const [mutationForm, setMutationForm] =
    useState<SalePackageForm>(emptyPackageForm);
  const [confirmAction, setConfirmAction] =
    useState<PackageConfirmAction>(null);
  const [mutationBusy, setMutationBusy] = useState(false);
  const [confirmPhrase, setConfirmPhrase] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const out = await adminApiRequest<SalePackagesOut>(
        ADMIN_SALE_PACKAGES_PATH,
        "GET",
      );
      const nextItems = Array.isArray(out?.items) ? out.items : [];
      setItems(nextItems);
      setSelectedId((prev) => prev ?? nextItems[0]?.id ?? null);
    } catch (e: any) {
      setError(adminSafeLoadError(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const activeCount = useMemo(
    () => items.filter((item) => item.is_active).length,
    [items],
  );

  const filteredItems = useMemo(() => {
    if (filter === "active") {
      return items.filter((item) => item.is_active);
    }
    if (filter === "inactive") {
      return items.filter((item) => !item.is_active);
    }
    return items;
  }, [filter, items]);

  const packageWindow = useAdminListWindow(filteredItems, filter);

  const selectedItem = useMemo(() => {
    return (
      filteredItems.find((item) => item.id === selectedId) ||
      items.find((item) => item.id === selectedId) ||
      filteredItems[0] ||
      items[0] ||
      null
    );
  }, [filteredItems, items, selectedId]);

  function openCreateModal() {
    setMutationForm(emptyPackageForm);
    setMutationMode("create");
  }

  function openEditModal(item: SalePackage | null) {
    if (!item) return;
    setSelectedId(item.id);
    setMutationForm(formFromPackage(item));
    setMutationMode("edit");
  }

  async function submitPackageMutation() {
    if (!hasRequiredFormValues(mutationForm)) return;
    setMutationBusy(true);
    setError(null);
    try {
      if (mutationMode === "create") {
        const created = await adminApiRequest<SalePackage>(
          ADMIN_SALE_PACKAGES_PATH,
          "POST",
          {
            body: {
              title: mutationForm.title.trim(),
              asset: mutationForm.asset.trim(),
              price_asset_d8: mutationForm.price_asset_d8.trim(),
              efhc_amount_d8: mutationForm.efhc_amount_d8.trim(),
              is_active: false,
            },
            idempotencyKey: newIdempotencyKey(),
          },
        );
        if (created?.id) setSelectedId(created.id);
      }
      if (mutationMode === "edit" && selectedItem) {
        await adminApiRequest<SalePackage>(
          adminPath(ADMIN_SALE_PACKAGES_PACKAGE_ID_PATH, {
            package_id: selectedItem.id,
          }),
          "PUT",
          {
            body: {
              title: mutationForm.title.trim(),
              asset: mutationForm.asset.trim(),
              price_asset_d8: mutationForm.price_asset_d8.trim(),
              efhc_amount_d8: mutationForm.efhc_amount_d8.trim(),
            },
            idempotencyKey: newIdempotencyKey(),
          },
        );
      }
      setMutationMode(null);
      await load();
    } catch (e: any) {
      setError(adminSafeLoadError(e));
    } finally {
      setMutationBusy(false);
    }
  }

  async function togglePackage(item: SalePackage) {
    setMutationBusy(true);
    setError(null);
    try {
      await adminApiRequest<SalePackage>(
        adminPath(ADMIN_SALE_PACKAGES_PACKAGE_ID_TOGGLE_PATH, {
          package_id: item.id,
        }),
        "POST",
        { idempotencyKey: newIdempotencyKey() },
      );
      setConfirmAction(null);
      setConfirmPhrase("");
      await load();
    } catch (e: any) {
      setError(adminSafeLoadError(e));
    } finally {
      setMutationBusy(false);
    }
  }

  return (
    <AdminPage
      title="Магазин · Пакеты EFHC"
      subtitle="Пакеты EFHC — отдельная серверная сущность продажи, но управляются внутри общего модуля Магазин."
      backHref="/admin/shop"
    >
      <div className="contents" data-admin-sale-packages-surface="v352" data-eam-family="EAM-ADMIN-026">
      <AdminActionGrid
        title="Административные действия"
        subtitle={
          "Создавайте пакеты, обновляйте список и фильтруйте записи по состоянию."
        }
        items={[
          {
            label: "Создать пакет",
            note: "Открыть форму создания пакета.",
            onClick: () => openCreateModal(),
            disabled: mutationBusy || loading,
          },
          {
            label: "Обновить список",
            note: "Обновить список пакетов.",
            onClick: () => {
              void load();
            },
            disabled: mutationBusy || loading,
            variant: "secondary",
          },
          {
            label: "Показать активные",
            note: "Показать только активные пакеты.",
            onClick: () => setFilter("active"),
          },
          {
            label: "Показать неактивные",
            note: "Показать только неактивные пакеты.",
            onClick: () => setFilter("inactive"),
            variant: "ghost",
          },
          {
            label: "Показать всё",
            note: "Показать все пакеты.",
            onClick: () => setFilter("all"),
            variant: "secondary",
          },
        ]}
      />

      {error ? (
        <TelegramInfoBlock title="Статус раздела">
          {error || null}
        </TelegramInfoBlock>
      ) : null}

      <div className="grid gap-3 md:grid-cols-3">
        <AdminStatCard
          label="Всего пакетов"
          value={items.length}
          hint={
            "Количество пакетов в текущем списке."
          }
        />
        <AdminStatCard
          label="Активных"
          value={activeCount}
          hint="Количество активных пакетов."
          tone={activeCount > 0 ? "success" : "neutral"}
        />
        <AdminStatCard
          label="Текущий фильтр"
          value={filter}
          hint="Текущий фильтр списка."
          tone="neutral"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <AdminListShell
          title="Список пакетов"
          subtitle={
            "Выберите пакет, чтобы посмотреть и изменить его параметры."
          }
        >
          {loading ? (
            <TelegramSectionRow
              title="Загрузка"
              subtitle="Загрузка пакетов..."
              rightSlot={
                <TelegramStatusBadge label="Загрузка" tone="neutral" />
              }
            />
          ) : null}
          {!loading && filteredItems.length === 0 ? (
            <TelegramSectionRow
              title="Пакетов нет"
              subtitle="По выбранному фильтру пакеты не найдены."
              rightSlot={
                <TelegramStatusBadge label="Нет данных" tone="neutral" />
              }
            />
          ) : null}
          {packageWindow.visibleItems.map((item) => (
            <TelegramSectionRow
              key={item.id}
              title={item.title}
              subtitle={
                `ID ${item.id} • ${item.asset} • ` +
                `${item.price_asset_d8}`
              }
              rightSlot={
                <TelegramStatusBadge
                  label={item.is_active ? "Активен" : "Неактивен"}
                  tone={item.is_active ? "connected" : "warning"}
                />
              }
              onClick={() => setSelectedId(item.id)}
              className={
                selectedItem?.id === item.id
                  ? "border-[color:var(--tg-link-color)]/40"
                  : undefined
              }
            />
          ))}
          <AdminListExpandControl
            shown={packageWindow.visibleCount}
            total={packageWindow.totalCount}
            onExpand={packageWindow.expand}
            onCollapse={packageWindow.collapse}
          />
        </AdminListShell>

        <AdminDetailShell
          title="Детали пакета"
          subtitle={
            "Параметры и действия для выбранного пакета."
          }
          actions={
            selectedItem ? (
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  disabled={mutationBusy || loading}
                  onClick={() => openEditModal(selectedItem)}
                >
                  Редактировать
                </Button>
                <Button
                  variant={
                    selectedItem.is_active ? "ghost" : "secondary"
                  }
                  disabled={mutationBusy || loading}
                  onClick={() => {
                    setConfirmPhrase("");
                    setConfirmAction({
                      kind: "toggle",
                      item: selectedItem,
                    });
                  }}
                >
                  {selectedItem.is_active
                    ? "Деактивировать"
                    : "Активировать"}
                </Button>
              </div>
            ) : null
          }
        >
          {!selectedItem ? (
            <TelegramInfoBlock title="Детали пакета">
              Выберите пакет слева, чтобы увидеть его детали.
            </TelegramInfoBlock>
          ) : (
            <>
              <TelegramSectionRow
                title="Название"
                subtitle={selectedItem.title}
                rightSlot={
                  <TelegramStatusBadge
                    label="Выбран"
                    tone="primary"
                  />
                }
              />
              <TelegramSectionRow
                title="Актив"
                subtitle={selectedItem.asset}
                rightSlot={
                  <TelegramStatusBadge label="Пакет" tone="neutral" />
                }
              />
              <TelegramSectionRow
                title="Цена"
                subtitle={selectedItem.price_asset_d8}
                rightSlot={
                  <TelegramStatusBadge
                    label="Текущие данные"
                    tone="neutral"
                  />
                }
              />
              <TelegramSectionRow
                title="EFHC"
                subtitle={selectedItem.efhc_amount_d8}
                rightSlot={
                  <TelegramStatusBadge label="Неактивен" tone="warning" />
                }
              />
              <TelegramSectionRow
                title="Состояние"
                subtitle={
                  selectedItem.is_active
                    ? "Пакет активен и доступен."
                    : "Пакет неактивен."
                }
                rightSlot={
                  <TelegramStatusBadge
                    label={
                      selectedItem.is_active ? "Активен" : "Неактивен"
                    }
                    tone={
                      selectedItem.is_active ? "connected" : "warning"
                    }
                  />
                }
              />
              <TelegramInfoBlock title="Действия администратора">
                Создание, редактирование, активация и деактивация выполняются после подтверждения администратора. После успешного действия список обновляется.</TelegramInfoBlock>
              <TelegramInfoBlock title="Управление пакетами">
                Используйте этот раздел для обслуживания пакетов EFHC. Товарные карточки магазина управляются в разделе «Магазин».</TelegramInfoBlock>
            </>
          )}
        </AdminDetailShell>
      </div>

      </div>

      <AdminPromptModal
        dataAdminPromptMarker="sale-packages-editor-v352"
        open={mutationMode !== null}
        title={
          mutationMode === "create"
            ? "Создать пакет"
            : "Редактировать пакет"
        }
        submitLabel={
          mutationMode === "create" ? "Создать" : "Сохранить"
        }
        busy={mutationBusy}
        submitDisabled={!hasRequiredFormValues(mutationForm)}
        values={mutationForm}
        fields={[
          { key: "title", label: "Название" },
          { key: "asset", label: "Актив" },
          { key: "price_asset_d8", label: "Цена" },
          { key: "efhc_amount_d8", label: "Количество EFHC" },
        ]}
        onChange={(key, value) => {
          setMutationForm((prev) => ({ ...prev, [key]: value }));
        }}
        onClose={() => setMutationMode(null)}
        onSubmit={() => void submitPackageMutation()}
      />

      <AdminPromptModal
        dataAdminPromptMarker="sale-packages-toggle-v352"
        open={Boolean(confirmAction)}
        title={
          confirmAction?.item.is_active
            ? "Подтвердить деактивацию пакета"
            : "Подтвердить активацию пакета"
        }
        submitLabel={
          confirmAction?.item.is_active
            ? "Деактивировать"
            : "Активировать"
        }
        busy={mutationBusy}
        values={{
          phrase: confirmPhrase,
          package: confirmAction
            ? `${confirmAction.item.id}: ${confirmAction.item.title}`
            : "",
        }}
        fields={[
          { key: "package", label: "Пакет" },
          {
            key: "phrase",
            label: "Фраза подтверждения",
            placeholder: "подтверждаю",
          },
        ]}
        submitDisabled={confirmPhrase.trim().toLowerCase() !== "подтверждаю"}
        onChange={(key, value) => {
          if (key === "phrase") setConfirmPhrase(value);
        }}
        onClose={() => setConfirmAction(null)}
        onSubmit={() => {
          if (confirmAction) void togglePackage(confirmAction.item);
        }}
      />
    </AdminPage>
  );
}
