'use client'

import { ArrowLeft, User, MapPin, LogOut } from 'lucide-react'
import Link from 'next/link'

export default function ProfilePage() {
  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-20">
      <header className="sticky top-0 z-50 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-4 py-3">
        <div className="max-w-lg mx-auto flex items-center gap-3">
          <Link href="/">
            <ArrowLeft size={24} />
          </Link>
          <h1 className="text-xl font-bold">Profilo</h1>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-4 py-6 space-y-4">
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-4 flex items-center gap-4">
          <div className="w-14 h-14 bg-primary-light rounded-full flex items-center justify-center">
            <User size={28} className="text-primary" />
          </div>
          <div>
            <p className="font-semibold">Ospite</p>
            <Link href="/login" className="text-sm text-primary">
              Accedi o registrati
            </Link>
          </div>
        </div>

        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] divide-y divide-[var(--color-border)]">
          <button className="w-full px-4 py-3 flex items-center gap-3 text-left">
            <MapPin size={20} className="text-[var(--color-text-secondary)]" />
            <div>
              <p className="font-medium">Posizione</p>
              <p className="text-sm text-[var(--color-text-secondary)]">Imposta la tua posizione</p>
            </div>
          </button>
        </div>
      </main>
    </div>
  )
}
