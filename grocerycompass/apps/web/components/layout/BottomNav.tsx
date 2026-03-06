'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Search, ShoppingCart, TrendingDown, User } from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { href: '/', icon: Search, label: 'Cerca' },
  { href: '/liste', icon: ShoppingCart, label: 'Liste' },
  { href: '/liste', icon: TrendingDown, label: 'Confronta' },
  { href: '/profilo', icon: User, label: 'Profilo' },
]

export default function BottomNav() {
  const pathname = usePathname()

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-[var(--color-surface)] border-t border-[var(--color-border)] py-2 px-4 z-50">
      <div className="max-w-lg mx-auto flex justify-around">
        {navItems.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.label}
              href={item.href}
              className={cn(
                'flex flex-col items-center gap-1 min-w-[44px] min-h-[44px] justify-center',
                isActive ? 'text-primary' : 'text-[var(--color-text-secondary)]'
              )}
            >
              <item.icon size={20} />
              <span className="text-xs">{item.label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
