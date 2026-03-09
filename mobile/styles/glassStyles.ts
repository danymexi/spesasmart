import { Platform, ViewStyle } from "react-native";

// ── Light palette ────────────────────────────────────────────────────────────

export const lightGradientColors = {
  start: "#F5F5F5",
  mid: "#F0F4FF",
  end: "#F5F5F5",
};

export const lightGlassColors = {
  // Surfaces
  glass: "#FFFFFF",
  glassBorder: "#E5E7EB",
  glassLight: "#F3F4F6",
  glassDark: "#1E1E2E",

  // Semantic accents (subtle backgrounds)
  primarySubtle: "rgba(37,99,235,0.10)",
  primarySubtleStrong: "rgba(37,99,235,0.15)",
  accentSubtle: "rgba(249,115,22,0.10)",
  errorSubtle: "rgba(220,38,38,0.10)",
  successSubtle: "rgba(22,163,74,0.10)",

  // Core semantic colors
  primary: "#2563EB",
  primaryMuted: "#3B82F6",
  primaryLight: "#60A5FA",
  primaryFaded: "rgba(37,99,235,0.7)",
  accent: "#F97316",
  success: "#16A34A",
  warning: "#F59E0B",
  error: "#DC2626",

  // Text
  textPrimary: "#1a1a1a",
  textSecondary: "#4B5563",
  textMuted: "#6B7280",

  // Backgrounds & borders
  surface: "#FFFFFF",
  subtleBg: "rgba(0,0,0,0.03)",
  subtleBorder: "rgba(0,0,0,0.06)",
  divider: "#E5E7EB",

  // Tab bar
  tabBarBg: "#FFFFFF",
  tabBarBorder: "rgba(0,0,0,0.08)",
  searchbarBg: "#F3F4F6",
  cardShadow: "0 2px 8px rgba(0,0,0,0.08)",

  // ── Backward-compat aliases (old green names → new blue) ──
  greenAccent: "rgba(37,99,235,0.10)",
  greenAccentStrong: "rgba(37,99,235,0.15)",
  orangeAccent: "rgba(249,115,22,0.10)",
  redAccent: "rgba(220,38,38,0.10)",
  greenDark: "#2563EB",
  greenMedium: "#3B82F6",
  greenLight: "#60A5FA",
  greenSubtle: "rgba(37,99,235,0.7)",
};

// ── Dark palette ─────────────────────────────────────────────────────────────

export const darkGradientColors = {
  start: "#121212",
  mid: "#151520",
  end: "#121212",
};

export const darkGlassColors: typeof lightGlassColors = {
  // Surfaces
  glass: "#1E1E2E",
  glassBorder: "rgba(255,255,255,0.10)",
  glassLight: "rgba(255,255,255,0.06)",
  glassDark: "#0F0F1A",

  // Semantic accents (subtle backgrounds)
  primarySubtle: "rgba(96,165,250,0.12)",
  primarySubtleStrong: "rgba(96,165,250,0.20)",
  accentSubtle: "rgba(251,146,60,0.15)",
  errorSubtle: "rgba(248,113,113,0.15)",
  successSubtle: "rgba(74,222,128,0.12)",

  // Core semantic colors
  primary: "#60A5FA",
  primaryMuted: "#93C5FD",
  primaryLight: "#BFDBFE",
  primaryFaded: "rgba(96,165,250,0.7)",
  accent: "#FB923C",
  success: "#4ADE80",
  warning: "#FBBF24",
  error: "#F87171",

  // Text
  textPrimary: "#E8E8E8",
  textSecondary: "#B0B0B0",
  textMuted: "#888",

  // Backgrounds & borders
  surface: "#1E1E2E",
  subtleBg: "rgba(255,255,255,0.04)",
  subtleBorder: "rgba(255,255,255,0.08)",
  divider: "rgba(255,255,255,0.10)",

  // Tab bar
  tabBarBg: "#1A1A28",
  tabBarBorder: "rgba(255,255,255,0.08)",
  searchbarBg: "rgba(255,255,255,0.06)",
  cardShadow: "0 2px 8px rgba(0,0,0,0.4)",

  // ── Backward-compat aliases (old green names → new blue) ──
  greenAccent: "rgba(96,165,250,0.12)",
  greenAccentStrong: "rgba(96,165,250,0.20)",
  orangeAccent: "rgba(251,146,60,0.15)",
  redAccent: "rgba(248,113,113,0.15)",
  greenDark: "#60A5FA",
  greenMedium: "#93C5FD",
  greenLight: "#BFDBFE",
  greenSubtle: "rgba(96,165,250,0.7)",
};

