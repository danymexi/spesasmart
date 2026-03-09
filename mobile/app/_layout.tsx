import { useEffect, useMemo } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { PaperProvider, MD3DarkTheme, MD3LightTheme } from "react-native-paper";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useColorScheme } from "react-native";
import { useFonts } from "expo-font";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import * as SplashScreen from "expo-splash-screen";
import { registerServiceWorker } from "../services/registerSW";
import { createGuestUser, getNearbyStores, updateUserLocation } from "../services/api";
import { getGlassStyles } from "../styles/glassStyles";
import { useAppStore } from "../stores/useAppStore";

SplashScreen.preventAutoHideAsync();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, retry: 2 },
  },
});

const lightTheme = {
  ...MD3LightTheme,
  roundness: 16,
  colors: {
    ...MD3LightTheme.colors,
    primary: "#2563EB",
    secondary: "#F97316",
    surface: "#FFFFFF",
    background: "#F5F5F5",
  },
};

const darkTheme = {
  ...MD3DarkTheme,
  roundness: 16,
  colors: {
    ...MD3DarkTheme.colors,
    primary: "#60A5FA",
    secondary: "#FB923C",
    surface: "#1E1E2E",
    background: "#121212",
  },
};

export default function RootLayout() {
  const systemScheme = useColorScheme();
  const themeMode = useAppStore((s) => s.themeMode);

  const isDark = useMemo(() => {
    if (themeMode === "dark") return true;
    if (themeMode === "light") return false;
    return systemScheme === "dark";
  }, [themeMode, systemScheme]);

  const paperTheme = isDark ? darkTheme : lightTheme;
  const glass = useMemo(() => getGlassStyles(isDark), [isDark]);

  const [fontsLoaded] = useFonts({
    ...MaterialCommunityIcons.font,
  });

  useEffect(() => {
    registerServiceWorker();
  }, []);

  // Auto-create guest account on first load if not logged in
  useEffect(() => {
    const { isLoggedIn, setGuest } = useAppStore.getState();
    if (!isLoggedIn) {
      createGuestUser()
        .then((res) => setGuest(res.access_token, res.user.id, res.refresh_token))
        .catch(() => {}); // silently fail if offline
    }
  }, []);

  // Prefetch catalog on app startup
  useEffect(() => {
    useAppStore.getState().prefetchCatalog();
  }, []);

  // Auto-detect location on app startup
  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        const { setUserLocation, setNearbyChains, isLoggedIn } =
          useAppStore.getState();
        setUserLocation(latitude, longitude);
        try {
          const result = await getNearbyStores(latitude, longitude, 20);
          setNearbyChains(result.chain_slugs);
          if (isLoggedIn) {
            updateUserLocation(latitude, longitude).catch(() => {});
          }
        } catch {}
      },
      () => {}, // silently fail if permission denied
      { enableHighAccuracy: false, timeout: 10000 }
    );
  }, []);

  useEffect(() => {
    if (fontsLoaded) {
      SplashScreen.hideAsync();
    }
  }, [fontsLoaded]);

  if (!fontsLoaded) {
    return null;
  }

  return (
    <SafeAreaProvider>
      <PaperProvider theme={paperTheme}>
        <QueryClientProvider client={queryClient}>
          <Stack
            screenOptions={{
              headerStyle: glass.header as any,
              headerTintColor: glass.colors.primary,
              headerTitleStyle: { fontWeight: "bold", color: glass.colors.primary },
              headerShadowVisible: false,
              contentStyle: glass.background,
            }}
          >
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
            <Stack.Screen
              name="product/[id]"
              options={{ title: "Dettaglio Prodotto" }}
            />
            <Stack.Screen
              name="flyer/[id]"
              options={{ title: "Volantino" }}
            />
            <Stack.Screen
              name="purchases"
              options={{ title: "Storico Acquisti" }}
            />
            <Stack.Screen
              name="shopping-mode"
              options={{ title: "Modalit\u00e0 Spesa", presentation: "fullScreenModal", headerShown: false }}
            />
            <Stack.Screen
              name="barcode-scanner"
              options={{ title: "Scansiona Barcode", presentation: "modal", headerShown: false }}
            />
            <Stack.Screen
              name="store-map"
              options={{ title: "Mappa Negozi", headerShown: false }}
            />
            <Stack.Screen
              name="admin"
              options={{ title: "Admin Panel" }}
            />
            <Stack.Screen
              name="supermarket-login/[chain]"
              options={{ title: "Login Supermercato", presentation: "modal", headerShown: false }}
            />
          </Stack>
        </QueryClientProvider>
      </PaperProvider>
    </SafeAreaProvider>
  );
}
