import { StyleSheet, TouchableOpacity, View } from "react-native";
import { Text } from "react-native-paper";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { glassCard, glassColors } from "../styles/glassStyles";
import type { SmartSearchResult } from "../services/api";

const INDICATOR_STYLE: Record<string, { color: string; bg: string; label: string }> = {
  top: { color: "#2E7D32", bg: "rgba(46,125,50,0.12)", label: "Top" },
  neutro: { color: "#F57F17", bg: "rgba(245,127,23,0.12)", label: "Nella media" },
  flop: { color: "#C62828", bg: "rgba(198,40,40,0.12)", label: "Caro" },
};

interface Props {
  result: SmartSearchResult;
}

export default function SmartCompareCard({ result }: Props) {
  const { product, offers, price_indicator, best_price_per_unit, unit_reference } = result;

  const bestPrice = offers.length > 0
    ? Math.min(...offers.map((o) => o.offer_price))
    : null;

  const indConfig = price_indicator ? INDICATOR_STYLE[price_indicator] : null;

  return (
    <TouchableOpacity
      style={styles.card}
      onPress={() => router.push(`/product/${product.id}`)}
      activeOpacity={0.7}
    >
      {/* Header: product name + indicator badge */}
      <View style={styles.header}>
        <View style={styles.nameSection}>
          <Text variant="titleSmall" numberOfLines={1} style={styles.productName}>
            {product.name}
          </Text>
          {product.brand && (
            <Text variant="bodySmall" style={styles.brand}>
              {product.brand}
            </Text>
          )}
        </View>
        {indConfig && (
          <View style={[styles.indicatorBadge, { backgroundColor: indConfig.bg }]}>
            <Text style={[styles.indicatorText, { color: indConfig.color }]}>
              {indConfig.label}
            </Text>
          </View>
        )}
      </View>

      {/* PPU summary */}
      {best_price_per_unit && (
        <Text variant="bodySmall" style={styles.ppuSummary}>
          Da {"\u20AC"}{Number(best_price_per_unit).toFixed(2)}/{unit_reference || "kg"}
        </Text>
      )}

      {/* Chain price comparison */}
      {offers.length > 0 ? (
        <View style={styles.chainsRow}>
          {offers.map((offer) => {
            const isBest = offers.length > 1 && offer.offer_price === bestPrice;
            return (
              <View
                key={offer.chain_slug}
                style={[styles.chainCell, isBest && styles.chainCellBest]}
              >
                <Text
                  style={[styles.chainName, isBest && styles.chainNameBest]}
                  numberOfLines={1}
                >
                  {offer.chain_name}
                </Text>
                <Text style={[styles.chainPrice, isBest && styles.chainPriceBest]}>
                  {"\u20AC"}{Number(offer.offer_price).toFixed(2)}
                </Text>
                {offer.price_per_unit && (
                  <Text style={styles.chainPpu}>
                    {"\u20AC"}{Number(offer.price_per_unit).toFixed(2)}/{offer.unit_reference || "kg"}
                  </Text>
                )}
                {offer.discount_pct && (
                  <Text style={[styles.discount, isBest && styles.discountBest]}>
                    -{Number(offer.discount_pct).toFixed(0)}%
                  </Text>
                )}
              </View>
            );
          })}
        </View>
      ) : (
        <Text variant="bodySmall" style={styles.noOffers}>
          Nessuna offerta attiva
        </Text>
      )}

      {result.is_category_match && (
        <View style={styles.categoryBadge}>
          <MaterialCommunityIcons name="tag-outline" size={12} color="#6D4C41" />
          <Text style={styles.categoryText}>Confronto categoria</Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 12,
    marginBottom: 10,
    padding: 14,
    ...glassCard,
  } as any,
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 4,
  },
  nameSection: { flex: 1, marginRight: 8 },
  productName: { fontWeight: "600" },
  brand: { color: "#666", marginTop: 1 },
  indicatorBadge: {
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  indicatorText: { fontSize: 11, fontWeight: "bold" },
  ppuSummary: {
    color: glassColors.greenDark,
    fontWeight: "600",
    fontSize: 12,
    marginBottom: 8,
  },
  chainsRow: {
    flexDirection: "row",
    gap: 8,
  },
  chainCell: {
    flex: 1,
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.03)",
    borderRadius: 12,
    paddingVertical: 8,
    paddingHorizontal: 6,
  },
  chainCellBest: {
    backgroundColor: "rgba(27,94,32,0.08)",
  },
  chainName: { fontSize: 11, color: "#888", marginBottom: 2 },
  chainNameBest: { color: glassColors.greenDark, fontWeight: "600" },
  chainPrice: { fontSize: 16, fontWeight: "bold", color: "#333" },
  chainPriceBest: { color: glassColors.greenDark },
  chainPpu: { fontSize: 10, color: "#888", marginTop: 1 },
  discount: { fontSize: 11, color: "#E65100", fontWeight: "bold", marginTop: 2 },
  discountBest: { color: glassColors.greenDark },
  noOffers: { color: "#888", fontStyle: "italic" },
  categoryBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    marginTop: 8,
    backgroundColor: "rgba(109,76,65,0.08)",
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
    alignSelf: "flex-start",
  },
  categoryText: { fontSize: 10, color: "#6D4C41", fontWeight: "600" },
});
