import { useState } from "react";
import { Dimensions, StyleSheet, View } from "react-native";
import { Chip, Text } from "react-native-paper";
import { LineChart } from "react-native-chart-kit";
import { glassPanel } from "../styles/glassStyles";

interface PricePoint {
  date: string;
  price: number | string;
  chain_name: string;
  discount_type?: string | null;
  price_per_unit?: number | null;
  unit_reference?: string | null;
}

interface Props {
  data: PricePoint[];
}

const CHAIN_COLORS: Record<string, string> = {
  Esselunga: "#D32F2F",
  Lidl: "#0039A6",
  Coop: "#E53935",
  Iperal: "#1565C0",
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

export default function PriceChart({ data }: Props) {
  const hasPpu = data.some((p) => p.price_per_unit != null);
  const [viewMode, setViewMode] = useState<ViewMode>(hasPpu ? "price_per_unit" : "price");

  if (!data || data.length === 0) {
    return (
      <View style={styles.empty}>
        <Text variant="bodyMedium" style={styles.emptyText}>
          Dati insufficienti per il grafico
        </Text>
      </View>
    );
  }

  // Sort by date ascending
  const sorted = [...data].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
  );

  // Filter to points that have the selected value
  const filtered =
    viewMode === "price_per_unit"
      ? sorted.filter((p) => p.price_per_unit != null)
      : sorted;

  // Take last 24 data points max
  const recent = filtered.slice(-24);

  if (recent.length === 0) {
    return (
      <View style={styles.empty}>
        <Text variant="bodyMedium" style={styles.emptyText}>
          Dati insufficienti per il grafico
        </Text>
      </View>
    );
  }

  const labels = recent.map((p) => {
    const d = new Date(p.date);
    return `${d.getDate()}/${d.getMonth() + 1}`;
  });

  const prices = recent.map((p) =>
    viewMode === "price_per_unit" ? Number(p.price_per_unit) : Number(p.price)
  );

  // Determine unit reference from data
  const unitRef = recent.find((p) => p.unit_reference)?.unit_reference;
  const yAxisLabel =
    viewMode === "price_per_unit" ? "" : "\u20AC";
  const yAxisSuffix =
    viewMode === "price_per_unit"
      ? ` ${getUnitLabel(unitRef).replace("EUR", "\u20AC")}`
      : "";

  // Get chains for the legend
  const chains = [...new Set(recent.map((p) => p.chain_name))];

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

      <LineChart
        data={{
          labels,
          datasets: [{ data: prices, strokeWidth: 2 }],
        }}
        width={SCREEN_WIDTH - 64}
        height={200}
        yAxisLabel={yAxisLabel}
        yAxisSuffix={yAxisSuffix}
        chartConfig={{
          backgroundColor: "transparent",
          backgroundGradientFrom: "rgba(255,255,255,0.01)",
          backgroundGradientTo: "rgba(255,255,255,0.01)",
          decimalPlaces: 2,
          color: (opacity = 1) => `rgba(27, 94, 32, ${opacity})`,
          labelColor: (opacity = 1) => `rgba(0, 0, 0, ${opacity * 0.6})`,
          propsForDots: { r: "4", strokeWidth: "2", stroke: "#1B5E20" },
          propsForBackgroundLines: {
            strokeDasharray: "",
            stroke: "rgba(0,0,0,0.06)",
          },
        }}
        bezier
        style={styles.chart}
      />

      {/* Legend */}
      <View style={styles.legend}>
        {chains.map((chain) => (
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
    marginBottom: 12,
  },
  toggleChip: {
    height: 32,
  },
  chart: { borderRadius: 12 },
  empty: { padding: 20, alignItems: "center" },
  emptyText: { color: "#888" },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 8, paddingLeft: 4 },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
});
