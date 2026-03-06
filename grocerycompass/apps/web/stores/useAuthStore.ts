import { create } from 'zustand'

interface AuthState {
  userId: string | null
  email: string | null
  displayName: string | null
  isAuthenticated: boolean
  setAuth: (userId: string, email: string, displayName?: string | null) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  userId: null,
  email: null,
  displayName: null,
  isAuthenticated: false,

  setAuth: (userId, email, displayName) =>
    set({ userId, email, displayName: displayName || null, isAuthenticated: true }),

  clearAuth: () =>
    set({ userId: null, email: null, displayName: null, isAuthenticated: false }),
}))
