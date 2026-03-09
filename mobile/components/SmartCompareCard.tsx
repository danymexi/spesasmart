import { Image, StyleSheet, TouchableOpacity, View } from "react-native";
import { IconButton, Text } from "react-native-paper";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { glassCard, glassColors, productImage, imagePlaceholder } from "../styles/glassStyles";
import { useGlassTheme } from "../styles/useGlassTheme";
import type { SmartSearchResult } from "../services/api";

const INDICATOR_STYLE: Record<string, { color: string; bg: string; label: string }> = {
  top: { color: "#16A34A", bg: "rgba(22,163,74,0.12)", label: "Top" },
  neutro: { color: "#F59E0B", bg: "rgba(245,158,11,0.12)", label: "Nella media" },
  flop: { color: "#DC2626", bg: "rgba(220,38,38,0.12)", label: "Caro" },
};

interface Props {
  result: SmartSearchResult;
  isInWatchlist?: boolean;
  onWatchlistToggle?: (productId: string) => void;
  onAddToShoppingList?: (productId: string) => void;
  selectable?: boolean;
  isSelected?: boolean;
  onToggleSelect?: () => void;
}

export default function SmartCompareCard({ result, isInWatchlist, onWatchlistToggle, onAddToShoppingList, selectable, isSelected, onToggleSelect }: Props) {
  const glass = useGlassTheme();
  const { colors } = glass;
  const { product, offers, price_indicator, best_price_per_unit, unit_reference } = result;

  const bestPrice = offers.length > 0
    ? Math.min(...offers.map((o) => o.offer_price))
    : null;

  const indConfig = price_indicator ? INDICATOR_STYLE[price_indicator] : null;

  return (
    <TouchableOpacity
      style={[
        styles.card,
        glass.card,
        isSelected && [styles.cardSelected, { backgroundColor: colors.primarySubtle, borderColor: colors.primary }],
      ]}
      onPress={() => {
        if (selectable && onToggleSelect) {
          onToggleSelect();
        } else {
          router.push(`/product/${product.id}`);
        }
      }}
      activeOpacity={0.7}
    >
      {/* Header: image + product name + indicator badge + watchlist */}
      <View style={styles.header}>
        {selectable && (
          <MaterialCommunityIcons
            name={isSelected ? "checkbox-marked" : "checkbox-blank-outline"}
            size={24}
            color={isSelected ? colors.primary : colors.textMuted}
            style={styles.checkbox}
          />
        )}
        {product.image_url ? (
          <Image
            source={{ uri: product.image_url }}
            style={styles.productImage}
            resizeMode="contain"
          />
        ) : (
          <View style={[styles.productImage, styles.productImagePlaceholder]}>
            <MaterialCommunityIcons name="food-variant" size={20} color={colors.textMuted} />
          </View>
        )}
        <View style={styles.nameSection}>
          <Text variant="titleSmall" numberOfLines={1} style={[styles.productName, { color: colors.textPrimary }]}>
            {product.name}
          </Text>
          {product.brand && (
            <Text variant="bodySmall" style={[styles.brand, { color: colors.textSecondary }]}>
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
        {!selectable && onAddToShoppingList && (
          <IconButton
            icon="cart-plus"
            iconColor={colors.primaryMuted}
            size={22}
            onPress={() => onAddToShoppingList(product.id)}
            style={styles.watchlistBtn}
          />
        )}
        {!selectable && onWatchlistToggle && (
          <IconButton
            icon={isInWatchlist ? "check-circle" : "plus-circle-outline"}
            iconColor={isInWatchlist ? colors.primaryMuted : colors.textMuted}
            size={24}
            onPress={() => onWatchlistToggle(product.id)}
            style={styles.watchlistBtn}
          />
        )}
      </View>

      {/* PPU summary */}
      {best_price_per_unit && (
        <Text variant="bodySmall" style={[styles.ppuSummary, { color: colors.primary }]}>
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
                style={[styles.chainCell, { backgroundColor: colors.subtleBg }, isBest && [styles.chainCellBest, { backgroundColor: colors.primarySubtle }]]}
              >
                <Text
                  style={[styles.chainName, { color: colors.textSecondary }, isBest && [styles.chainNameBest, { color: colors.primary }]]}
                  numberOfLines={1}
                >
                  {offer.chain_name}
                </Text>
                <Text style={[styles.chainPrice, { color: colors.textPrimary }, isBest && [styles.chainPriceBest, { color: colors.primary }]]}>
                  {"\u20AC"}{Number(offer.offer_price).toFixed(2)}
                </Text>
                {offer.price_per_unit && (
                  <Text style={[styles.chainPpu, { color: colors.textMuted }]}>
                    {"\u20AC"}{Number(offer.price_per_unit).toFixed(2)}/{offer.unit_reference || "kg"}
                  </Text>
                )}
                {offer.discount_pct && (
                  <Text style={[styles.discount, { color: colors.accent }, isBest && [styles.discountBest, { color: colors.primary }]]}>
                    -{Number(offer.discount_pct).toFixed(0)}%
                  </Text>
                )}
              </View>
            );
          })}
        </View>
      ) : (
        <Text variant="bodySmall" style={[styles.noOffers, { color: colors.textMuted }]}>
          Nessuna offerta attiva
        </Text>
      )}

      {result.is_category_match && (
        <View style={[styles.categoryBadge, { backgroundColor: colors.subtleBg }]}>
          <MaterialCommunityIcons name="tag-outline" size={12} color={colors.textMuted} />
          <Text style={[styles.categoryText, { color: colors.textMuted }]}>Confronto categoria</Text>
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
  cardSelected: {
    borderColor: glassColors.greenDark,
    borderWidth: 2,
    backgroundColor: "rgba(46,125,50,0.06)",
  },
  checkbox: {
    marginRight: 8,
    marginTop: 2,
  },
  header: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: 4,
  },
  productImage: {
    ...productImage.compact,
    marginRight: 10,
  },
  productImagePlaceholder: {
    ...imagePlaceholder,
  },
  nameSection: { flex: 1, marginRight: 8 },
  watchlistBtn: { margin: 0, marginLeft: 4 },
  productName: { fontWeight: "700", color: "#1a1a1a" },
  brand: { color: "#444", marginTop: 1 },
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
  chainName: { fontSize: 11, color: "#555", marginBottom: 2 },
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
