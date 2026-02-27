import { Platform, ViewStyle } from "react-native";

// Gradient background colors (applied as CSS linear-gradient on web)
export const gradientColors = {
  start: "#E8F5E9",
  mid: "#E0F2F1",
  end: "#E3F2FD",
};

// Glass surface tokens
export const glassColors = {
  // Light glass
  glass: "rgba(255,255,255,0.72)",
  glassBorder: "rgba(255,255,255,0.45)",
  glassLight: "rgba(255,255,255,0.5)",
  glassDark: "rgba(30,30,30,0.6)",

  // Accent glass variants
  greenAccent: "rgba(27,94,32,0.12)",
  greenAccentStrong: "rgba(27,94,32,0.15)",
  orangeAccent: "rgba(255,111,0,0.12)",
  redAccent: "rgba(198,40,40,0.12)",

  // Text
  greenDark: "#1B5E20",
  greenMedium: "#2E7D32",
  greenSubtle: "rgba(27,94,32,0.7)",

  // Subtle backgrounds
  subtleBg: "rgba(0,0,0,0.04)",
  subtleBorder: "rgba(0,0,0,0.06)",
};

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
  backgroundColor: glassColors.glass,
  borderWidth: 1,
  borderColor: glassColors.glassBorder,
  elevation: 0,
  shadowOpacity: 0,
  ...webBlurStrong,
  ...(Platform.OS === "web"
    ? ({ boxShadow: "0 4px 30px rgba(0,0,0,0.08)" } as any)
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
