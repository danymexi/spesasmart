import { useState } from "react";
import { StyleSheet, TouchableOpacity, View } from "react-native";
import { Text } from "react-native-paper";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { router } from "expo-router";
import { glassCard, glassColors } from "../styles/glassStyles";
import { useGlassTheme } from "../styles/useGlassTheme";
import type { ShoppingListCompareResponse } from "../services/api";

interface Props {
  compareData: ShoppingListCompareResponse;
  itemCount: number;
}

export default function HomeSpesaSummary({ compareData, itemCount }: Props) {
  const glass = useGlassTheme();
  const { colors } = glass;
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  const toggle = (key: string) =>
    setExpandedRow((prev) => (prev === key ? null : key));

  const { items, chain_totals, multi_store_total } = compareData;

  return (
    <View style={styles.container}>
      <View style={[styles.card, glass.card, { borderColor: colors.primarySubtle }]}>
        {/* Header */}
        <View style={styles.headerRow}>
          <MaterialCommunityIcons
            name="cart-check"
            size={22}
            color={colors.primary}
          />
          <Text style={[styles.title, { color: colors.primary }]}>
            La tua Spesa ({itemCount} articol{itemCount === 1 ? "o" : "i"})
          </Text>
        </View>

        {/* Multi-negozio row */}
        <TouchableOpacity
          style={styles.multiRow}
          activeOpacity={0.7}
          onPress={() => toggle("multi")}
        >
          <View style={[styles.starBadge, { backgroundColor: colors.primaryMuted }]}>
            <MaterialCommunityIcons name="star" size={14} color="#fff" />
          </View>
          <Text style={[styles.multiLabel, { color: colors.primary }]}>Multi-negozio</Text>
          <Text style={[styles.multiPrice, { color: colors.primary }]}>
            {"\u20AC"}{Number(multi_store_total).toFixed(2)}
          </Text>
          <MaterialCommunityIcons
            name={expandedRow === "multi" ? "chevron-down" : "chevron-right"}
            size={18}
            color={colors.textMuted}
          />
        </TouchableOpacity>

        {/* Multi-negozio expanded detail */}
        {expandedRow === "multi" && (
          <View style={styles.expandedList}>
            {items.map((item) => {
              const best = item.chain_prices.find((cp) => cp.is_best);
              return (
                <View key={item.item_id} style={styles.productRow}>
                  <Text style={[styles.productName, { color: colors.textSecondary }]} numberOfLines={1}>
                    {best ? (best.product_name || item.display_name) : item.display_name}
                  </Text>
                  {best ? (
                    <>
                      <Text style={[styles.productChain, { color: colors.textMuted }]}>{best.chain_name}</Text>
                      <Text style={[styles.productPrice, { color: colors.textPrimary }]}>
                        {"\u20AC"}{Number(best.offer_price).toFixed(2)}
                      </Text>
                    </>
                  ) : (
                    <Text style={[styles.noMatch, { color: colors.textMuted }]}>non trovato</Text>
                  )}
                </View>
              );
            })}
          </View>
        )}

        {/* Divider */}
        <View style={[styles.divider, { backgroundColor: colors.subtleBorder }]} />

        {/* Per-chain rows */}
        {chain_totals.map((chain) => (
          <View key={chain.chain_slug}>
            <TouchableOpacity
              style={styles.chainRow}
              activeOpacity={0.7}
              onPress={() => toggle(chain.chain_slug)}
            >
              <Text style={[styles.chainName, { color: colors.textPrimary }]}>{chain.chain_name}</Text>
              <Text style={[styles.chainPrice, { color: colors.textPrimary }]}>
                {"\u20AC"}{Number(chain.total).toFixed(2)}
              </Text>
              <Text style={[styles.coverage, { color: colors.textMuted }]}>
                ({chain.items_covered}/{itemCount})
              </Text>
              <MaterialCommunityIcons
                name={
                  expandedRow === chain.chain_slug
                    ? "chevron-down"
                    : "chevron-right"
                }
                size={18}
                color={colors.textMuted}
              />
            </TouchableOpacity>

            {/* Chain expanded detail */}
            {expandedRow === chain.chain_slug && (
              <View style={styles.expandedList}>
                {items
                  .filter((item) =>
                    item.chain_prices.some(
                      (cp) => cp.chain_slug === chain.chain_slug
                    )
                  )
                  .map((item) => {
                    const cp = item.chain_prices.find(
                      (p) => p.chain_slug === chain.chain_slug
                    )!;
                    return (
                      <View key={item.item_id} style={styles.productRow}>
                        <Text style={[styles.productName, { color: colors.textSecondary }]} numberOfLines={1}>
                          {cp.product_name || item.display_name}
                        </Text>
                        <Text style={[styles.productPrice, { color: colors.textPrimary }]}>
                          {"\u20AC"}{Number(cp.offer_price).toFixed(2)}
                        </Text>
                      </View>
                    );
                  })}
              </View>
            )}
          </View>
        ))}

        {/* Footer link */}
        <TouchableOpacity
          style={[styles.footerBtn, { backgroundColor: colors.primarySubtle }]}
          activeOpacity={0.7}
          onPress={() => router.push("/(tabs)/watchlist")}
        >
          <Text style={[styles.footerBtnText, { color: colors.primary }]}>Vai alla Lista</Text>
          <MaterialCommunityIcons
            name="arrow-right"
            size={16}
            color={colors.primary}
          />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 12,
    marginTop: 12,
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
  multiRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 6,
  },
  starBadge: {
    backgroundColor: glassColors.greenMedium,
    borderRadius: 10,
    width: 22,
    height: 22,
    alignItems: "center",
    justifyContent: "center",
  },
  multiLabel: {
    flex: 1,
    fontSize: 15,
    fontWeight: "700",
    color: glassColors.greenDark,
  },
  multiPrice: {
    fontSize: 18,
    fontWeight: "bold",
    color: glassColors.greenDark,
  },
  divider: {
    height: 1,
    backgroundColor: glassColors.subtleBorder,
    marginVertical: 10,
  },
  chainRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    gap: 8,
  },
  chainName: {
    flex: 1,
    fontSize: 14,
    fontWeight: "600",
    color: glassColors.textPrimary,
  },
  chainPrice: {
    fontSize: 15,
    fontWeight: "600",
    color: glassColors.textPrimary,
  },
  coverage: {
    fontSize: 12,
    color: glassColors.textMuted,
    minWidth: 36,
  },
  expandedList: {
    paddingLeft: 16,
    paddingBottom: 6,
  },
  productRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 4,
    gap: 6,
  },
  productName: {
    flex: 1,
    fontSize: 13,
    color: glassColors.textSecondary,
  },
  productChain: {
    fontSize: 11,
    color: glassColors.textMuted,
    fontWeight: "500",
  },
  productPrice: {
    fontSize: 13,
    fontWeight: "600",
    color: glassColors.textPrimary,
  },
  noMatch: {
    fontSize: 12,
    fontStyle: "italic",
    color: glassColors.textMuted,
  },
  footerBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    marginTop: 12,
    paddingVertical: 10,
    backgroundColor: "rgba(46,125,50,0.08)",
    borderRadius: 12,
  },
  footerBtnText: {
    fontSize: 14,
    fontWeight: "600",
    color: glassColors.greenDark,
  },
});
