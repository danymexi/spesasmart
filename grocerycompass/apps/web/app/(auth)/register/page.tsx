'use client'

import { useState } from 'react'
import Link from 'next/link'

export default function RegisterPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')

  return (
    <div className="min-h-screen bg-[var(--color-bg)] flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-3xl font-bold text-center mb-2">Crea account</h1>
        <p className="text-center text-[var(--color-text-secondary)] mb-8">
          Salva liste, confronta prezzi, risparmia
        </p>

        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <div>
            <label className="block text-sm font-medium mb-1">Nome (opzionale)</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-4 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Il tuo nome"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="la-tua@email.it"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Min. 8 caratteri"
              required
            />
          </div>
          <button
            type="submit"
            className="w-full bg-primary text-white rounded-xl py-3 font-medium"
          >
            Registrati
          </button>
        </form>

        <p className="text-center text-sm mt-6 text-[var(--color-text-secondary)]">
          Hai gi&agrave; un account?{' '}
          <Link href="/login" className="text-primary font-medium">
            Accedi
          </Link>
        </p>
      </div>
    </div>
  )
}
