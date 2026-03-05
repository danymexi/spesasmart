import axios from "axios";
import { Platform } from "react-native";

// On web production (served by backend), use relative URL.
// On web dev or native, use explicit host.
function getBaseUrl(): string {
  if (Platform.OS === "web") {
    // In production the SPA is served by the backend at the same origin
    if (typeof window !== "undefined" && window.location.hostname !== "localhost") {
      return "/api/v1";
    }
    return "http://localhost:8000/api/v1";
  }
  // Physical devices need the LAN IP
  const API_HOST = Platform.select({
    ios: "192.168.178.40",
    android: "192.168.178.40",
    default: "localhost",
  });
  return `http://${API_HOST}:8000/api/v1`;
}

const BASE_URL = getBaseUrl();

// ── Types ────────────────────────────────────────────────────────────────────

export interface Chain {
  id: string;
  name: string;
  slug: string;
  logo_url: string | null;
  website_url: string | null;
}

export interface Store {
  id: string;
  chain_id: string;
  name: string | null;
  address: string | null;
  city: string | null;
  province: string;
  zip_code: string | null;
  lat: number | null;
  lon: number | null;
  chain_name: string | null;
}

export interface Flyer {
  id: string;
  chain_id: string;
  store_id: string | null;
  title: string | null;
  valid_from: string;
  valid_to: string;
  source_url: string | null;
  pages_count: number | null;
  status: string;
  created_at: string;
  chain_name: string | null;
}

export interface FlyerPage {
  id: string;
  page_number: number | null;
  image_url: string | null;
  processed: boolean;
}

export interface FlyerProduct {
  product_id: string;
  product_name: string;
  brand: string | null;
  category: string | null;
  original_price: number | null;
  offer_price: number;
  discount_pct: number | null;
  discount_type: string | null;
  quantity: string | null;
}

export interface Product {
  id: string;
  name: string;
  brand: string | null;
  category: string | null;
  subcategory: string | null;
  unit: string | null;
  image_url: string | null;
}

export interface ProductSearchResult {
  product: Product;
  best_current_price: number | null;
  chain_name: string | null;
  offers_count: number;
}

export interface PriceHistoryPoint {
  date: string;
  price: number;
  chain_name: string;
  chain_slug: string | null;
  discount_type: string | null;
  price_per_unit: number | null;
  unit_reference: string | null;
}

export interface PriceHistoryResponse {
  product: Product;
  history: PriceHistoryPoint[];
}

export interface BestPriceResponse {
  product: Product;
  best_price: number;
  chain_name: string;
  valid_until: string | null;
  original_price: number | null;
  discount_pct: number | null;
  price_per_unit: number | null;
  unit_reference: string | null;
  price_indicator: string | null;
}

export interface Offer {
  id: string;
  product_id: string;
  product_name: string;
  brand: string | null;
  category: string | null;
  chain_id: string;
  chain_name: string;
  original_price: number | null;
  offer_price: number;
  discount_pct: number | null;
  discount_type: string | null;
  quantity: string | null;
  price_per_unit: number | null;
  valid_from: string | null;
  valid_to: string | null;
  image_url: string | null;
  previous_price: number | null;
  previous_date: string | null;
  previous_chain: string | null;
}

export interface WatchlistItem {
  id: string;
  product_id: string;
  product_name: string;
  brand: string | null;
  target_price: number | null;
  notify_any_offer: boolean;
  best_current_price: number | null;
  best_chain: string | null;
}

export interface UserProfile {
  id: string;
  email: string | null;
  telegram_chat_id: number | null;
  push_token: string | null;
  preferred_zone: string;
  notification_mode: "instant" | "digest";
  created_at: string;
}

export interface UserDeal {
  product_id: string;
  product_name: string;
  brand: string | null;
  chain_name: string;
  offer_price: number;
  original_price: number | null;
  discount_pct: number | null;
  valid_to: string | null;
  image_url: string | null;
}

export interface SmartSearchOffer {
  chain_name: string;
  chain_slug: string;
  offer_price: number;
  original_price: number | null;
  discount_pct: number | null;
  price_per_unit: number | null;
  unit_reference: string | null;
  valid_to: string | null;
  offer_id: string;
}

export interface SmartSearchResult {
  product: Product;
  offers: SmartSearchOffer[];
  price_indicator: string | null;
  best_price_per_unit: number | null;
  unit_reference: string | null;
  is_category_match: boolean;
}

