export interface ShoppingList {
  id: string
  name: string
  emoji: string
  items: ListItem[]
  createdAt: Date
  updatedAt: Date
}

export interface ListItem {
  id: string
  canonicalProductId?: string
  freeTextName?: string
  quantity: number
  unit: string
  isChecked: boolean
  note?: string
  productName?: string
  productBrand?: string
  productImage?: string
  prices?: StorePriceEntry[]
}

export interface StorePriceEntry {
  storeId: string
  storeName: string
  chainLogo: string
  price: number
  priceDiscounted?: number
  pricePerUnit?: number
  unitLabel?: string
  distanceKm: number
  inStock: boolean
}

export interface Product {
  id: string
  name: string
  brand?: string
  categoryName?: string
  quantityValue?: number
  quantityUnit?: string
  quantityRaw?: string
  barcodeEan?: string
  imageUrl?: string
  description?: string
  tags?: string[]
  minPrice?: number
  numChains?: number
  prices: StorePriceEntry[]
}

export interface Store {
  id: string
  chainId: string
  chainName: string
  chainSlug: string
  chainLogo?: string
  name: string
  address?: string
  city?: string
  province?: string
  lat: number
  lng: number
  distanceKm?: number
  isOnlineOnly: boolean
}
