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
  limit?: number;
  offset?: number;
}): Promise<CatalogProduct[]> {
  const res = await apiClient.get<CatalogProduct[]>("/products/catalog", { params });
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

// ── Push Token ───────────────────────────────────────────────────────────────

export async function registerPushToken(
  token: string,
  _platform: "ios" | "android"
): Promise<void> {
  console.log(`Registering push token: ${token}`);
}

export default apiClient;
