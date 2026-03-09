import { StyleSheet, View } from "react-native";
import { Text } from "react-native-paper";

type Indicator = "top" | "neutro" | "flop";

// Backward compat: map old API values to new
const COMPAT_MAP: Record<string, Indicator> = {
  ottimo: "top",
  medio: "neutro",
  alto: "flop",
  top: "top",
  neutro: "neutro",
  flop: "flop",
};

const INDICATOR_CONFIG: Record<Indicator, { color: string; bg: string; border: string; label: string }> = {
  top: { color: "#16A34A", bg: "rgba(22,163,74,0.12)", border: "rgba(22,163,74,0.25)", label: "Prezzo Top" },
  neutro: { color: "#F59E0B", bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.25)", label: "Nella media" },
  flop: { color: "#DC2626", bg: "rgba(220,38,38,0.12)", border: "rgba(220,38,38,0.25)", label: "Prezzo alto" },
};

interface Props {
  indicator: string | null | undefined;
}

export default function PriceIndicator({ indicator }: Props) {
  if (!indicator) return null;

  const mapped = COMPAT_MAP[indicator] ?? "neutro";
  const config = INDICATOR_CONFIG[mapped];

  return (
    <View style={[styles.container, { backgroundColor: config.bg, borderColor: config.border }]}>
      <View style={[styles.dot, { backgroundColor: config.color }]} />
      <Text variant="labelMedium" style={{ color: config.color, fontWeight: "bold" }}>
        {config.label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 14,
    borderWidth: 1,
    gap: 6,
  },
  dot: { width: 10, height: 10, borderRadius: 5 },
});