export interface TripItem {
  product_name: string;
  offer_price: number;
  chain_name: string;
  search_term: string | null;
}

export interface StoreTrip {
  chain_name: string;
  items: TripItem[];
  total: number;
  items_covered: number;
}

export interface TripOptimizationResult {
  single_store_best: StoreTrip | null;
  multi_store_plan: StoreTrip[];
  single_store_total: number;
  multi_store_total: number;
  potential_savings: number;
  all_single_stores: StoreTrip[];
  items_total: number;
  items_not_covered: number;
}

export interface UserBrandItem {
  id: string;
  brand_name: string;
  category: string | null;
  notify: boolean;
  created_at: string;
}

export interface Alternative {
  product_id: string;
  product_name: string;
  brand: string | null;
  category: string | null;
  chain_name: string;
  offer_price: number;
  original_price: number | null;
  discount_pct: number | null;
  price_per_unit: number | null;
  unit_reference: string | null;
  valid_to: string | null;
  image_url: string | null;
}

export interface BrandDeal {
  product_id: string;
  product_name: string;
  brand: string | null;
  category: string | null;
  chain_name: string;
  offer_price: number;
  original_price: number | null;
  discount_pct: number | null;
  price_per_unit: number | null;
  unit_reference: string | null;
  valid_to: string | null;
  image_url: string | null;
}

export interface BrandInfo {
  name: string;
  count: number;
}

export interface CatalogProduct {
  id: string;
  name: string;
  brand: string | null;
  category: string | null;
  image_url: string | null;
  has_active_offer: boolean;
  best_offer_price: number | null;
  best_chain_name: string | null;
  best_price_per_unit: number | null;
  unit_reference: string | null;
  unit: string | null;
  price_indicator: string | null; // "ottimo" | "medio" | "alto"
}

export interface PriceTrendPoint {
  period: string;
  avg_price_per_unit: number | null;
  min_price_per_unit: number | null;
  max_price_per_unit: number | null;
  avg_offer_price: number | null;
  min_offer_price: number | null;
  max_offer_price: number | null;
  data_points: number;
}

export interface PriceTrendResponse {
  product: Product;
  trends: PriceTrendPoint[];
  unit_reference: string | null;
}

export interface CategoryInfo {
  name: string;
  count: number;
}

export interface AuthResponse {
  access_token: string;
  user: UserProfile;
}

export interface LinkedProductDetail {
  id: string;
  name: string;
  brand: string | null;
}

export interface ShoppingListItem {
  id: string;
  product_id: string | null;
  product_name: string | null;
  custom_name: string | null;
  quantity: number;
  unit: string | null;
  checked: boolean;
  offer_id: string | null;
  chain_name: string | null;
  offer_price: number | null;
  notes: string | null;
  linked_product_ids: string[];
  linked_product_count: number;
  linked_products_details: LinkedProductDetail[];
  created_at: string;
}

export interface CompareOffer {
  chain_name: string;
  chain_slug: string;
  offer_price: number;
  original_price: number | null;
  discount_pct: number | null;
  price_per_unit: number | null;
  unit_reference: string | null;
  valid_to: string | null;
  offer_id: string;
}

export interface CompareResponse {
  product: Product;
  offers: CompareOffer[];
}

// ── Shopping List Compare Types ──────────────────────────────────────────────

export interface ChainPriceInfo {
  chain_name: string;
  chain_slug: string;
  offer_price: number;
  original_price: number | null;
  discount_pct: number | null;
  product_name: string;
  is_best: boolean;
}

export interface CompareItemInfo {
  item_id: string;
  product_id: string | null;
  display_name: string;
  image_url: string | null;
  quantity: number;
  search_term: string | null;
  chain_prices: ChainPriceInfo[];
}

export interface ChainTotalInfo {
  chain_name: string;
  chain_slug: string;
  total: number;
  items_covered: number;
}

export interface ShoppingListCompareResponse {
  items: CompareItemInfo[];
  chain_totals: ChainTotalInfo[];
  items_total: number;
  multi_store_total: number;
  potential_savings: number;
}

// ── Nearby Stores Types ─────────────────────────────────────────────────────

export interface NearbyChainInfo {
  chain_name: string;
  chain_slug: string;
  store_count: number;
  min_distance_km: number;
}

