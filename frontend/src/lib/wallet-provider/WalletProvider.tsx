import dynamic from "next/dynamic";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  TonConnectUIProvider,
  useIsConnectionRestored,
  useTonAddress,
  useTonConnectUI,
  useTonWallet,
} from "@tonconnect/ui-react";

import type { Lang } from "../i18n";
import { tonConnectLanguage, tonConnectTheme } from "../tonconnect";
import {
  createNativeGramWalletAdapter,
} from "./adapters/NativeGramWalletAdapter";
import {
  createTelegramWalletAdapter,
} from "./adapters/TelegramWalletAdapter";
import { createTonConnectAdapter } from "./adapters/TonConnectAdapter";
import {
  WalletAdapterUnavailableError,
  type PreparedWalletProof,
  type WalletAdapter,
  type WalletAdapterDescriptor,
  type WalletAdapterId,
  type WalletBindingResult,
  type WalletSession,
  type WalletTransactionRequest,
  type WalletTransactionResult,
  type WalletView,
} from "./types";

const STORAGE_KEY = "efhc.walletProvider.v1";
const DEFAULT_ADAPTER: WalletAdapterId = "tonconnect";
const ADAPTER_ORDER: WalletAdapterId[] = [
  "tonconnect",
  "telegram_wallet",
  "native_gram_wallet",
];

function isWalletAdapterId(value: unknown): value is WalletAdapterId {
  return ADAPTER_ORDER.includes(value as WalletAdapterId);
}

function configuredAdapter(): WalletAdapterId | null {
  const value = process.env.NEXT_PUBLIC_EFHC_WALLET_PROVIDER?.trim();
  return isWalletAdapterId(value) ? value : null;
}

function storedAdapter(): WalletAdapterId | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return isWalletAdapterId(value) ? value : null;
  } catch {
    return null;
  }
}

function storeAdapter(id: WalletAdapterId) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Selection persistence is UI convenience only.
  }
}

type WalletProviderValue = {
  activeAdapterId: WalletAdapterId;
  activeAdapterLabel: string;
  adapters: WalletAdapterDescriptor[];
  session: WalletSession | null;
  address: string;
  providerName: string;
  restoreSettled: boolean;
  modalOpened: boolean;
  selectAdapter(id: WalletAdapterId): void;
  listWallets(adapterId?: WalletAdapterId): Promise<WalletView[]>;
  prepareProof(): Promise<PreparedWalletProof | null>;
  connect(wallet?: WalletView): Promise<void>;
  bindWallet(
    proofState: PreparedWalletProof | null,
  ): Promise<WalletBindingResult | null>;
  disconnect(): Promise<void>;
  sendTransaction(
    tx: WalletTransactionRequest,
  ): Promise<WalletTransactionResult>;
  isUserRejected(error: unknown): boolean;
};

type WalletProviderProps = React.PropsWithChildren<{
  manifestUrl: string;
  returnUrl: string;
  restoreConnection?: boolean;
  language: Lang;
  themeMode: "auto" | "dark" | "light";
  telegramScheme: "light" | "dark";
}>;

const WalletProviderContext =
  createContext<WalletProviderValue | null>(null);

// Pages Router must not mount the official provider during SSR. Keep the
// pre-hydration EFHC shell visible (including protected static pages) and
// switch to the single real TON provider after the browser hydrates.
const OfficialTonConnectProvider = dynamic(
  () => import("@tonconnect/ui-react").then((mod) => mod.TonConnectUIProvider),
  { ssr: false },
);
const DISCONNECTED_WALLET_CONTEXT: WalletProviderValue = {
  activeAdapterId: "tonconnect",
  activeAdapterLabel: "TON Connect",
  adapters: [
    { id: "tonconnect", label: "TON Connect", available: false, connected: false },
  ],
  session: null,
  address: "",
  providerName: "tonconnect",
  restoreSettled: false,
  modalOpened: false,
  selectAdapter: () => { throw new WalletAdapterUnavailableError("tonconnect"); },
  listWallets: async () => [],
  prepareProof: async () => null,
  connect: async () => { throw new WalletAdapterUnavailableError("tonconnect"); },
  bindWallet: async () => null,
  disconnect: async () => undefined,
  sendTransaction: async () => { throw new WalletAdapterUnavailableError("tonconnect"); },
  isUserRejected: () => false,
};

/**
 * Single application-facing wallet root. TonConnect is mounted as one
 * adapter; no page or feature imports its SDK directly.
 */
type TonConnectRuntimeSnapshot = {
  tonConnectUI: any;
  tonWallet: any;
  tonAddress: string;
  restoreSettled: boolean;
  modalOpened: boolean;
};

