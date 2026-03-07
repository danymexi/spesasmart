import { Platform, ViewStyle } from "react-native";

// ── Light palette ────────────────────────────────────────────────────────────

export const lightGradientColors = {
  start: "#E8F5E9",
  mid: "#E0F2F1",
  end: "#E3F2FD",
};

export const lightGlassColors = {
  glass: "rgba(255,255,255,0.78)",
  glassBorder: "rgba(255,255,255,0.45)",
  glassLight: "rgba(255,255,255,0.5)",
  glassDark: "rgba(30,30,30,0.6)",

  greenAccent: "rgba(27,94,32,0.12)",
  greenAccentStrong: "rgba(27,94,32,0.15)",
  orangeAccent: "rgba(255,111,0,0.12)",
  redAccent: "rgba(198,40,40,0.12)",

  greenDark: "#1B5E20",
  greenMedium: "#2E7D32",
  greenLight: "#66BB6A",
  greenSubtle: "rgba(27,94,32,0.7)",
  textPrimary: "#1a1a1a",
  textSecondary: "#444",
  textMuted: "#666",

  subtleBg: "rgba(0,0,0,0.04)",
  subtleBorder: "rgba(0,0,0,0.06)",

  tabBarBg: "rgba(255,255,255,0.85)",
  tabBarBorder: "rgba(200,200,200,0.5)",
  searchbarBg: "rgba(255,255,255,0.6)",
  cardShadow: "0 8px 32px rgba(0,0,0,0.12)",
};

// ── Dark palette ─────────────────────────────────────────────────────────────

export const darkGradientColors = {
  start: "#121212",
  mid: "#1a1a2e",
  end: "#0d1b2a",
};

export const darkGlassColors: typeof lightGlassColors = {
  glass: "rgba(30,30,30,0.78)",
  glassBorder: "rgba(255,255,255,0.12)",
  glassLight: "rgba(255,255,255,0.08)",
  glassDark: "rgba(10,10,10,0.8)",

  greenAccent: "rgba(102,187,106,0.15)",
  greenAccentStrong: "rgba(102,187,106,0.22)",
  orangeAccent: "rgba(255,183,77,0.18)",
  redAccent: "rgba(239,83,80,0.18)",

  greenDark: "#81C784",
  greenMedium: "#66BB6A",
  greenLight: "#A5D6A7",
  greenSubtle: "rgba(102,187,106,0.7)",
  textPrimary: "#E8E8E8",
  textSecondary: "#B0B0B0",
  textMuted: "#888",

  subtleBg: "rgba(255,255,255,0.05)",
  subtleBorder: "rgba(255,255,255,0.08)",

  tabBarBg: "rgba(30,30,30,0.92)",
  tabBarBorder: "rgba(255,255,255,0.1)",
  searchbarBg: "rgba(255,255,255,0.08)",
  cardShadow: "0 8px 32px rgba(0,0,0,0.4)",
};

// ── Backward-compatible exports (light theme default) ────────────────────────

export const gradientColors = lightGradientColors;
export const glassColors = lightGlassColors;

export type GlassColorTokens = typeof lightGlassColors;

// Web-only backdrop filter styles (passed as `as any` for TypeScript)
const webBlur = Platform.OS === "web"
  ? ({
      backdropFilter: "blur(20px) saturate(180%)",
      WebkitBackdropFilter: "blur(20px) saturate(180%)",
    } as any)
  : {};

const webBlurStrong = Platform.OS === "web"
  ? ({
      backdropFilter: "blur(24px) saturate(200%)",
      WebkitBackdropFilter: "blur(24px) saturate(200%)",
    } as any)
  : {};

// Shared glass card style
export const glassCard: ViewStyle = {
  backgroundColor: glassColors.glass,
  borderRadius: 20,
  borderWidth: 1,
  borderColor: glassColors.glassBorder,
  elevation: 0,
  shadowOpacity: 0,
  ...webBlur,
} as any;

// Glass panel (for sections / headers)
export const glassPanel: ViewStyle = {
  backgroundColor: glassColors.glass,
  borderRadius: 20,
  borderWidth: 1,
  borderColor: glassColors.glassBorder,
  ...webBlur,
} as any;

