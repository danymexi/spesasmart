import { useCallback, useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { PaperProvider, MD3DarkTheme, MD3LightTheme } from "react-native-paper";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useColorScheme, View, ActivityIndicator } from "react-native";
import { useFonts } from "expo-font";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import * as SplashScreen from "expo-splash-screen";
import { registerServiceWorker } from "../services/registerSW";
import { glassColors, glassHeader, gradientBackground } from "../styles/glassStyles";
import { useAppStore } from "../stores/useAppStore";

SplashScreen.preventAutoHideAsync();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, retry: 2 },
  },
});

const lightTheme = {
  ...MD3LightTheme,
  roundness: 20,
  colors: {
    ...MD3LightTheme.colors,
    primary: "#2E7D32",
    secondary: "#FF6F00",
    surface: "rgba(255,255,255,0.72)",
    background: "transparent",
  },
};

const darkTheme = {
  ...MD3DarkTheme,
  colors: {
    ...MD3DarkTheme.colors,
    primary: "#66BB6A",
    secondary: "#FFB74D",
  },
};

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const theme = colorScheme === "dark" ? darkTheme : lightTheme;

  const [fontsLoaded] = useFonts({
    ...MaterialCommunityIcons.font,
  });

  useEffect(() => {
    registerServiceWorker();
  }, []);

  // Prefetch catalog on app startup
  useEffect(() => {
    useAppStore.getState().prefetchCatalog();
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
      <PaperProvider theme={theme}>
        <QueryClientProvider client={queryClient}>
          <Stack
            screenOptions={{
              headerStyle: glassHeader as any,
              headerTintColor: glassColors.greenDark,
              headerTitleStyle: { fontWeight: "bold", color: glassColors.greenDark },
              headerShadowVisible: false,
              contentStyle: gradientBackground,
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
              name="supermarket-login/[chain]"
              options={{ title: "Login Supermercato", presentation: "modal", headerShown: false }}
            />
          </Stack>
        </QueryClientProvider>
      </PaperProvider>
    </SafeAreaProvider>
  );
}
