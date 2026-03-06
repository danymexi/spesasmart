'use client'

import { cn } from '@/lib/utils'

interface BadgeProps {
  variant?: 'default' | 'savings' | 'danger' | 'info'
  children: React.ReactNode
  className?: string
}

export default function Badge({ variant = 'default', children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
        {
          'bg-gray-100 text-gray-700': variant === 'default',
          'bg-savings-bg text-savings': variant === 'savings',
          'bg-red-50 text-red-600': variant === 'danger',
          'bg-blue-50 text-blue-600': variant === 'info',
        },
        className
      )}
    >
      {children}
    </span>
  )
}