// ── Backward-compatible exports (light theme default) ────────────────────────

export const gradientColors = lightGradientColors;
export const glassColors = lightGlassColors;

export type GlassColorTokens = typeof lightGlassColors;

// Flat card style — no backdrop blur
const flatShadow = Platform.OS === "web"
  ? ({ boxShadow: "0 2px 8px rgba(0,0,0,0.08)" } as any)
  : {};

// Shared flat card style
export const glassCard: ViewStyle = {
  backgroundColor: glassColors.glass,
  borderRadius: 16,
  borderWidth: 1,
  borderColor: glassColors.glassBorder,
  elevation: 2,
  shadowColor: "#000",
  shadowOffset: { width: 0, height: 1 },
  shadowOpacity: 0.06,
  shadowRadius: 4,
  ...flatShadow,
} as any;

// Flat panel (for sections / headers)
export const glassPanel: ViewStyle = {
  backgroundColor: glassColors.glass,
  borderRadius: 16,
  borderWidth: 1,
  borderColor: glassColors.glassBorder,
} as any;

// Flat searchbar
export const glassSearchbar: ViewStyle = {
  backgroundColor: glassColors.searchbarBg,
  borderRadius: 12,
  borderWidth: 1,
  borderColor: glassColors.glassBorder,
  elevation: 0,
} as any;

// Flat chip
export const glassChip: ViewStyle = {
  backgroundColor: glassColors.glassLight,
  borderWidth: 1,
  borderColor: glassColors.glassBorder,
  borderRadius: 12,
} as any;

// Tab bar style (solid, no blur)
export const glassTabBar: ViewStyle = {
  position: "absolute",
  bottom: 16,
  left: 20,
  right: 20,
  height: 64,
  borderRadius: 24,
  backgroundColor: glassColors.tabBarBg,
  borderWidth: 1,
  borderColor: glassColors.tabBarBorder,
  elevation: 4,
  shadowColor: "#000",
  shadowOffset: { width: 0, height: 2 },
  shadowOpacity: 0.1,
  shadowRadius: 8,
  ...(Platform.OS === "web"
    ? ({ boxShadow: "0 4px 16px rgba(0,0,0,0.10)" } as any)
    : {}),
} as any;

// Header style (solid)
export const glassHeader: ViewStyle = {
  backgroundColor: glassColors.glass,
  borderBottomWidth: 1,
  borderBottomColor: glassColors.glassBorder,
  elevation: 0,
  shadowOpacity: 0,
} as any;

// Product image sizes
export const productImage = {
  card: { width: 72, height: 72, borderRadius: 12 },
  compact: { width: 52, height: 52, borderRadius: 10 },
  search: { width: 56, height: 56, borderRadius: 10 },
  detail: { width: "100%" as any, height: 200, borderRadius: 16 },
};

// Image placeholder style
export const imagePlaceholder: ViewStyle = {
  backgroundColor: glassColors.subtleBg,
  justifyContent: "center",
  alignItems: "center",
};

// Background for web (flat gradient)
export const gradientBackground = Platform.OS === "web"
  ? ({
      background: `linear-gradient(160deg, ${gradientColors.start}, ${gradientColors.mid}, ${gradientColors.end})`,
      minHeight: "100vh",
    } as any)
  : { backgroundColor: gradientColors.start };

// Chain badge style
export const chainBadgeGlass: ViewStyle = {
  backgroundColor: glassColors.primarySubtleStrong,
  borderRadius: 10,
  paddingHorizontal: 8,
  paddingVertical: 3,
};

