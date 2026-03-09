import { StyleSheet, View } from "react-native";
import { Text } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { getBudget } from "../services/api";
import { useGlassTheme } from "../styles/useGlassTheme";
import { useAppStore } from "../stores/useAppStore";

function getBarColor(pct: number): string {
  if (pct < 60) return "#16A34A"; // green
  if (pct < 85) return "#F59E0B"; // yellow
  return "#DC2626"; // red
}

export default function BudgetProgressBar() {
  const glass = useGlassTheme();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);

  const { data: budget } = useQuery({
    queryKey: ["budget"],
    queryFn: getBudget,
    enabled: isLoggedIn,
    staleTime: 5 * 60 * 1000,
  });

  if (!budget || budget.monthly_budget == null) return null;

  const pct = Math.min(budget.progress_pct ?? 0, 100);
  const barColor = getBarColor(pct);

  return (
    <View style={[styles.container, { backgroundColor: glass.colors.surface }]}>
      <View style={styles.header}>
        <Text variant="labelMedium" style={{ color: glass.colors.textSecondary }}>
          Budget mensile
        </Text>
        <Text variant="labelMedium" style={{ color: glass.colors.textPrimary, fontWeight: "600" }}>
          {"\u20AC"}{budget.spent_this_month.toFixed(2)} / {"\u20AC"}{budget.monthly_budget.toFixed(2)}
        </Text>
      </View>
      <View style={styles.trackOuter}>
        <View
          style={[
            styles.trackInner,
            { width: `${pct}%`, backgroundColor: barColor },
          ]}
        />
      </View>
      {budget.remaining != null && (
        <Text
          variant="labelSmall"
          style={{
            color: budget.remaining >= 0 ? "#16A34A" : "#DC2626",
            marginTop: 4,
          }}
        >
          {budget.remaining >= 0
            ? `Rimangono \u20AC${budget.remaining.toFixed(2)}`
            : `Superato di \u20AC${Math.abs(budget.remaining).toFixed(2)}`}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 12,
    marginTop: 12,
    padding: 14,
    borderRadius: 16,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  trackOuter: {
    height: 8,
    backgroundColor: "rgba(0,0,0,0.08)",
    borderRadius: 4,
    overflow: "hidden",
  },
  trackInner: {
    height: 8,
    borderRadius: 4,
  },
});