export interface NearbyStoresResponse {
  chains: NearbyChainInfo[];
  chain_slugs: string[];
  total_stores: number;
}

// ── Suggestions Types ───────────────────────────────────────────────────────

export interface SuggestionItem {
  product_id: string;
  product_name: string;
  brand: string | null;
  category: string | null;
  chain_name: string;
  offer_price: number;
  original_price: number | null;
  discount_pct: number | null;
  price_per_unit: number | null;
  unit_reference: string | null;
  image_url: string | null;
  suggestion_type: "alternative" | "complementary";
}

export interface ShoppingListSuggestionsResponse {
  alternatives: SuggestionItem[];
  complementary: SuggestionItem[];
}

// ── Purchase History Types ───────────────────────────────────────────────────

export interface SupermarketAccount {
  chain_slug: string;
  masked_email: string;
  is_valid: boolean;
  last_error: string | null;
  last_synced_at: string | null;
}

export interface PurchaseOrderItem {
  id: string;
  chain_slug: string;
  external_order_id: string;
  order_date: string;
  total_amount: number | null;
  store_name: string | null;
  status: string | null;
  items_count: number;
}

export interface PurchaseItemDetail {
  id: string;
  external_name: string;
  external_code: string | null;
  quantity: number | null;
  unit_price: number | null;
  total_price: number | null;
  brand: string | null;
  category: string | null;
  product_id: string | null;
  product_name: string | null;
}

export interface PurchaseHabit {
  product_id: string;
  product_name: string;
  brand: string | null;
  category: string | null;
  image_url: string | null;
  total_purchases: number;
  avg_interval_days: number;
  avg_price: number | null;
  last_purchased: string;
  next_purchase_predicted: string | null;
}

export interface SmartListItem {
  product_id: string;
  product_name: string;
  brand: string | null;
  category: string | null;
  image_url: string | null;
  total_purchases: number;
  avg_interval_days: number;
  avg_price: number | null;
  urgency: "alta" | "media" | "bassa";
  days_until_due: number;
  best_current_price: number | null;
  best_chain: string | null;
  savings_vs_avg: number | null;
}

// ── Catalog Preload Types ───────────────────────────────────────────────────

export interface CatalogPreloadItem {
  id: string;
  name: string;
  brand: string | null;
  category: string | null;
  image_url: string | null;
  best_price: number | null;
  best_chain: string | null;
  best_chain_slug: string | null;
}

// ── API Client ───────────────────────────────────────────────────────────────

const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

// Request interceptor: attach JWT token
apiClient.interceptors.request.use((config) => {
  // Dynamic import to avoid circular dependency
  const { useAppStore } = require("../stores/useAppStore");
  const token = useAppStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: auto-logout on 401
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      if (error.response.status === 401) {
        const { useAppStore } = require("../stores/useAppStore");
        const state = useAppStore.getState();
        if (state.isLoggedIn) {
          state.logout();
        }
      }
      console.error(`API Error ${error.response.status}:`, error.response.data);
    } else if (error.request) {
      console.error("API Network Error:", error.message);
    }
    return Promise.reject(error);
  }
);

// ── Auth ─────────────────────────────────────────────────────────────────────

export async function registerUser(email: string, password: string): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>("/auth/register", { email, password });
  return res.data;
}

export async function loginUser(email: string, password: string): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>("/auth/login", { email, password });
  return res.data;
}

export async function getMe(): Promise<UserProfile> {
  const res = await apiClient.get<UserProfile>("/auth/me");
  return res.data;
}

// ── Chains ───────────────────────────────────────────────────────────────────

export async function getChains(): Promise<Chain[]> {
  const res = await apiClient.get<Chain[]>("/chains");
  return res.data;
}

// ── Stores ───────────────────────────────────────────────────────────────────

export async function getStores(city?: string, chain?: string): Promise<Store[]> {
  const res = await apiClient.get<Store[]>("/stores", { params: { city, chain } });
  return res.data;
}

// ── Flyers ───────────────────────────────────────────────────────────────────

export async function getFlyers(chain?: string): Promise<Flyer[]> {
  const res = await apiClient.get<Flyer[]>("/flyers", { params: { chain, active: true } });
  return res.data;
}

export async function getFlyer(flyerId: string): Promise<Flyer> {
  const res = await apiClient.get<Flyer>(`/flyers/${flyerId}`);
  return res.data;
}