// Discount badge style
export const discountBadgeGlass: ViewStyle = {
  backgroundColor: glassColors.accentSubtle,
  borderRadius: 8,
  paddingHorizontal: 6,
  paddingVertical: 2,
};

// Alert badge style
export const alertBadgeGlass: ViewStyle = {
  backgroundColor: glassColors.primarySubtle,
  borderRadius: 8,
  borderWidth: 1,
  borderColor: "rgba(37,99,235,0.2)",
  paddingHorizontal: 6,
  paddingVertical: 2,
};

// ── Theme-aware factory ──────────────────────────────────────────────────────

export interface GlassTheme {
  isDark: boolean;
  colors: GlassColorTokens;
  gradient: typeof lightGradientColors;
  card: ViewStyle;
  panel: ViewStyle;
  searchbar: ViewStyle;
  chip: ViewStyle;
  tabBar: ViewStyle;
  header: ViewStyle;
  background: any;
  chainBadge: ViewStyle;
  discountBadge: ViewStyle;
  alertBadge: ViewStyle;
  placeholder: ViewStyle;
}

export function getGlassStyles(isDark: boolean): GlassTheme {
  const c = isDark ? darkGlassColors : lightGlassColors;
  const g = isDark ? darkGradientColors : lightGradientColors;

  const flatShadowThemed = Platform.OS === "web"
    ? ({ boxShadow: c.cardShadow } as any)
    : {};

  const card: ViewStyle = {
    backgroundColor: c.glass,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: c.glassBorder,
    elevation: 2,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: isDark ? 0.2 : 0.06,
    shadowRadius: 4,
    ...flatShadowThemed,
  } as any;

  const panel: ViewStyle = {
    backgroundColor: c.glass,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: c.glassBorder,
  } as any;

  const searchbar: ViewStyle = {
    backgroundColor: c.searchbarBg,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: c.glassBorder,
    elevation: 0,
  } as any;

  const chip: ViewStyle = {
    backgroundColor: c.glassLight,
    borderWidth: 1,
    borderColor: c.glassBorder,
    borderRadius: 12,
  } as any;

  const tabBar: ViewStyle = {
    position: "absolute",
    bottom: 16,
    left: 20,
    right: 20,
    height: 64,
    borderRadius: 24,
    backgroundColor: c.tabBarBg,
    borderWidth: 1,
    borderColor: c.tabBarBorder,
    elevation: 4,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: isDark ? 0.3 : 0.1,
    shadowRadius: 8,
    ...(Platform.OS === "web"
      ? ({ boxShadow: isDark ? "0 4px 16px rgba(0,0,0,0.3)" : "0 4px 16px rgba(0,0,0,0.10)" } as any)
      : {}),
  } as any;

  const header: ViewStyle = {
    backgroundColor: c.glass,
    borderBottomWidth: 1,
    borderBottomColor: c.glassBorder,
    elevation: 0,
    shadowOpacity: 0,
  } as any;

  const background =
    Platform.OS === "web"
      ? ({
          background: `linear-gradient(160deg, ${g.start}, ${g.mid}, ${g.end})`,
          minHeight: "100vh",
        } as any)
      : { backgroundColor: g.start };

  return {
    isDark,
    colors: c,
    gradient: g,
    card,
    panel,
    searchbar,
    chip,
    tabBar,
    header,
    background,
    chainBadge: {
      backgroundColor: c.primarySubtleStrong,
      borderRadius: 10,
      paddingHorizontal: 8,
      paddingVertical: 3,
    },
    discountBadge: {
      backgroundColor: c.accentSubtle,
      borderRadius: 8,
      paddingHorizontal: 6,
      paddingVertical: 2,
    },
    alertBadge: {
      backgroundColor: c.primarySubtle,
      borderRadius: 8,
      borderWidth: 1,
      borderColor: isDark ? "rgba(96,165,250,0.3)" : "rgba(37,99,235,0.2)",
      paddingHorizontal: 6,
      paddingVertical: 2,
    },
    placeholder: {
      backgroundColor: c.subtleBg,
      justifyContent: "center" as const,
      alignItems: "center" as const,
    },
  };
}
