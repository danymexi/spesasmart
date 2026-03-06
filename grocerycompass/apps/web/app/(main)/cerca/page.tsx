'use client'

import { useState } from 'react'
import { Search, ArrowLeft } from 'lucide-react'
import Link from 'next/link'

export default function SearchPage() {
  const [query, setQuery] = useState('')

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      {/* Search Header */}
      <header className="sticky top-0 z-50 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-4 py-3">
        <div className="max-w-lg mx-auto flex items-center gap-3">
          <Link href="/">
            <ArrowLeft size={24} />
          </Link>
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-disabled)]" size={18} />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Cerca prodotti..."
              className="w-full pl-9 pr-4 py-2.5 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              autoFocus
            />
          </div>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-6">
        {query.length === 0 ? (
          <div className="text-center py-12 text-[var(--color-text-secondary)]">
            <Search size={48} className="mx-auto mb-4 opacity-30" />
            <p>Cerca un prodotto per confrontare i prezzi</p>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-[var(--color-text-secondary)]">
              Risultati per &quot;{query}&quot;
            </p>
            {/* Product results will be rendered here */}
          </div>
        )}
      </main>
    </div>
  )
}
