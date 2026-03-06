'use client'

import { ArrowLeft, Plus, BarChart3 } from 'lucide-react'
import Link from 'next/link'

export default function ListDetailPage({ params }: { params: { id: string } }) {
  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-20">
      <header className="sticky top-0 z-50 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-4 py-3">
        <div className="max-w-lg mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/liste">
              <ArrowLeft size={24} />
            </Link>
            <h1 className="text-xl font-bold">La mia lista</h1>
          </div>
          <button className="bg-savings text-white rounded-lg px-3 py-1.5 text-sm font-medium flex items-center gap-1">
            <BarChart3 size={16} />
            Confronta
          </button>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-6">
        <div className="text-center py-12">
          <p className="text-[var(--color-text-secondary)] mb-4">
            Aggiungi prodotti alla lista per iniziare
          </p>
          <button className="bg-primary text-white rounded-xl px-6 py-3 font-medium flex items-center gap-2 mx-auto">
            <Plus size={20} />
            Aggiungi prodotto
          </button>
        </div>
      </main>
    </div>
  )
}
