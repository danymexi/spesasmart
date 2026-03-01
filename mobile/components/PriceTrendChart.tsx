import { Dimensions, StyleSheet, View } from "react-native";
import { Text } from "react-native-paper";
import { LineChart } from "react-native-chart-kit";
import { glassPanel, glassColors } from "../styles/glassStyles";
import type { PriceTrendPoint } from "../services/api";

interface Props {
  trends: PriceTrendPoint[];
  unitReference: string | null;
}

const SCREEN_WIDTH = Dimensions.get("window").width;

function unitLabel(unitRef: string | null): string {
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

export default function PriceTrendChart({ trends, unitReference }: Props) {
  // Filter to periods that have price_per_unit data
  const withPpu = trends.filter((t) => t.avg_price_per_unit != null);

  if (withPpu.length < 2) {
    return (
      <View style={styles.empty}>
        <Text variant="bodyMedium" style={styles.emptyText}>
          Dati insufficienti per l'andamento
        </Text>
      </View>
    );
  }

  const labels = withPpu.map((t) => {
    const [, month] = t.period.split("-");
    const monthNames = [
      "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
      "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
    ];
    return monthNames[parseInt(month, 10) - 1] || month;
  });

  const avgData = withPpu.map((t) => Number(t.avg_price_per_unit));
  const minData = withPpu.map((t) => Number(t.min_price_per_unit));
  const maxData = withPpu.map((t) => Number(t.max_price_per_unit));

  // Compute 12-month average
  const totalAvg =
    avgData.reduce((sum, v) => sum + v, 0) / avgData.length;

  const label = unitLabel(unitReference);

  return (
    <View style={styles.container}>
      <LineChart
        data={{
          labels,
          datasets: [
            {
              data: maxData,
              strokeWidth: 1,
              color: (opacity = 1) => `rgba(198, 40, 40, ${opacity * 0.5})`,
            },
            {
              data: avgData,
              strokeWidth: 2,
              color: (opacity = 1) => `rgba(27, 94, 32, ${opacity})`,
            },
            {
              data: minData,
              strokeWidth: 1,
              color: (opacity = 1) => `rgba(21, 101, 192, ${opacity * 0.5})`,
            },
          ],
          legend: ["Max", "Media", "Min"],
        }}
        width={SCREEN_WIDTH - 64}
        height={220}
        yAxisLabel={"\u20AC"}
        yAxisSuffix=""
        chartConfig={{
          backgroundColor: "transparent",
          backgroundGradientFrom: "rgba(255,255,255,0.01)",
          backgroundGradientTo: "rgba(255,255,255,0.01)",
          decimalPlaces: 2,
          color: (opacity = 1) => `rgba(27, 94, 32, ${opacity})`,
          labelColor: (opacity = 1) => `rgba(0, 0, 0, ${opacity * 0.6})`,
          propsForDots: { r: "3", strokeWidth: "1" },
          propsForBackgroundLines: {
            strokeDasharray: "",
            stroke: "rgba(0,0,0,0.06)",
          },
        }}
        bezier
        style={styles.chart}
      />

      <View style={styles.summary}>
        <Text variant="bodyMedium" style={styles.summaryText}>
          Media {withPpu.length} mesi:{" "}
          <Text style={styles.summaryValue}>
            {totalAvg.toFixed(2)} {label}
          </Text>
        </Text>
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
  summary: {
    marginTop: 12,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "rgba(0,0,0,0.06)",
    alignItems: "center",
  },
  summaryText: { color: "#666" },
  summaryValue: {
    fontWeight: "bold",
    color: glassColors.greenDark,
  },
});
