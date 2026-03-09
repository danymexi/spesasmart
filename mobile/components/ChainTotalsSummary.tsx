import { useState } from "react";
import { StyleSheet, TouchableOpacity, View } from "react-native";
import { Text } from "react-native-paper";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { glassCard, glassColors } from "../styles/glassStyles";
import { useGlassTheme } from "../styles/useGlassTheme";
import type { ChainTotalInfo } from "../services/api";

interface Props {
  chainTotals: ChainTotalInfo[];
  itemsTotal: number;
  multiStoreTotal: number;
  potentialSavings: number;
  onOpenOptimizer?: () => void;
}

export default function ChainTotalsSummary({
  chainTotals,
  itemsTotal,
  multiStoreTotal,
  potentialSavings,
  onOpenOptimizer,
}: Props) {
  const glass = useGlassTheme();
  const { colors } = glass;
  const [expanded, setExpanded] = useState(false);

  if (chainTotals.length === 0) return null;

  const best = chainTotals[0];

  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={[styles.card, glass.card, { borderColor: colors.primarySubtle }]}
        activeOpacity={0.7}
        onPress={() => setExpanded(!expanded)}
      >
        {/* Header row */}
        <View style={styles.headerRow}>
          <MaterialCommunityIcons
            name="cart-check"
            size={22}
            color={colors.primary}
          />
          <Text style={[styles.title, { color: colors.primary }]}>Confronto Spesa</Text>
          <MaterialCommunityIcons
            name={expanded ? "chevron-up" : "chevron-down"}
            size={22}
            color={colors.textMuted}
          />
        </View>

        {/* Best chain highlight */}
        <View style={styles.bestRow}>
          <View style={[styles.bestBadge, { backgroundColor: colors.primaryMuted }]}>
            <MaterialCommunityIcons name="star" size={14} color="#fff" />
          </View>
          <Text style={[styles.bestChain, { color: colors.primary }]}>{best.chain_name}</Text>
          <Text style={[styles.bestPrice, { color: colors.primary }]}>
            {"\u20AC"}{Number(best.total).toFixed(2)}
          </Text>
          <Text style={[styles.coverage, { color: colors.textMuted }]}>
            ({best.items_covered}/{itemsTotal})
          </Text>
        </View>

        {/* Expanded: all chains */}
        {expanded && (
          <View style={styles.chainList}>
            {chainTotals.slice(1).map((chain) => (
              <View key={chain.chain_slug} style={styles.chainRow}>
                <Text style={[styles.chainName, { color: colors.textPrimary }]}>{chain.chain_name}</Text>
                <Text style={[styles.chainPrice, { color: colors.textPrimary }]}>
                  {"\u20AC"}{Number(chain.total).toFixed(2)}
                </Text>
                <Text style={[styles.coverage, { color: colors.textMuted }]}>
                  ({chain.items_covered}/{itemsTotal})
                </Text>
              </View>
            ))}

            {/* Multi-store total */}
            <View style={[styles.divider, { backgroundColor: colors.subtleBorder }]} />
            <View style={styles.multiRow}>
              <MaterialCommunityIcons
                name="store-marker"
                size={16}
                color={colors.primary}
              />
              <Text style={[styles.multiLabel, { color: colors.primary }]}>Multi-negozio</Text>
              <Text style={[styles.multiPrice, { color: colors.primary }]}>
                {"\u20AC"}{Number(multiStoreTotal).toFixed(2)}
              </Text>
            </View>
            {potentialSavings > 0 && (
              <Text style={[styles.savings, { color: colors.primary }]}>
                Risparmio: {"\u20AC"}{Number(potentialSavings).toFixed(2)}
              </Text>
            )}

            {onOpenOptimizer && (
              <TouchableOpacity
                style={[styles.detailsBtn, { backgroundColor: colors.primarySubtle }]}
                onPress={onOpenOptimizer}
              >
                <Text style={[styles.detailsBtnText, { color: colors.primary }]}>Dettagli Ottimizzazione</Text>
                <MaterialCommunityIcons
                  name="arrow-right"
                  size={16}
                  color={colors.primary}
                />
              </TouchableOpacity>
            )}
          </View>
        )}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 12,
    marginBottom: 12,
  },
  card: {
    padding: 16,
    ...glassCard,
    borderColor: "rgba(46,125,50,0.25)",
  } as any,
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 12,
  },
  title: {
    flex: 1,
    fontSize: 16,
    fontWeight: "700",
    color: glassColors.greenDark,
  },
  bestRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  bestBadge: {
    backgroundColor: glassColors.greenMedium,
    borderRadius: 10,
    width: 22,
    height: 22,
    alignItems: "center",
    justifyContent: "center",
  },
  bestChain: {
    flex: 1,
    fontSize: 15,
    fontWeight: "700",
    color: glassColors.greenDark,
  },
  bestPrice: {
    fontSize: 18,
    fontWeight: "bold",
    color: glassColors.greenDark,
  },
  coverage: {
    fontSize: 12,
    color: glassColors.textMuted,
  },
  chainList: {
    marginTop: 12,
  },
  chainRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 6,
    gap: 8,
  },
  chainName: {
    flex: 1,
    fontSize: 14,
    color: glassColors.textPrimary,
  },
  chainPrice: {
    fontSize: 15,
    fontWeight: "600",
    color: glassColors.textPrimary,
  },
  divider: {
    height: 1,
    backgroundColor: glassColors.subtleBorder,
    marginVertical: 10,
  },
  multiRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  multiLabel: {
    flex: 1,
    fontSize: 14,
    fontWeight: "600",
    color: glassColors.greenDark,
  },
  multiPrice: {
    fontSize: 16,
    fontWeight: "bold",
    color: glassColors.greenDark,
  },
  savings: {
    marginTop: 4,
    fontSize: 13,
    fontWeight: "600",
    color: "#2E7D32",
    textAlign: "right",
  },
  detailsBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    marginTop: 12,
    paddingVertical: 10,
    backgroundColor: "rgba(46,125,50,0.08)",
    borderRadius: 12,
  },
  detailsBtnText: {
    fontSize: 14,
    fontWeight: "600",
    color: glassColors.greenDark,
  },
});
