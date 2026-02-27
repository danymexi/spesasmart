import { Dimensions, StyleSheet, View } from "react-native";
import { Text } from "react-native-paper";
import { LineChart } from "react-native-chart-kit";
import { glassPanel } from "../styles/glassStyles";

interface PricePoint {
  date: string;
  price: number | string;
  chain_name: string;
  discount_type?: string | null;
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

export default function PriceChart({ data }: Props) {
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

  // Take last 12 data points max
  const recent = sorted.slice(-12);

  const labels = recent.map((p) => {
    const d = new Date(p.date);
    return `${d.getDate()}/${d.getMonth() + 1}`;
  });

  const prices = recent.map((p) => Number(p.price));

  // Get chains for the legend
  const chains = [...new Set(recent.map((p) => p.chain_name))];

  return (
    <View style={styles.container}>
      <LineChart
        data={{
          labels,
          datasets: [{ data: prices, strokeWidth: 2 }],
        }}
        width={SCREEN_WIDTH - 64}
        height={200}
        yAxisLabel={"\u20AC"}
        yAxisSuffix=""
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
  chart: { borderRadius: 12 },
  empty: { padding: 20, alignItems: "center" },
  emptyText: { color: "#888" },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 8, paddingLeft: 4 },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
});
