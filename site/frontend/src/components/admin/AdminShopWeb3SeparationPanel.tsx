import React, { useMemo } from "react";
import { adminShopItemTypeLabel, adminShopStatusLabel } from "../../lib/humanLabels";
import {
  AdminActionTable,
  AdminChartCard,
  AdminConfirmationBlock,
  AdminEmptyState,
  AdminFilterBar,
  AdminFlowMapCard,
  AdminKpiCard,
  AdminSectionHeader,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";

type CatalogItemLike = {
  sku: string;
  code?: string;
  title: string;
  item_type?: string;
  status?: string;
  active?: boolean;
  is_active?: boolean;
  price_ton?: string;
  price_usdt?: string;
  pay_currencies?: string[];
  methods?: Record<string, { price?: string } | undefined> | null;
};

type OrderLike = Record<string, unknown>;

type Props = {
  catalog: CatalogItemLike[];
  orders: OrderLike[];
  selectedCode: string | null;
  activeTab: string;
  paymentLane: string;
  loading: boolean;
  onTabChange: (value: string) => void;
  onPaymentLaneChange: (value: string) => void;
  onSelectCode: (code: string) => void;
  onRefreshOrders: () => void;
  onCreateItem: () => void;
};

function itemCode(item: CatalogItemLike): string {
  return item.code || item.sku;
}

function statusOf(item: CatalogItemLike): string {
  if (item.status) return item.status;
  if (item.active ?? item.is_active) return "live";
  return "hidden";
}

function hasTon(item: CatalogItemLike): boolean {
  return Boolean(item.price_ton || item.methods?.TON?.price);
}

function hasUsdt(item: CatalogItemLike): boolean {
  return Boolean(item.price_usdt || item.methods?.USDT?.price);
}

function orderStatus(row: OrderLike): string {
  return String(row.status || "unknown");
}

function countOrders(orders: OrderLike[], status: string): number {
  return orders.filter((row) => orderStatus(row) === status).length;
}

export function AdminShopWeb3SeparationPanel(props: Props) {
  const liveItems = props.catalog.filter((item) => statusOf(item) === "live");
  const draftItems = props.catalog.filter((item) => statusOf(item) === "draft");
  const hiddenItems = props.catalog.filter((item) => statusOf(item) === "hidden");
  const tonReady = props.catalog.filter(hasTon);
  const usdtPlanned = props.catalog.filter(hasUsdt);
  const pendingOrders = countOrders(props.orders, "PENDING");
  const paidOrders = countOrders(props.orders, "PAID");
  const selectedItem = useMemo(
    () => props.catalog.find((item) => itemCode(item) === props.selectedCode),
    [props.catalog, props.selectedCode],
  );

  const visibleItems = useMemo(
    () => props.catalog.slice(0, 6),
    [props.catalog],
  );

  const liveShare = props.catalog.length
    ? Math.round((liveItems.length / props.catalog.length) * 100)
    : 0;
  const tonShare = props.catalog.length
    ? Math.round((tonReady.length / props.catalog.length) * 100)
    : 0;

  return (
    <section
      className="efhc-admin-shop-web3"
      data-admin-shop-active-tab={props.activeTab}
      data-admin-sandbox-source="ui-main section-cards; data-table; chart-area-interactive; MaterialM dashboard cards"
    >
      <AdminSectionHeader
        eyebrow="Управление магазином"
        title="Магазин и оплаты"
        subtitle={
          "Администратор управляет карточками и заказами. Покупатель оплачивает " +
          "товар во внешнем магазине, а система связывает подтверждённую оплату с заказом."
        }
        actions={
          <button
            type="button"
            className="efhc-admin-live-dashboard_live"
            onClick={props.onRefreshOrders}
            disabled={props.loading}
          >
            {props.loading ? "Обновляется" : "Обновить заказы"}
          </button>
        }
      />

      <AdminFilterBar
        groups={[
          {
            label: "Раздел",
            value: props.activeTab === "catalog" ? "Каталог" : props.activeTab === "preview" ? "Предпросмотр" : props.activeTab === "orders" ? "Заказы" : props.activeTab === "nft" ? "Выдача VIP NFT" : "История",
            options: [
              { key: "catalog", label: "Каталог" },
              { key: "preview", label: "Предпросмотр" },
              { key: "orders", label: "Заказы" },
              { key: "nft", label: "Выдача VIP NFT" },
              { key: "history", label: "История" },
            ],
            onChange: props.onTabChange,
          },
          {
            label: "Способ оплаты",
            value: props.paymentLane,
            options: [
              { key: "ton", label: `TON ${tonReady.length}` },
              { key: "usdt", label: `USDT ${usdtPlanned.length}` },
              { key: "intent", label: "Данные платежа" },
            ],
            onChange: props.onPaymentLaneChange,
          },
        ]}
      />

      {props.activeTab !== "orders" ? (
        <div className="efhc-admin-shop-web3_kpis">
          <AdminKpiCard label="Каталог" value={props.catalog.length} meta="товарные карточки" hint={`${liveItems.length} опубликовано · ${hiddenItems.length} скрыто`} tone="primary" />
          <AdminKpiCard label="Оплата TON" value={`${tonShare}%`} meta={`${tonReady.length} карточек`} hint="готово к оплате через TON" tone="success" />
          <AdminKpiCard label="Неактивные" value={draftItems.length} meta="архив" hint="не показываются покупателям" tone="warning" />
          <AdminKpiCard label="Заказы" value={props.orders.length} meta={`${pendingOrders} ожидают · ${paidOrders} оплачено`} hint="текущие заказы магазина" tone="neutral" />
        </div>
      ) : null}

      <AdminFlowMapCard
        title="Как устроен магазин"
        nodes={[
          {
            label: "1. Товарная карточка",
            value: selectedItem ? itemCode(selectedItem) : "нет выбора",
            hint: selectedItem?.title || "карточка каталога",
            active: Boolean(selectedItem),
          },
          {
            label: "2. Действие администратора",
            value: props.activeTab === "catalog" ? "Каталог" : props.activeTab === "preview" ? "Предпросмотр" : props.activeTab === "orders" ? "Заказы" : props.activeTab === "nft" ? "Выдача VIP NFT" : "История",
            hint: "редактирование, скрытие и проверка заказов",
            active: true,
          },
          {
            label: "3. Способ оплаты",
            value: props.paymentLane === "ton" ? "TON" : props.paymentLane === "usdt" ? "USDT" : "Платёж",
            hint: "покупатель выбирает способ оплаты во внешнем магазине",
            active: props.paymentLane !== "usdt",
          },
          {
            label: "4. Сопоставление оплаты",
            value: "назначение + сумма",
            hint: "заказ меняется только после подтверждения оплаты",
            active: true,
          },
        ]}
      />

      <div className="efhc-admin-shop-web3_grid">
        <AdminChartCard
          title="Состояние товаров"
          subtitle="Простое сравнение опубликованных, скрытых и архивных карточек."
          meta={<AdminStatusBadge label="текущие данные" tone="primary" />}
        >
          <div className="efhc-admin-shop-web3_bars" aria-label="Состояние товаров">
            <span style={{ height: `${Math.max(10, liveShare)}%` }}>
              Опубликовано {liveItems.length}
            </span>
            <span style={{ height: `${Math.max(10, 100 - liveShare)}%` }}>
              Скрыто {hiddenItems.length + draftItems.length}
            </span>
            <span style={{ height: `${Math.max(10, tonShare)}%` }}>
              TON {tonReady.length}
            </span>
          </div>
        </AdminChartCard>

        <AdminChartCard
          title="Быстрый выбор товара"
          subtitle="Список товаров и подробности выбранной карточки."
          meta={<AdminStatusBadge label="удобно на телефоне" tone="success" />}
        >
          {visibleItems.length ? (
            <div className="efhc-admin-shop-web3_deck">
              {visibleItems.map((item) => {
                const code = itemCode(item);
                const selected = code === props.selectedCode;
                return (
                  <button
                    key={code}
                    type="button"
                    className="efhc-admin-shop-web3_card"
                    data-selected={selected ? "true" : "false"}
                    onClick={() => props.onSelectCode(code)}
                  >
                    <strong>{item.title}</strong>
                    <span>{code} · {adminShopItemTypeLabel(item.item_type)}</span>
                    <small>
                      {adminShopStatusLabel(statusOf(item))} · TON {hasTon(item) ? "доступно" : "—"}
                    </small>
                  </button>
                );
              })}
            </div>
          ) : (
            <AdminEmptyState
              title="Каталог пуст"
              text="Создайте первую карточку товара."
            />
          )}
        </AdminChartCard>
      </div>

      <AdminActionTable
        title="Ответственность разделов"
        rows={[
          {
            label: "Действия администратора",
            value: "редактирование, состояние, архив, удаление, исполнение заказа",
            hint: "Управление товарами и заказами",
          },
          {
            label: "Путь покупателя",
            value: "оплата, подтверждение и автоматическая обработка",
            hint: "показывать только сведения о магазине и заказах",
          },
          {
            label: "Оплата USDT",
            value: "появится только после готовности реальной оплаты",
            hint: "не включать для покупателей, пока способ оплаты не готов",
          },
        ]}
      />

      <AdminConfirmationBlock
        title="Правила безопасности оплаты"
        text={
          "Платёж зачисляется только после его связи с заказом и подтверждения входящей операции."
        }
        confirmed
      />

      <div className="efhc-admin-shop-web3_actions">
        <button type="button" onClick={props.onCreateItem}>
          Новая карточка
        </button>
        <button type="button" onClick={() => props.onTabChange("orders")}>
          Открыть заказы
        </button>
        <button type="button" onClick={() => props.onTabChange("preview")}>
          Предпросмотр витрины
        </button>
      </div>
    </section>
  );
}
