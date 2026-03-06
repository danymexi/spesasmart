import { Search, MapPin, ShoppingCart, TrendingDown } from 'lucide-react'
import Link from 'next/link'

export default function HomePage() {
  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-4 py-3">
        <div className="max-w-lg mx-auto flex items-center justify-between">
          <h1 className="text-xl font-bold text-primary">GroceryCompass</h1>
          <button className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)]">
            <MapPin size={16} />
            <span>Milano</span>
          </button>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-6 space-y-8">
        {/* Search Bar */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-disabled)]" size={20} />
          <input
            type="text"
            placeholder="Cerca prodotti..."
            className="w-full pl-10 pr-4 py-3 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] text-base focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>

        {/* Your Lists */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <ShoppingCart size={20} />
              Le tue liste
            </h2>
            <Link
              href="/liste"
              className="text-sm text-primary font-medium"
            >
              Vedi tutte
            </Link>
          </div>
          <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-4">
            <p className="text-[var(--color-text-secondary)] text-sm text-center py-4">
              Crea la tua prima lista per iniziare a confrontare i prezzi
            </p>
            <Link
              href="/liste"
              className="block w-full text-center bg-primary text-white rounded-lg py-2.5 font-medium mt-2"
            >
              + Nuova lista
            </Link>
          </div>
        </section>

        {/* Nearby Deals */}
        <section>
          <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
            <TrendingDown size={20} className="text-savings" />
            Offerte vicino a te
          </h2>
          <div className="grid grid-cols-3 gap-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-3 animate-pulse"
              >
                <div className="bg-gray-200 rounded-lg aspect-square mb-2" />
                <div className="h-3 bg-gray-200 rounded mb-1" />
                <div className="h-3 bg-gray-200 rounded w-2/3" />
              </div>
            ))}
          </div>
        </section>

        {/* Nearby Stores */}
        <section>
          <h2 className="text-lg font-semibold mb-3">
            Supermercati vicini
          </h2>
          <div className="space-y-2">
            {['Esselunga', 'Iperal', 'Conad'].map((name) => (
              <div
                key={name}
                className="flex items-center gap-3 bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-3"
              >
                <div className="w-10 h-10 bg-gray-200 rounded-lg flex-shrink-0" />
                <div className="flex-1">
                  <p className="font-medium">{name}</p>
                  <p className="text-sm text-[var(--color-text-secondary)]">--.- km</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Bottom Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 bg-[var(--color-surface)] border-t border-[var(--color-border)] py-2 px-4">
        <div className="max-w-lg mx-auto flex justify-around">
          <Link href="/" className="flex flex-col items-center gap-1 text-primary">
            <Search size={20} />
            <span className="text-xs">Cerca</span>
          </Link>
          <Link href="/liste" className="flex flex-col items-center gap-1 text-[var(--color-text-secondary)]">
            <ShoppingCart size={20} />
            <span className="text-xs">Liste</span>
          </Link>
          <Link href="/liste" className="flex flex-col items-center gap-1 text-[var(--color-text-secondary)]">
            <TrendingDown size={20} />
            <span className="text-xs">Confronta</span>
          </Link>
          <Link href="/profilo" className="flex flex-col items-center gap-1 text-[var(--color-text-secondary)]">
            <MapPin size={20} />
            <span className="text-xs">Profilo</span>
          </Link>
        </div>
      </nav>
    </div>
  )
}