// Glass searchbar
export const glassSearchbar: ViewStyle = {
  backgroundColor: "rgba(255,255,255,0.6)",
  borderRadius: 16,
  borderWidth: 1,
  borderColor: glassColors.glassBorder,
  elevation: 0,
  ...webBlur,
} as any;

// Glass chip
export const glassChip: ViewStyle = {
  backgroundColor: glassColors.glassLight,
  borderWidth: 1,
  borderColor: glassColors.glassBorder,
  borderRadius: 14,
} as any;

// Floating tab bar style
export const glassTabBar: ViewStyle = {
  position: "absolute",
  bottom: 16,
  left: 20,
  right: 20,
  height: 64,
  borderRadius: 28,
  backgroundColor: "rgba(255,255,255,0.85)",
  borderWidth: 1,
  borderColor: "rgba(200,200,200,0.5)",
  elevation: 0,
  shadowOpacity: 0,
  ...webBlurStrong,
  ...(Platform.OS === "web"
    ? ({ boxShadow: "0 8px 32px rgba(0,0,0,0.12)" } as any)
    : {}),
} as any;

// Glass header style (for Stack / Tabs headers)
export const glassHeader: ViewStyle = {
  backgroundColor: glassColors.glass,
  borderBottomWidth: 1,
  borderBottomColor: glassColors.glassBorder,
  elevation: 0,
  shadowOpacity: 0,
  ...webBlur,
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

// Gradient background for web (applied to contentStyle)
export const gradientBackground = Platform.OS === "web"
  ? ({
      background: `linear-gradient(160deg, ${gradientColors.start}, ${gradientColors.mid}, ${gradientColors.end})`,
      minHeight: "100vh",
    } as any)
  : { backgroundColor: gradientColors.start };

// Chain badge glass style
export const chainBadgeGlass: ViewStyle = {
  backgroundColor: glassColors.greenAccentStrong,
  borderRadius: 10,
  paddingHorizontal: 8,
  paddingVertical: 3,
};

// Discount badge glass style
export const discountBadgeGlass: ViewStyle = {
  backgroundColor: glassColors.orangeAccent,
  borderRadius: 8,
  paddingHorizontal: 6,
  paddingVertical: 2,
};

// Alert badge glass style
export const alertBadgeGlass: ViewStyle = {
  backgroundColor: glassColors.greenAccent,
  borderRadius: 8,
  borderWidth: 1,
  borderColor: "rgba(46,125,50,0.2)",
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

  const card: ViewStyle = {
    backgroundColor: c.glass,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: c.glassBorder,
    elevation: 0,
    shadowOpacity: 0,
    ...webBlur,
  } as any;

  const panel: ViewStyle = {
    backgroundColor: c.glass,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: c.glassBorder,
    ...webBlur,
  } as any;

  const searchbar: ViewStyle = {
    backgroundColor: c.searchbarBg,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: c.glassBorder,
    elevation: 0,
    ...webBlur,
  } as any;

  const chip: ViewStyle = {
    backgroundColor: c.glassLight,
    borderWidth: 1,
    borderColor: c.glassBorder,
    borderRadius: 14,
  } as any;

  const tabBar: ViewStyle = {
    position: "absolute",
    bottom: 16,
    left: 20,
    right: 20,
    height: 64,
    borderRadius: 28,
    backgroundColor: c.tabBarBg,
    borderWidth: 1,
    borderColor: c.tabBarBorder,
    elevation: 0,
    shadowOpacity: 0,
    ...webBlurStrong,
    ...(Platform.OS === "web"
      ? ({ boxShadow: c.cardShadow } as any)
      : {}),
  } as any;

  const header: ViewStyle = {
    backgroundColor: c.glass,
    borderBottomWidth: 1,
    borderBottomColor: c.glassBorder,
    elevation: 0,
    shadowOpacity: 0,
    ...webBlur,
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
      backgroundColor: c.greenAccentStrong,
      borderRadius: 10,
      paddingHorizontal: 8,
      paddingVertical: 3,
    },
    discountBadge: {
      backgroundColor: c.orangeAccent,
      borderRadius: 8,
      paddingHorizontal: 6,
      paddingVertical: 2,
    },
    alertBadge: {
      backgroundColor: c.greenAccent,
      borderRadius: 8,
      borderWidth: 1,
      borderColor: isDark ? "rgba(102,187,106,0.3)" : "rgba(46,125,50,0.2)",
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
