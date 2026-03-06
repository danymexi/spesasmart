const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1'

type FetchOptions = {
  method?: string
  body?: unknown
  headers?: Record<string, string>
}

async function apiFetch<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {} } = options

  const config: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
  }

  if (body) {
    config.body = JSON.stringify(body)
  }

  // Add auth token if available
  if (typeof window !== 'undefined') {
    const token = sessionStorage.getItem('access_token')
    if (token) {
      (config.headers as Record<string, string>)['Authorization'] = `Bearer ${token}`
    }
  }

  const response = await fetch(`${API_BASE}${endpoint}`, config)

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Errore di rete' }))
    throw new Error(error.error?.message || error.message || 'Errore sconosciuto')
  }

  return response.json()
}

// Products
export const searchProducts = (q: string, page = 1) =>
  apiFetch(`/products/search?q=${encodeURIComponent(q)}&page=${page}`)

export const getProduct = (id: string, lat?: number, lng?: number) => {
  const params = new URLSearchParams()
  if (lat) params.set('lat', String(lat))
  if (lng) params.set('lng', String(lng))
  return apiFetch(`/products/${id}?${params}`)
}

// Stores
export const getNearbyStores = (lat: number, lng: number, radius = 20) =>
  apiFetch(`/stores?lat=${lat}&lng=${lng}&radius=${radius}`)

// Lists
export const getLists = (userId: string) =>
  apiFetch(`/lists?user_id=${userId}`)

export const createList = (userId: string, data: { name: string; emoji?: string }) =>
  apiFetch(`/lists?user_id=${userId}`, { method: 'POST', body: data })

export const getListItems = (listId: string) =>
  apiFetch(`/lists/${listId}/items`)

export const addListItem = (listId: string, data: { canonical_product_id?: string; free_text_name?: string; quantity?: number }) =>
  apiFetch(`/lists/${listId}/items`, { method: 'POST', body: data })

// Compare
export const compareList = (listId: string, data: { lat: number; lng: number; radius_km?: number; max_stores?: number }) =>
  apiFetch(`/lists/${listId}/compare`, { method: 'POST', body: data })

// Auth
export const register = (data: { email: string; password: string; display_name?: string }) =>
  apiFetch('/auth/register', { method: 'POST', body: data })

export const login = (data: { email: string; password: string }) =>
  apiFetch('/auth/login', { method: 'POST', body: data })
