import { create } from 'zustand'

interface LocationState {
  lat: number | null
  lng: number | null
  city: string | null
  isLoading: boolean
  error: string | null
  setLocation: (lat: number, lng: number, city?: string) => void
  requestLocation: () => void
}

export const useLocationStore = create<LocationState>((set) => ({
  lat: null,
  lng: null,
  city: null,
  isLoading: false,
  error: null,

  setLocation: (lat, lng, city) =>
    set({ lat, lng, city: city || null, error: null }),

  requestLocation: () => {
    set({ isLoading: true, error: null })

    if (!navigator.geolocation) {
      set({ isLoading: false, error: 'Geolocalizzazione non supportata' })
      return
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        set({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          isLoading: false,
        })
      },
      (error) => {
        // Fallback to Milan
        set({
          lat: 45.4642,
          lng: 9.1900,
          city: 'Milano',
          isLoading: false,
          error: 'Posizione non disponibile, usando Milano come default',
        })
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
    )
  },
}))
