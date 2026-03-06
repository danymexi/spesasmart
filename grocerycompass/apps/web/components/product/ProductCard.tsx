'use client'

import Link from 'next/link'
import Image from 'next/image'
import Badge from '@/components/ui/Badge'
import { formatPrice } from '@/lib/utils'
import type { Product } from '@/types'

interface ProductCardProps {
  product: Product
  onAddToList?: () => void
}

export default function ProductCard({ product, onAddToList }: ProductCardProps) {
  const bestPrice = product.minPrice || (product.prices[0]?.priceDiscounted ?? product.prices[0]?.price)
  const hasDiscount = product.prices.some((p) => p.priceDiscounted)

  return (
    <Link
      href={`/prodotti/${product.id}`}
      className="flex gap-3 bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-3 hover:shadow-sm transition-shadow"
    >
      {/* Image */}
      <div className="w-20 h-20 bg-gray-100 rounded-lg flex-shrink-0 overflow-hidden relative">
        {product.imageUrl ? (
          <Image
            src={product.imageUrl}
            alt={product.name}
            fill
            className="object-cover"
            sizes="80px"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-2xl">
            🛒
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <h3 className="font-medium text-sm truncate">{product.name}</h3>
        {product.brand && (
          <p className="text-xs text-[var(--color-text-secondary)]">
            {product.brand}
            {product.quantityRaw ? ` · ${product.quantityRaw}` : ''}
          </p>
        )}

        <div className="flex items-center gap-2 mt-1.5">
          {bestPrice && (
            <span className="font-price font-bold text-sm">
              {formatPrice(bestPrice)}
            </span>
          )}
          {hasDiscount && <Badge variant="savings">Offerta</Badge>}
        </div>

        {product.numChains && (
          <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
            in {product.numChains} supermercati
          </p>
        )}
      </div>

      {/* Add button */}
      {onAddToList && (
        <button
          onClick={(e) => {
            e.preventDefault()
            onAddToList()
          }}
          className="self-center w-9 h-9 flex items-center justify-center bg-primary-light text-primary rounded-lg flex-shrink-0"
          aria-label="Aggiungi alla lista"
        >
          +
        </button>
      )}
    </Link>
  )
}
