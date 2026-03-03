import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  getWatchlist,
  getCatalogPreload,
  type WatchlistItem,
  type Chain,
  type CatalogPreloadItem,
} from "../services/api";

// ── Types ────────────────────────────────────────────────────────────────────

interface PreferredStore {
  storeId: number;
  chainId: number;
  name: string;
  address: string;
}

interface AppState {
  // Auth
  accessToken: string | null;
  userEmail: string | null;
  isLoggedIn: boolean;
  userId: string;

  // User
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

  // Catalog cache
  catalogProducts: CatalogPreloadItem[];
  catalogLoading: boolean;
  catalogLastFetched: number | null;

  // Geolocation
  userLat: number | null;
  userLon: number | null;
  nearbyChains: string[];

  // Preferences
  preferredStores: PreferredStore[];
  preferredCategories: string[];
  availableChains: Chain[];

  // Actions
  setAuth: (token: string, userId: string, email: string) => void;
  logout: () => void;
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

  // Catalog cache actions
  prefetchCatalog: () => Promise<void>;

  // Geolocation actions
  setUserLocation: (lat: number, lon: number) => void;
  setNearbyChains: (chains: string[]) => void;

  reset: () => void;
}

// ── Initial state ────────────────────────────────────────────────────────────

const initialState = {
  accessToken: null as string | null,
  userEmail: null as string | null,
  isLoggedIn: false,
  userId: "",

  pushToken: null as string | null,
  notificationsEnabled: true,
  telegramEnabled: false,

  selectedChains: [] as number[],
  selectedCategory: null as string | null,
  offersOnly: false,

  watchlistItems: [] as WatchlistItem[],
  watchlistLoading: false,

  catalogProducts: [] as CatalogPreloadItem[],
  catalogLoading: false,
  catalogLastFetched: null as number | null,

  userLat: null as number | null,
  userLon: null as number | null,
  nearbyChains: [] as string[],

  preferredStores: [] as PreferredStore[],
  preferredCategories: [] as string[],
  availableChains: [] as Chain[],
};

// ── Store ────────────────────────────────────────────────────────────────────

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      ...initialState,

      // ── Auth actions ──────────────────────────────────────────────────

      setAuth: (token: string, userId: string, email: string) =>
        set({ accessToken: token, userId, userEmail: email, isLoggedIn: true }),

      logout: () =>
        set({
          accessToken: null,
          userEmail: null,
          isLoggedIn: false,
          userId: "",
          watchlistItems: [],
        }),

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
        if (!get().isLoggedIn) return;

        set({ watchlistLoading: true });
        try {
          const items = await getWatchlist();
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

      // ── Catalog cache ─────────────────────────────────────────────────

      prefetchCatalog: async () => {
        const { catalogLastFetched, catalogLoading } = get();
        const THIRTY_MIN = 30 * 60 * 1000;
        if (catalogLoading) return;
        if (catalogLastFetched && Date.now() - catalogLastFetched < THIRTY_MIN) return;

        set({ catalogLoading: true });
        try {
          const products = await getCatalogPreload();
          set({
            catalogProducts: products,
            catalogLoading: false,
            catalogLastFetched: Date.now(),
          });
        } catch (error) {
          console.error("Catalog prefetch error:", error);
          set({ catalogLoading: false });
        }
      },

      // ── Geolocation ───────────────────────────────────────────────────

      setUserLocation: (lat: number, lon: number) =>
        set({ userLat: lat, userLon: lon }),

      setNearbyChains: (chains: string[]) =>
        set({ nearbyChains: chains }),

      // ── Reset ───────────────────────────────────────────────────────────

      reset: () => set(initialState),
    }),
    {
      name: "spesasmart-app-store",
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        userEmail: state.userEmail,
        isLoggedIn: state.isLoggedIn,
        userId: state.userId,
        pushToken: state.pushToken,
        notificationsEnabled: state.notificationsEnabled,
        telegramEnabled: state.telegramEnabled,
        selectedChains: state.selectedChains,
        preferredStores: state.preferredStores,
        preferredCategories: state.preferredCategories,
        watchlistItems: state.watchlistItems,
        userLat: state.userLat,
        userLon: state.userLon,
        nearbyChains: state.nearbyChains,
      }),
    }
  )
);

export default useAppStore;
