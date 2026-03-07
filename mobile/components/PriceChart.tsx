import { useState, useMemo } from "react";
import { Dimensions, StyleSheet, View } from "react-native";
import { Chip, Text } from "react-native-paper";
import { LineChart } from "react-native-chart-kit";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { glassPanel, glassColors } from "../styles/glassStyles";

interface PricePoint {
  date: string;
  price: number | string;
  chain_name: string;
  chain_slug?: string | null;
  discount_type?: string | null;
  price_per_unit?: number | null;
  unit_reference?: string | null;
}

interface Props {
  data: PricePoint[];
}

const CHAIN_COLORS: Record<string, string> = {
  Esselunga: "#E30613",
  Lidl: "#0050AA",
  Coop: "#E07000",
  Iperal: "#009639",
  Conad: "#D4A017",
  Carrefour: "#004E9A",
  Eurospin: "#1B5E20",
  MD: "#FF6F00",
  "Penny Market": "#CC0000",
  Aldi: "#00529B",
  Bennet: "#E91E63",
  Pam: "#8BC34A",
};

const SCREEN_WIDTH = Dimensions.get("window").width;

type ViewMode = "price" | "price_per_unit";

function getUnitLabel(unitRef: string | null | undefined): string {
  switch (unitRef) {
    case "kg":
      return "EUR/kg";
    case "l":
      return "EUR/L";
    case "pz":
      return "EUR/pz";
    default:
      return "EUR/kg";
  }
}

