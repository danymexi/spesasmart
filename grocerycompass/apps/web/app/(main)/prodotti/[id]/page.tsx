'use client'

import { ArrowLeft, Plus, Minus, ShoppingCart } from 'lucide-react'
import Link from 'next/link'

export default function ProductDetailPage({ params }: { params: { id: string } }) {
  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-24">
      <header className="sticky top-0 z-50 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-4 py-3">
        <div className="max-w-lg mx-auto flex items-center gap-3">
          <Link href="/">
            <ArrowLeft size={24} />
          </Link>
          <h1 className="text-lg font-semibold truncate">Dettaglio prodotto</h1>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-6 space-y-6">
        {/* Product Image */}
        <div className="bg-[var(--color-surface)] rounded-xl p-6 flex items-center justify-center">
          <div className="w-48 h-48 bg-gray-100 rounded-lg" />
        </div>

        {/* Product Info */}
        <div>
          <h2 className="text-2xl font-bold">Nome Prodotto</h2>
          <p className="text-[var(--color-text-secondary)]">Brand - 1 L</p>
        </div>

        {/* Price Table */}
        <section>
          <h3 className="text-lg font-semibold mb-3">Prezzi vicino a te</h3>
          <div className="space-y-2">
            {['Esselunga', 'Iperal', 'Conad'].map((store, i) => (
              <div
                key={store}
                className={`flex items-center gap-3 bg-[var(--color-surface)] rounded-xl border p-3 ${
                  i === 0 ? 'border-primary' : 'border-[var(--color-border)]'
                }`}
              >
                <div className="w-10 h-10 bg-gray-200 rounded-lg flex-shrink-0" />
                <div className="flex-1">
                  <p className="font-medium">{store}</p>
                  <p className="text-xs text-[var(--color-text-secondary)]">--.- km</p>
                </div>
                <div className="text-right">
                  <p className="font-price font-bold">--,--</p>
                  <p className="text-xs text-[var(--color-text-secondary)]">--/kg</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Price History */}
        <section>
          <h3 className="text-lg font-semibold mb-3">Storico prezzi (30gg)</h3>
          <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-4 h-40 flex items-center justify-center">
            <p className="text-sm text-[var(--color-text-disabled)]">Grafico in arrivo</p>
          </div>
        </section>
      </main>

      {/* Add to List CTA */}
      <div className="fixed bottom-0 left-0 right-0 bg-[var(--color-surface)] border-t border-[var(--color-border)] p-4">
        <div className="max-w-lg mx-auto flex items-center gap-3">
          <div className="flex items-center gap-2 border border-[var(--color-border)] rounded-lg">
            <button className="p-2"><Minus size={18} /></button>
            <span className="font-medium px-2">1</span>
            <button className="p-2"><Plus size={18} /></button>
          </div>
          <button className="flex-1 bg-primary text-white rounded-xl py-3 font-medium flex items-center justify-center gap-2">
            <ShoppingCart size={20} />
            Aggiungi alla lista
          </button>
        </div>
      </div>
    </div>
  )
}