export async function getFlyerPages(flyerId: string): Promise<FlyerPage[]> {
  const res = await apiClient.get<FlyerPage[]>(`/flyers/${flyerId}/pages`);
  return res.data;
}

export async function getFlyerProducts(flyerId: string): Promise<FlyerProduct[]> {
  const res = await apiClient.get<FlyerProduct[]>(`/flyers/${flyerId}/products`);
  return res.data;
}

// ── Products ─────────────────────────────────────────────────────────────────

export async function searchProducts(
  q: string,
  category?: string,
  limit: number = 20
): Promise<ProductSearchResult[]> {
  const res = await apiClient.get<ProductSearchResult[]>("/products/search", {
    params: { q, category, limit },
  });
  return res.data;
}

export async function getProduct(productId: string): Promise<Product> {
  const res = await apiClient.get<Product>(`/products/${productId}`);
  return res.data;
}

export async function getProductHistory(productId: string): Promise<PriceHistoryResponse> {
  const res = await apiClient.get<PriceHistoryResponse>(`/products/${productId}/history`);
  return res.data;
}

export async function getProductBestPrice(productId: string): Promise<BestPriceResponse> {
  const res = await apiClient.get<BestPriceResponse>(`/products/${productId}/best-price`);
  return res.data;
}

export async function getProductPriceTrends(
  productId: string,
  months: number = 12
): Promise<PriceTrendResponse> {
  const res = await apiClient.get<PriceTrendResponse>(
    `/products/${productId}/price-trends`,
    { params: { months } }
  );
  return res.data;
}

// ── Offers ───────────────────────────────────────────────────────────────────

export async function getActiveOffers(params?: {
  chain?: string;
  category?: string;
  min_discount?: number;
  sort?: string;
  limit?: number;
  offset?: number;
}): Promise<Offer[]> {
  const res = await apiClient.get<Offer[]>("/offers/active", { params });
  return res.data;
}

export async function getBestOffers(limit: number = 20, category?: string): Promise<Offer[]> {
  const res = await apiClient.get<Offer[]>("/offers/best", { params: { limit, category } });
  return res.data;
}

export async function getHistoricLows(limit: number = 20): Promise<Offer[]> {
  const res = await apiClient.get<Offer[]>("/offers/historic-lows", { params: { limit } });
  return res.data;
}

// ── Watchlist (JWT-protected, /me routes) ────────────────────────────────────

export async function getWatchlist(): Promise<WatchlistItem[]> {
  const res = await apiClient.get<WatchlistItem[]>("/users/me/watchlist");
  return res.data;
}

export async function addToWatchlist(
  productId: string,
  targetPrice?: number
): Promise<WatchlistItem> {
  const res = await apiClient.post<WatchlistItem>("/users/me/watchlist", {
    product_id: productId,
    target_price: targetPrice,
    notify_any_offer: true,
  });
  return res.data;
}

export async function removeFromWatchlist(productId: string): Promise<void> {
  await apiClient.delete(`/users/me/watchlist/${productId}`);
}

// ── User Stores ──────────────────────────────────────────────────────────────

export async function addUserStore(storeId: string): Promise<void> {
  await apiClient.post("/users/me/stores", { store_id: storeId });
}

// ── User Deals ───────────────────────────────────────────────────────────────

export async function getUserDeals(): Promise<UserDeal[]> {
  const res = await apiClient.get<UserDeal[]>("/users/me/deals");
  return res.data;
}

// ── Catalog ──────────────────────────────────────────────────────────────────

export async function getCatalogProducts(params?: {
  category?: string;
  brand?: string;
  q?: string;
  sort?: string;
  chain?: string;
  limit?: number;
  offset?: number;
}): Promise<CatalogProduct[]> {
  const res = await apiClient.get<CatalogProduct[]>("/products/catalog", { params });
  return res.data;
}

export async function getCatalogGrouped(params?: {
  category?: string;
  brand?: string;
  q?: string;
  sort?: string;
  chain?: string;
  limit?: number;
  offset?: number;
}): Promise<SmartSearchResult[]> {
  const res = await apiClient.get<SmartSearchResult[]>("/products/catalog-grouped", { params });
  return res.data;
}

export async function getCategories(): Promise<CategoryInfo[]> {
  const res = await apiClient.get<CategoryInfo[]>("/products/categories");
  return res.data;
}

