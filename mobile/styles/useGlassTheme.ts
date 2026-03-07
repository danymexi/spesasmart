import { useMemo } from "react";
import { useColorScheme } from "react-native";
import { useAppStore } from "../stores/useAppStore";
import { getGlassStyles, type GlassTheme } from "./glassStyles";

/**
 * Returns theme-aware glass styles based on the user's theme preference.
 *
 * Uses the persisted `themeMode` from the store:
 *   - "system" (default): follows OS light/dark
 *   - "light": always light
 *   - "dark": always dark
 */
export function useGlassTheme(): GlassTheme {
  const systemScheme = useColorScheme();
  const themeMode = useAppStore((s) => s.themeMode);

  const isDark = useMemo(() => {
    if (themeMode === "dark") return true;
    if (themeMode === "light") return false;
    return systemScheme === "dark";
  }, [themeMode, systemScheme]);

  return useMemo(() => getGlassStyles(isDark), [isDark]);
}
