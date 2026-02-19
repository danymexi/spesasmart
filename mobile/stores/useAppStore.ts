import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  getWatchlist,
  type WatchlistItem,
  type Chain,
} from "../services/api";

// ── Types ────────────────────────────────────────────────────────────────────

interface PreferredStore {
  storeId: number;
  chainId: number;
  name: string;
  address: string;
}

interface AppState {
  // User
  userId: string;
  pushToken: string | null;
  notificationsEnabled: boolean;
  telegramEnabled: boolean;

  // Filters
  selectedChains: number[];
  selectedCategory: string | null;
  offersOnly: boolean;

  // Cached data
  watchlistItems: WatchlistItem[];
  watchlistLoading: boolean;

  // Preferences
  preferredStores: PreferredStore[];
  preferredCategories: string[];
  availableChains: Chain[];

  // Actions
  setUserId: (id: string) => void;
  setPushToken: (token: string | null) => void;
  setNotificationsEnabled: (enabled: boolean) => void;
  setTelegramEnabled: (enabled: boolean) => void;

  toggleChain: (chainId: number) => void;
  setSelectedChains: (chainIds: number[]) => void;
  setCategory: (category: string | null) => void;
  setOffersOnly: (offersOnly: boolean) => void;

  refreshWatchlist: () => Promise<void>;
  setWatchlistItems: (items: WatchlistItem[]) => void;

  addPreferredStore: (store: PreferredStore) => void;
  removePreferredStore: (storeId: number) => void;
  setPreferredCategories: (categories: string[]) => void;
  togglePreferredCategory: (category: string) => void;

  setAvailableChains: (chains: Chain[]) => void;

  reset: () => void;
}

// ── Initial state ────────────────────────────────────────────────────────────

const initialState = {
  userId: "",
  pushToken: null,
  notificationsEnabled: true,
  telegramEnabled: false,

  selectedChains: [],
  selectedCategory: null,
  offersOnly: false,

  watchlistItems: [],
  watchlistLoading: false,

  preferredStores: [],
  preferredCategories: [],
  availableChains: [],
};

// ── Store ────────────────────────────────────────────────────────────────────

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      ...initialState,

      // ── User actions ────────────────────────────────────────────────────

      setUserId: (id: string) => set({ userId: id }),

      setPushToken: (token: string | null) => set({ pushToken: token }),

      setNotificationsEnabled: (enabled: boolean) =>
        set({ notificationsEnabled: enabled }),

      setTelegramEnabled: (enabled: boolean) =>
        set({ telegramEnabled: enabled }),

      // ── Filter actions ──────────────────────────────────────────────────

      toggleChain: (chainId: number) => {
        const current = get().selectedChains;
        const exists = current.includes(chainId);
        set({
          selectedChains: exists
            ? current.filter((id) => id !== chainId)
            : [...current, chainId],
        });
      },

      setSelectedChains: (chainIds: number[]) =>
        set({ selectedChains: chainIds }),

      setCategory: (category: string | null) =>
        set({ selectedCategory: category }),

      setOffersOnly: (offersOnly: boolean) => set({ offersOnly }),

      // ── Watchlist actions ───────────────────────────────────────────────

      refreshWatchlist: async () => {
        const userId = get().userId;
        if (!userId) return;

        set({ watchlistLoading: true });
        try {
          const items = await getWatchlist(userId);
          set({ watchlistItems: items, watchlistLoading: false });
        } catch (error) {
          console.error("Errore nel caricamento della lista:", error);
          set({ watchlistLoading: false });
        }
      },

      setWatchlistItems: (items: WatchlistItem[]) =>
        set({ watchlistItems: items }),

      // ── Store preferences ───────────────────────────────────────────────

      addPreferredStore: (store: PreferredStore) => {
        const current = get().preferredStores;
        if (!current.some((s) => s.storeId === store.storeId)) {
          set({ preferredStores: [...current, store] });
        }
      },

      removePreferredStore: (storeId: number) => {
        set({
          preferredStores: get().preferredStores.filter(
            (s) => s.storeId !== storeId
          ),
        });
      },

      // ── Category preferences ────────────────────────────────────────────

      setPreferredCategories: (categories: string[]) =>
        set({ preferredCategories: categories }),

      togglePreferredCategory: (category: string) => {
        const current = get().preferredCategories;
        const exists = current.includes(category);
        set({
          preferredCategories: exists
            ? current.filter((c) => c !== category)
            : [...current, category],
        });
      },

      // ── Chains ──────────────────────────────────────────────────────────

      setAvailableChains: (chains: Chain[]) =>
        set({ availableChains: chains }),

      // ── Reset ───────────────────────────────────────────────────────────

      reset: () => set(initialState),
    }),
    {
      name: "spesasmart-app-store",
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        userId: state.userId,
        pushToken: state.pushToken,
        notificationsEnabled: state.notificationsEnabled,
        telegramEnabled: state.telegramEnabled,
        selectedChains: state.selectedChains,
        preferredStores: state.preferredStores,
        preferredCategories: state.preferredCategories,
        watchlistItems: state.watchlistItems,
      }),
    }
  )
);

export default useAppStore;