export async function getWatchlistIds(): Promise<{ product_ids: string[] }> {
  const res = await apiClient.get<{ product_ids: string[] }>("/users/me/watchlist/ids");
  return res.data;
}

// ── User Brands ──────────────────────────────────────────────────────────────

export async function getUserBrands(): Promise<UserBrandItem[]> {
  const res = await apiClient.get<UserBrandItem[]>("/users/me/brands");
  return res.data;
}

export async function addUserBrand(
  brandName: string,
  category?: string,
  notify: boolean = true
): Promise<UserBrandItem> {
  const res = await apiClient.post<UserBrandItem>("/users/me/brands", {
    brand_name: brandName,
    category: category || null,
    notify,
  });
  return res.data;
}

export async function removeUserBrand(brandId: string): Promise<void> {
  await apiClient.delete(`/users/me/brands/${brandId}`);
}

// ── Brand Deals & Alternatives ───────────────────────────────────────────────

export async function getBrandDeals(limit: number = 30): Promise<BrandDeal[]> {
  const res = await apiClient.get<BrandDeal[]>("/users/me/brand-deals", {
    params: { limit },
  });
  return res.data;
}

export async function getAlternatives(limit: number = 20): Promise<Alternative[]> {
  const res = await apiClient.get<Alternative[]>("/users/me/alternatives", {
    params: { limit },
  });
  return res.data;
}

// ── Brands Autocomplete ─────────────────────────────────────────────────────

export async function getBrands(q?: string, limit: number = 50): Promise<BrandInfo[]> {
  const res = await apiClient.get<BrandInfo[]>("/products/brands", {
    params: { q, limit },
  });
  return res.data;
}

// ── Push Token ───────────────────────────────────────────────────────────────

export async function registerPushToken(
  token: string,
  _platform: "ios" | "android"
): Promise<void> {
  console.log(`Registering push token: ${token}`);
}

// ── Shopping List ────────────────────────────────────────────────────────────

export async function getShoppingList(): Promise<ShoppingListItem[]> {
  const res = await apiClient.get<ShoppingListItem[]>("/users/me/shopping-list");
  return res.data;
}

export async function getShoppingListCount(): Promise<number> {
  const res = await apiClient.get<{ count: number }>("/users/me/shopping-list/count");
  return res.data.count;
}

export async function addToShoppingList(params: {
  product_id?: string;
  product_ids?: string[];
  custom_name?: string;
  quantity?: number;
  unit?: string;
  offer_id?: string;
  notes?: string;
}): Promise<ShoppingListItem> {
  const res = await apiClient.post<ShoppingListItem>("/users/me/shopping-list", params);
  return res.data;
}

export async function toggleShoppingItem(itemId: string): Promise<{ id: string; checked: boolean }> {
  const res = await apiClient.patch<{ id: string; checked: boolean }>(
    `/users/me/shopping-list/${itemId}/check`
  );
  return res.data;
}

export async function removeShoppingItem(itemId: string): Promise<void> {
  await apiClient.delete(`/users/me/shopping-list/${itemId}`);
}

export async function clearCheckedItems(): Promise<void> {
  await apiClient.delete("/users/me/shopping-list/checked");
}

export async function updateLinkedProducts(itemId: string, productIds: string[]): Promise<ShoppingListItem> {
  const res = await apiClient.put<ShoppingListItem>(
    `/users/me/shopping-list/${itemId}/products`,
    { product_ids: productIds }
  );
  return res.data;
}

// ── Compare Prices ──────────────────────────────────────────────────────────

export async function getProductCompare(productId: string): Promise<CompareResponse> {
  const res = await apiClient.get<CompareResponse>(`/products/${productId}/compare`);
  return res.data;
}

// ── User Profile Update ─────────────────────────────────────────────────────

export async function updateUserProfile(data: {
  notification_mode?: string;
  telegram_chat_id?: number;
  push_token?: string;
}): Promise<UserProfile> {
  const res = await apiClient.patch<UserProfile>("/users/me", data);
  return res.data;
}

// ── Smart Search ─────────────────────────────────────────────────────────────

export async function smartSearch(q: string, limit: number = 10): Promise<SmartSearchResult[]> {
  const res = await apiClient.get<SmartSearchResult[]>("/products/smart-search", {
    params: { q, limit },
  });
  return res.data;
}

