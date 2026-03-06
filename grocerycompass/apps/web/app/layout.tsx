import type { Metadata } from 'next'
import './globals.css'
import { Providers } from './providers'

export const metadata: Metadata = {
  title: 'GroceryCompass — Confronta i prezzi dei supermercati',
  description: 'Risparmia sulla spesa confrontando i prezzi di tutti i supermercati vicini. Suggerimenti intelligenti di acquisto multi-punto-vendita.',
  keywords: ['supermercati', 'confronto prezzi', 'risparmio', 'spesa', 'Italia'],
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="it">
      <body>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}
