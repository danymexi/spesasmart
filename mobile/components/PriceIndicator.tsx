import { StyleSheet, View } from "react-native";
import { Text } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { getProductHistory, getProductBestPrice } from "../services/api";

interface Props {
  productId: string;
}

type Indicator = "ottimo" | "medio" | "alto";

function computeIndicator(currentPrice: number, history: { price: number | string }[]): Indicator {
  if (history.length === 0) return "medio";

  const prices = history.map((h) => Number(h.price));
  const avg = prices.reduce((sum, p) => sum + p, 0) / prices.length;

  if (currentPrice < avg * 0.8) return "ottimo";
  if (currentPrice > avg * 1.1) return "alto";
  return "medio";
}

const INDICATOR_CONFIG: Record<Indicator, { color: string; bg: string; border: string; label: string }> = {
  ottimo: { color: "#2E7D32", bg: "rgba(46,125,50,0.12)", border: "rgba(46,125,50,0.25)", label: "Ottimo prezzo" },
  medio: { color: "#F57F17", bg: "rgba(245,127,23,0.12)", border: "rgba(245,127,23,0.25)", label: "Nella media" },
  alto: { color: "#C62828", bg: "rgba(198,40,40,0.12)", border: "rgba(198,40,40,0.25)", label: "Prezzo alto" },
};

export default function PriceIndicator({ productId }: Props) {
  const { data: bestPrice } = useQuery({
    queryKey: ["bestPrice", productId],
    queryFn: () => getProductBestPrice(productId),
  });

  const { data: history } = useQuery({
    queryKey: ["productHistory", productId],
    queryFn: () => getProductHistory(productId),
  });

  if (!bestPrice || !history) return null;

  const indicator = computeIndicator(
    Number(bestPrice.best_price),
    history.history
  );
  const config = INDICATOR_CONFIG[indicator];

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