/**
 * Stable EFHC application shell. The official provider is a sibling of
 * application pages, not their parent: loading its browser-only SDK must
 * never unmount protected pages after their first render.
 */
export function WalletProvider(props: WalletProviderProps) {
  const [hydrated, setHydrated] = useState(false);
  const [tonRuntime, setTonRuntime] = useState<TonConnectRuntimeSnapshot | null>(null);
  useEffect(() => setHydrated(true), []);

  return (
    <WalletProviderRuntime runtime={tonRuntime}>
      {props.children}
      {hydrated ? (
        <OfficialTonConnectProvider
          manifestUrl={props.manifestUrl}
          enableAndroidBackHandler={false}
          restoreConnection={props.restoreConnection}
          actionsConfiguration={{
            twaReturnUrl: props.returnUrl as `${string}://${string}`,
            // Keep official pre-sign, success and error action dialogs visible
            // rather than dropping the only payment feedback after handoff.
            modals: "all",
          }}
          uiPreferences={{
            theme: tonConnectTheme(props.themeMode, props.telegramScheme) as any,
          }}
          walletsPreferredFeatures={{
            sendTransaction: { minMessages: 1 },
          }}
        >
          <TonConnectRuntimeBridge
            language={props.language}
            themeMode={props.themeMode}
            telegramScheme={props.telegramScheme}
            onUpdate={setTonRuntime}
          />
        </OfficialTonConnectProvider>
      ) : null}
    </WalletProviderRuntime>
  );
}

/** Only this bridge is nested under the browser-only official provider. */
function TonConnectRuntimeBridge(props: {
  language: Lang;
  themeMode: "auto" | "dark" | "light";
  telegramScheme: "light" | "dark";
  onUpdate: (value: TonConnectRuntimeSnapshot) => void;
}) {
  const [tonConnectUI, setTonConnectOptions] = useTonConnectUI();
  const tonWallet = useTonWallet() as any;
  const tonAddress = useTonAddress();
  const restoreSettled = useIsConnectionRestored();
  const [modalOpened, setModalOpened] = useState(false);

  useEffect(() => {
    try {
      setTonConnectOptions({
        language: tonConnectLanguage(props.language) as any,
        uiPreferences: {
          theme: tonConnectTheme(props.themeMode, props.telegramScheme) as any,
        },
      });
    } catch {
      // TonConnect UI sync is best effort; adapter remains guarded.
    }
  }, [
    props.language,
    props.telegramScheme,
    props.themeMode,
    setTonConnectOptions,
  ]);

  useEffect(() => {
    const api = tonConnectUI as any;
    if (typeof api?.onModalStateChange !== "function") return;
    const unsubscribe = api.onModalStateChange((state: any) => {
      setModalOpened(Boolean(
        state?.status === "opened" || state?.open === true,
      ));
    });
    return () => {
      try {
        unsubscribe?.();
      } catch {
        // no-op
      }
    };
  }, [tonConnectUI]);

  useEffect(() => {
    props.onUpdate({
      tonConnectUI,
      tonWallet,
      tonAddress,
      restoreSettled,
      modalOpened,
    });
  }, [
    modalOpened,
    props.onUpdate,
    restoreSettled,
    tonAddress,
    tonConnectUI,
    tonWallet,
  ]);

  return null;
}