// ── Preferred Chains ─────────────────────────────────────────────────────────

export async function getPreferredChains(): Promise<string[]> {
  const res = await apiClient.get<{ chains: string[] }>("/users/me/preferred-chains");
  return res.data.chains;
}

export async function updatePreferredChains(chains: string[]): Promise<void> {
  await apiClient.put("/users/me/preferred-chains", { chains });
}

// ── Trip Optimizer ───────────────────────────────────────────────────────────

export async function optimizeTrip(): Promise<TripOptimizationResult> {
  const res = await apiClient.get<TripOptimizationResult>("/users/me/shopping-list/optimize");
  return res.data;
}

// ── Shopping List Compare ───────────────────────────────────────────────────

export async function getShoppingListCompare(
  chainSlugs?: string
): Promise<ShoppingListCompareResponse> {
  const res = await apiClient.get<ShoppingListCompareResponse>(
    "/users/me/shopping-list/compare",
    { params: chainSlugs ? { chain_slugs: chainSlugs } : undefined }
  );
  return res.data;
}

// ── Shopping List Suggestions ───────────────────────────────────────────────

export async function getShoppingListSuggestions(
  limit: number = 10
): Promise<ShoppingListSuggestionsResponse> {
  const res = await apiClient.get<ShoppingListSuggestionsResponse>(
    "/users/me/shopping-list/suggestions",
    { params: { limit } }
  );
  return res.data;
}

// ── Nearby Stores ───────────────────────────────────────────────────────────

export async function getNearbyStores(
  lat: number,
  lon: number,
  radiusKm: number = 20
): Promise<NearbyStoresResponse> {
  const res = await apiClient.get<NearbyStoresResponse>("/stores/nearby", {
    params: { lat, lon, radius_km: radiusKm },
  });
  return res.data;
}

// ── Catalog Preload ─────────────────────────────────────────────────────────

export async function getCatalogPreload(): Promise<CatalogPreloadItem[]> {
  const res = await apiClient.get<CatalogPreloadItem[]>("/products/catalog/preload");
  return res.data;
}

// ── User Location ───────────────────────────────────────────────────────────

export async function updateUserLocation(
  lat: number,
  lon: number
): Promise<{ lat: number; lon: number }> {
  const res = await apiClient.put<{ lat: number; lon: number }>(
    "/users/me/location",
    { lat, lon }
  );
  return res.data;
}

// ── Supermarket Accounts ────────────────────────────────────────────────────

export async function getSupermarketAccounts(): Promise<SupermarketAccount[]> {
  const res = await apiClient.get<SupermarketAccount[]>("/users/me/supermarket-accounts");
  return res.data;
}

export async function addSupermarketAccount(
  chainSlug: string,
  email: string,
  password: string
): Promise<SupermarketAccount> {
  const res = await apiClient.post<SupermarketAccount>("/users/me/supermarket-accounts", {
    chain_slug: chainSlug,
    email,
    password,
  });
  return res.data;
}

export async function removeSupermarketAccount(chainSlug: string): Promise<void> {
  await apiClient.delete(`/users/me/supermarket-accounts/${chainSlug}`);
}

export async function triggerPurchaseSync(chainSlug: string): Promise<{ status: string; message: string }> {
  const res = await apiClient.post<{ status: string; message: string }>(
    `/users/me/supermarket-accounts/${chainSlug}/sync`
  );
  return res.data;
}

// ── Purchase History ────────────────────────────────────────────────────────

export async function getPurchaseOrders(
  limit: number = 50,
  offset: number = 0,
  chain?: string
): Promise<PurchaseOrderItem[]> {
  const res = await apiClient.get<PurchaseOrderItem[]>("/users/me/purchases", {
    params: { limit, offset, chain },
  });
  return res.data;
}

export async function getPurchaseItems(orderId: string): Promise<PurchaseItemDetail[]> {
  const res = await apiClient.get<PurchaseItemDetail[]>(`/users/me/purchases/${orderId}/items`);
  return res.data;
}

export async function getPurchaseHabits(): Promise<PurchaseHabit[]> {
  const res = await apiClient.get<PurchaseHabit[]>("/users/me/purchase-habits");
  return res.data;
}

export async function getSmartList(): Promise<SmartListItem[]> {
  const res = await apiClient.get<SmartListItem[]>("/users/me/smart-list");
  return res.data;
}

export default apiClient;