function computeMovingAverage(values: number[], window: number): (number | null)[] {
  return values.map((_, i) => {
    if (i < window - 1) return null;
    const slice = values.slice(i - window + 1, i + 1);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
}

function getTrendText(prices: number[]): { text: string; color: string; icon: "trending-down" | "trending-up" | "trending-neutral" } {
  if (prices.length < 3) return { text: "Dati insufficienti", color: "#888", icon: "trending-neutral" };

  // Check last 3 data points
  const recent = prices.slice(-3);
  const allDecreasing = recent.every((v, i) => i === 0 || v <= recent[i - 1]);
  const allIncreasing = recent.every((v, i) => i === 0 || v >= recent[i - 1]);

  // Count consecutive weeks of decline/increase from the end
  let streak = 0;
  for (let i = prices.length - 1; i > 0; i--) {
    if (prices[i] < prices[i - 1]) streak++;
    else break;
  }

  if (allDecreasing && streak >= 2) {
    return { text: `In calo da ${streak} settimane`, color: "#2E7D32", icon: "trending-down" };
  }

  let upStreak = 0;
  for (let i = prices.length - 1; i > 0; i--) {
    if (prices[i] > prices[i - 1]) upStreak++;
    else break;
  }

  if (allIncreasing && upStreak >= 2) {
    return { text: `In aumento da ${upStreak} settimane`, color: "#C62828", icon: "trending-up" };
  }

  return { text: "Prezzo stabile", color: "#666", icon: "trending-neutral" };
}

export default function PriceChart({ data }: Props) {
  const hasPpu = data.some((p) => p.price_per_unit != null);
  const [viewMode, setViewMode] = useState<ViewMode>(hasPpu ? "price_per_unit" : "price");

  const chartData = useMemo(() => {
    if (!data || data.length === 0) return null;

    // Sort by date ascending
    const sorted = [...data].sort(
      (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
    );

    // Filter to points that have the selected value
    const filtered =
      viewMode === "price_per_unit"
        ? sorted.filter((p) => p.price_per_unit != null)
        : sorted;

    // Take last 30 data points max
    const recent = filtered.slice(-30);

    if (recent.length === 0) return null;

    // Get unique chains
    const chains = [...new Set(recent.map((p) => p.chain_name))];

    // Build labels from unique dates
    const dates = [...new Set(recent.map((p) => p.date))].sort();
    const labels = dates.map((d) => {
      const dt = new Date(d);
      return `${dt.getDate()}/${dt.getMonth() + 1}`;
    });

    // Build one dataset per chain
    const datasets = chains.map((chain) => {
      const chainPoints = recent.filter((p) => p.chain_name === chain);
      const chainPriceMap = new Map<string, number>();
      for (const p of chainPoints) {
        const val = viewMode === "price_per_unit" ? Number(p.price_per_unit) : Number(p.price);
        chainPriceMap.set(p.date, val);
      }

      const values = dates.map((d) => chainPriceMap.get(d) ?? 0);
      const color = CHAIN_COLORS[chain] || "#666";

      return { data: values, color: () => color, strokeWidth: 2 };
    });

    // Compute all prices for trend and min
    const allPrices = recent.map((p) =>
      viewMode === "price_per_unit" ? Number(p.price_per_unit) : Number(p.price)
    );

    // Moving average (4-week window)
    const movingAvg = computeMovingAverage(allPrices, 4);
    const maValues = movingAvg.map((v) => v ?? allPrices[0]);

    datasets.push({
      data: maValues,
      color: () => "rgba(0,0,0,0.3)",
      strokeWidth: 1,
    });

    // Find historic low
    const minPrice = Math.min(...allPrices.filter((v) => v > 0));
    const minIndex = allPrices.indexOf(minPrice);

    // Trend indicator
    const trend = getTrendText(allPrices.filter((v) => v > 0));

    return { labels, datasets, chains, trend, minPrice, minIndex, allPrices };
  }, [data, viewMode]);

  if (!chartData) {
    return (
      <View style={styles.empty}>
        <Text variant="bodyMedium" style={styles.emptyText}>
          Dati insufficienti per il grafico
        </Text>
      </View>
    );
  }

  const unitRef = data.find((p) => p.unit_reference)?.unit_reference;
  const yAxisLabel = viewMode === "price_per_unit" ? "" : "\u20AC";
  const yAxisSuffix =
    viewMode === "price_per_unit"
      ? ` ${getUnitLabel(unitRef).replace("EUR", "\u20AC")}`
      : "";

  // Show fewer labels to avoid crowding
  const showEvery = Math.max(1, Math.floor(chartData.labels.length / 6));
  const displayLabels = chartData.labels.map((l, i) =>
    i % showEvery === 0 ? l : ""
  );

  return (
    <View style={styles.container}>
      {/* Toggle chips */}
      {hasPpu && (
        <View style={styles.toggleRow}>
          <Chip
            selected={viewMode === "price"}
            onPress={() => setViewMode("price")}
            compact
            style={styles.toggleChip}
          >
            Prezzo
          </Chip>
          <Chip
            selected={viewMode === "price_per_unit"}
            onPress={() => setViewMode("price_per_unit")}
            compact
            style={styles.toggleChip}
          >
            Prezzo al {unitRef === "l" ? "litro" : "kg"}
          </Chip>
        </View>
      )}

      {/* Trend indicator */}
      <View style={styles.trendRow}>
        <MaterialCommunityIcons
          name={chartData.trend.icon}
          size={18}
          color={chartData.trend.color}
        />
        <Text variant="bodySmall" style={[styles.trendText, { color: chartData.trend.color }]}>
          {chartData.trend.text}
        </Text>
        <Text variant="labelSmall" style={styles.minText}>
          Min storico: {"\u20AC"}{chartData.minPrice.toFixed(2)}
        </Text>
      </View>

      <LineChart
        data={{
          labels: displayLabels,
          datasets: chartData.datasets,
        }}
        width={SCREEN_WIDTH - 64}
        height={220}
        yAxisLabel={yAxisLabel}
        yAxisSuffix={yAxisSuffix}
        chartConfig={{
          backgroundColor: "transparent",
          backgroundGradientFrom: "rgba(255,255,255,0.01)",
          backgroundGradientTo: "rgba(255,255,255,0.01)",
          decimalPlaces: 2,
          color: (opacity = 1) => `rgba(100, 100, 100, ${opacity})`,
          labelColor: (opacity = 1) => `rgba(0, 0, 0, ${opacity * 0.6})`,
          propsForDots: { r: "3", strokeWidth: "1" },
          propsForBackgroundLines: {
            strokeDasharray: "",
            stroke: "rgba(0,0,0,0.06)",
          },
        }}
        bezier
        style={styles.chart}
        withShadow={false}
      />

      {/* Legend */}
      <View style={styles.legend}>
        {chartData.chains.map((chain) => (
          <View key={chain} style={styles.legendItem}>
            <View
              style={[
                styles.legendDot,
                { backgroundColor: CHAIN_COLORS[chain] ?? "#666" },
              ]}
            />
            <Text variant="labelSmall">{chain}</Text>
          </View>
        ))}
        <View style={styles.legendItem}>
          <View style={[styles.legendLine]} />
          <Text variant="labelSmall" style={styles.legendMa}>Media mobile</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 12,
    padding: 12,
    marginBottom: 8,
    ...glassPanel,
  } as any,
  toggleRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 8,
  },
  toggleChip: {
    height: 32,
  },
  trendRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 10,
    paddingHorizontal: 4,
  },
  trendText: { fontWeight: "600", fontSize: 13 },
  minText: { marginLeft: "auto", color: "#888", fontSize: 11 },
  chart: { borderRadius: 12 },
  empty: { padding: 20, alignItems: "center" },
  emptyText: { color: "#888" },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 8, paddingLeft: 4 },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  legendLine: {
    width: 16,
    height: 0,
    borderTopWidth: 2,
    borderStyle: "dashed",
    borderColor: "rgba(0,0,0,0.3)",
  },
  legendMa: { color: "#888" },
});