function WalletProviderRuntime(
  props: React.PropsWithChildren<{
    runtime: TonConnectRuntimeSnapshot | null;
  }>,
) {
  const tonConnectUI = props.runtime?.tonConnectUI ?? null;
  const tonWallet = props.runtime?.tonWallet ?? null;
  const tonAddress = props.runtime?.tonAddress ?? "";
  const restoreSettled = props.runtime?.restoreSettled ?? false;
  const tonModalOpened = props.runtime?.modalOpened ?? false;
  const [adapterRevision, setAdapterRevision] = useState(0);
  const [activeAdapterId, setActiveAdapterId] =
    useState<WalletAdapterId>(
      DEFAULT_ADAPTER,
    );

  const adapters = useMemo<WalletAdapter[]>(() => [
    createTonConnectAdapter({
      tonConnectUI,
      wallet: tonWallet,
      address: tonAddress,
      restoreSettled,
      modalOpened: tonModalOpened,
    }),
    createTelegramWalletAdapter(),
    createNativeGramWalletAdapter(),
  ], [
    restoreSettled,
    tonAddress,
    tonConnectUI,
    tonModalOpened,
    tonWallet,
  ]);

  const adapterMap = useMemo(
    () => new Map(adapters.map((adapter) => [adapter.id, adapter])),
    [adapters],
  );

  useEffect(() => {
    const unsubscribers = adapters.map((adapter) =>
      adapter.subscribe(() => {
      setAdapterRevision((value) => value + 1);
    }));
    return () => {
      for (const unsubscribe of unsubscribers) {
        try {
          unsubscribe();
        } catch {
          // no-op
        }
      }
    };
  }, [adapters]);

  useEffect(() => {
    const preferred = [
      configuredAdapter(),
      storedAdapter(),
      activeAdapterId,
      ...ADAPTER_ORDER,
    ].filter(isWalletAdapterId);
    const selected = preferred.find((id) => (
      adapterMap.get(id)?.getSnapshot().available
    ));
    if (selected && selected !== activeAdapterId) {
      setActiveAdapterId(selected);
    }
  }, [activeAdapterId, adapterMap, adapterRevision]);

  const activeAdapter = adapterMap.get(activeAdapterId)
    || adapterMap.get(DEFAULT_ADAPTER);
  if (!activeAdapter) {
    throw new WalletAdapterUnavailableError(DEFAULT_ADAPTER);
  }
  const activeSnapshot = activeAdapter.getSnapshot();

  const selectAdapter = useCallback((id: WalletAdapterId) => {
    const target = adapterMap.get(id);
    if (!target?.getSnapshot().available) {
      throw new WalletAdapterUnavailableError(id);
    }
    setActiveAdapterId(id);
    storeAdapter(id);
  }, [adapterMap]);

  const listWallets = useCallback(
    (adapterId?: WalletAdapterId) => {
      const target = adapterId ? adapterMap.get(adapterId) : activeAdapter;
      if (!target?.getSnapshot().available) {
        throw new WalletAdapterUnavailableError(adapterId || activeAdapter.id);
      }
      return target.listWallets();
    },
    [activeAdapter, adapterMap],
  );
  const prepareProof = useCallback(
    () => activeAdapter.prepareProof(),
    [activeAdapter],
  );
  const connect = useCallback(
    async (wallet?: WalletView) => {
      const target = wallet?.adapterId
        ? adapterMap.get(wallet.adapterId)
        : activeAdapter;
      if (!target?.getSnapshot().available) {
        throw new WalletAdapterUnavailableError(
          wallet?.adapterId || activeAdapter.id,
        );
      }
      if (wallet?.adapterId && wallet.adapterId !== activeAdapterId) {
        setActiveAdapterId(wallet.adapterId);
        storeAdapter(wallet.adapterId);
      }
      await target.connect(wallet);
    },
    [activeAdapter, activeAdapterId, adapterMap],
  );
  const bindWallet = useCallback(
    (proofState: PreparedWalletProof | null) => (
      activeAdapter.bindWallet(proofState)
    ),
    [activeAdapter],
  );
  const disconnect = useCallback(
    () => activeAdapter.disconnect(),
    [activeAdapter],
  );
  const sendTransaction = useCallback(
    (tx: WalletTransactionRequest) => activeAdapter.sendTransaction(tx),
    [activeAdapter],
  );
  const isUserRejected = useCallback(
    (error: unknown) => activeAdapter.isUserRejected(error),
    [activeAdapter],
  );

  const descriptors = adapters.map((adapter) => {
    const snapshot = adapter.getSnapshot();
    return {
      id: adapter.id,
      label: adapter.label,
      available: snapshot.available,
      connected: Boolean(snapshot.session),
    };
  });

  const value = useMemo<WalletProviderValue>(() => ({
    activeAdapterId: activeAdapter.id,
    activeAdapterLabel: activeAdapter.label,
    adapters: descriptors,
    session: activeSnapshot.session,
    address: activeSnapshot.session?.address || "",
    providerName:
      activeSnapshot.session?.providerName || activeAdapter.id,
    restoreSettled: activeSnapshot.restoreSettled,
    modalOpened: activeSnapshot.modalOpened,
    selectAdapter,
    listWallets,
    prepareProof,
    connect,
    bindWallet,
    disconnect,
    sendTransaction,
    isUserRejected,
  }), [
    activeAdapter.id,
    activeAdapter.label,
    activeSnapshot.modalOpened,
    activeSnapshot.restoreSettled,
    activeSnapshot.session,
    bindWallet,
    connect,
    descriptors,
    disconnect,
    isUserRejected,
    listWallets,
    prepareProof,
    selectAdapter,
    sendTransaction,
  ]);

  return (
    <WalletProviderContext.Provider value={props.runtime ? value : DISCONNECTED_WALLET_CONTEXT}>
      {props.children}
    </WalletProviderContext.Provider>
  );
}

export function useWalletProvider(): WalletProviderValue {
  const value = useContext(WalletProviderContext);
  if (!value) {
    throw new Error(
      "useWalletProvider must be used inside WalletProvider",
    );
  }
  return value;
}
