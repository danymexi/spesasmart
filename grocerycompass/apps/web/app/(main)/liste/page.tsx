'use client'

import { useState } from 'react'
import { Plus, ShoppingCart, ArrowLeft } from 'lucide-react'
import Link from 'next/link'

export default function ListsPage() {
  const [lists] = useState<Array<{
    id: string
    name: string
    emoji: string
    itemCount: number
  }>>([])

  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-20">
      <header className="sticky top-0 z-50 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-4 py-3">
        <div className="max-w-lg mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/">
              <ArrowLeft size={24} />
            </Link>
            <h1 className="text-xl font-bold">Le mie liste</h1>
          </div>
          <button className="bg-primary text-white rounded-lg px-3 py-1.5 text-sm font-medium flex items-center gap-1">
            <Plus size={16} />
            Nuova
          </button>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-6">
        {lists.length === 0 ? (
          <div className="text-center py-16">
            <ShoppingCart size={64} className="mx-auto mb-4 text-[var(--color-text-disabled)]" />
            <h2 className="text-lg font-semibold mb-2">Nessuna lista</h2>
            <p className="text-[var(--color-text-secondary)] mb-6">
              Crea la tua prima lista della spesa per confrontare i prezzi nei supermercati vicini
            </p>
            <button className="bg-primary text-white rounded-xl px-6 py-3 font-medium">
              + Crea lista
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {lists.map((list) => (
              <Link
                key={list.id}
                href={`/liste/${list.id}`}
                className="block bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-4"
              >
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{list.emoji}</span>
                  <div className="flex-1">
                    <h3 className="font-medium">{list.name}</h3>
                    <p className="text-sm text-[var(--color-text-secondary)]">
                      {list.itemCount} prodotti
                    </p>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
