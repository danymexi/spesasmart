'use client'

import { useState } from 'react'
import Link from 'next/link'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  return (
    <div className="min-h-screen bg-[var(--color-bg)] flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-3xl font-bold text-center mb-2">GroceryCompass</h1>
        <p className="text-center text-[var(--color-text-secondary)] mb-8">
          Accedi per salvare le tue liste
        </p>

        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <div>
            <label className="block text-sm font-medium mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="la-tua@email.it"
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
            />
          </div>
          <button
            type="submit"
            className="w-full bg-primary text-white rounded-xl py-3 font-medium"
          >
            Accedi
          </button>
        </form>

        <p className="text-center text-sm mt-6 text-[var(--color-text-secondary)]">
          Non hai un account?{' '}
          <Link href="/register" className="text-primary font-medium">
            Registrati
          </Link>
        </p>
      </div>
    </div>
  )
}
