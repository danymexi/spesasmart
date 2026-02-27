import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { PaperProvider, MD3DarkTheme, MD3LightTheme } from "react-native-paper";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useColorScheme } from "react-native";
import { registerServiceWorker } from "../services/registerSW";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, retry: 2 },
  },
});

const lightTheme = {
  ...MD3LightTheme,
  colors: {
    ...MD3LightTheme.colors,
    primary: "#1B5E20",
    secondary: "#FF6F00",
    surface: "#FFFFFF",
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

  useEffect(() => {
    registerServiceWorker();
  }, []);

  return (
    <SafeAreaProvider>
      <PaperProvider theme={theme}>
        <QueryClientProvider client={queryClient}>
          <Stack
            screenOptions={{
              headerStyle: { backgroundColor: theme.colors.primary },
              headerTintColor: "#fff",
              headerTitleStyle: { fontWeight: "bold" },
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
          </Stack>
        </QueryClientProvider>
      </PaperProvider>
    </SafeAreaProvider>
  );
}
