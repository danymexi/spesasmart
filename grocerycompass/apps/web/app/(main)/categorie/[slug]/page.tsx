'use client'

import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'

export default function CategoryPage({ params }: { params: { slug: string } }) {
  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-20">
      <header className="sticky top-0 z-50 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-4 py-3">
        <div className="max-w-lg mx-auto flex items-center gap-3">
          <Link href="/">
            <ArrowLeft size={24} />
          </Link>
          <h1 className="text-xl font-bold capitalize">{params.slug.replace('-', ' ')}</h1>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-6">
        <p className="text-[var(--color-text-secondary)]">Prodotti in questa categoria</p>
      </main>
    </div>
  )
}
