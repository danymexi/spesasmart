import axios from "axios";
import { Platform } from "react-native";

// On web/simulator, localhost works. On a physical device, use the LAN IP.
const API_HOST = Platform.select({
  web: "localhost",
  ios: "192.168.1.19",
  android: "192.168.1.19",
  default: "localhost",
});

const BASE_URL = `http://${API_HOST}:8000/api/v1`;

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
  telegram_chat_id: number | null;
  push_token: string | null;
  preferred_zone: string;
  created_at: string;
}

export interface UserDeal {
  product_name: string;
  brand: string | null;
  chain_name: string;
  offer_price: number;
  original_price: number | null;
  discount_pct: number | null;
  valid_to: string | null;
}

// ── API Client ───────────────────────────────────────────────────────────────

const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      console.error(`API Error ${error.response.status}:`, error.response.data);
    } else if (error.request) {
      console.error("API Network Error:", error.message);
    }
    return Promise.reject(error);
  }
);

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

// ── Users ────────────────────────────────────────────────────────────────────

export async function createUser(data: {
  telegram_chat_id?: number;
  push_token?: string;
  preferred_zone?: string;
}): Promise<UserProfile> {
  const res = await apiClient.post<UserProfile>("/users", data);
  return res.data;
}

export async function getUser(userId: string): Promise<UserProfile> {
  const res = await apiClient.get<UserProfile>(`/users/${userId}`);
  return res.data;
}

// ── Watchlist ────────────────────────────────────────────────────────────────

export async function getWatchlist(userId: string): Promise<WatchlistItem[]> {
  const res = await apiClient.get<WatchlistItem[]>(`/users/${userId}/watchlist`);
  return res.data;
}

export async function addToWatchlist(
  userId: string,
  productId: string,
  targetPrice?: number
): Promise<WatchlistItem> {
  const res = await apiClient.post<WatchlistItem>(`/users/${userId}/watchlist`, {
    product_id: productId,
    target_price: targetPrice,
    notify_any_offer: true,
  });
  return res.data;
}

export async function removeFromWatchlist(userId: string, productId: string): Promise<void> {
  await apiClient.delete(`/users/${userId}/watchlist/${productId}`);
}

// ── User Stores ──────────────────────────────────────────────────────────────

export async function addUserStore(userId: string, storeId: string): Promise<void> {
  await apiClient.post(`/users/${userId}/stores`, { store_id: storeId });
}

// ── User Deals ───────────────────────────────────────────────────────────────

export async function getUserDeals(userId: string): Promise<UserDeal[]> {
  const res = await apiClient.get<UserDeal[]>(`/users/${userId}/deals`);
  return res.data;
}

// ── Push Token ───────────────────────────────────────────────────────────────

export async function registerPushToken(
  userId: string,
  token: string,
  _platform: "ios" | "android"
): Promise<void> {
  // Update user with push token
  // This would need a PATCH endpoint in practice
  console.log(`Registering push token for user ${userId}: ${token}`);
}

export default apiClient;
