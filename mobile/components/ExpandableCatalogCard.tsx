import { useState, useCallback } from "react";
import {
  Image,
  LayoutAnimation,
  Platform,
  StyleSheet,
  TouchableOpacity,
  View,
} from "react-native";
import { IconButton, Text } from "react-native-paper";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import {
  glassCard,
  glassColors,
  productImage,
  imagePlaceholder,
} from "../styles/glassStyles";
import { useGlassTheme } from "../styles/useGlassTheme";
import type { SmartSearchResult } from "../services/api";
import { useChainLogos } from "../hooks/useChainLogos";

const INDICATOR_STYLE: Record<
  string,
  { color: string; bg: string; label: string }
> = {
  top: { color: "#16A34A", bg: "rgba(22,163,74,0.12)", label: "Top" },
  neutro: {
    color: "#F59E0B",
    bg: "rgba(245,158,11,0.12)",
    label: "Nella media",
  },
  flop: { color: "#DC2626", bg: "rgba(220,38,38,0.12)", label: "Caro" },
};

interface Props {
  result: SmartSearchResult;
  isInWatchlist?: boolean;
  onWatchlistToggle?: (productId: string) => void;
  onAddToShoppingList?: (productId: string) => void;
}

export default function ExpandableCatalogCard({
  result,
  isInWatchlist,
  onWatchlistToggle,
  onAddToShoppingList,
}: Props) {
  const glass = useGlassTheme();
  const chainLogos = useChainLogos();
  const { colors } = glass;
  const {
    product,
    offers,
    price_indicator,
    best_price_per_unit,
    unit_reference,
    has_active_offers,
    last_known_price,
    last_known_chain,
    last_seen_date,
  } = result;

  const [expanded, setExpanded] = useState(false);

  const bestOffer = offers.length > 0
    ? offers.reduce((best, o) =>
        o.offer_price < best.offer_price ? o : best
      , offers[0])
    : null;

  const indConfig = price_indicator ? INDICATOR_STYLE[price_indicator] : null;

  const toggleExpand = useCallback(() => {
    if (Platform.OS !== "web") {
      LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    }
    setExpanded((prev) => !prev);
  }, []);

  // ── Inactive card (no active offers) ──
  if (!has_active_offers) {
    const formattedDate = last_seen_date
      ? new Date(last_seen_date).toLocaleDateString("it-IT", {
          day: "numeric",
          month: "short",
        })
      : null;

    return (
      <TouchableOpacity
        style={[styles.card, glass.card, { opacity: 0.5 }]}
        onPress={() => router.push(`/product/${product.id}`)}
        activeOpacity={0.7}
      >
        <View style={styles.header}>
          {product.image_url ? (
            <Image
              source={{ uri: product.image_url }}
              style={styles.productImage}
              resizeMode="contain"
            />
          ) : (
            <View style={[styles.productImage, styles.productImagePlaceholder]}>
              <MaterialCommunityIcons
                name="food-variant"
                size={20}
                color={colors.textMuted}
              />
            </View>
          )}
          <View style={styles.nameSection}>
            <Text
              variant="titleSmall"
              numberOfLines={1}
              style={[styles.productName, { color: colors.textMuted }]}
            >
              {product.name}
            </Text>
            {product.brand && (
              <Text
                variant="bodySmall"
                style={[styles.brand, { color: colors.textMuted }]}
              >
                {product.brand}
              </Text>
            )}
            {last_known_price != null && (
              <Text
                variant="bodySmall"
                style={[styles.lastKnown, { color: colors.textMuted }]}
              >
                Ultimo prezzo: {"\u20AC"}
                {Number(last_known_price).toFixed(2)}
                {last_known_chain ? ` da ${last_known_chain}` : ""}
                {formattedDate ? ` (${formattedDate})` : ""}
              </Text>
            )}
          </View>
        </View>
      </TouchableOpacity>
    );
  }

  // ── Active card ──
  return (
    <TouchableOpacity
      style={[styles.card, glass.card]}
      onPress={() => router.push(`/product/${product.id}`)}
      activeOpacity={0.85}
    >
      {/* Header row */}
      <View style={styles.header}>
        {product.image_url ? (
          <Image
            source={{ uri: product.image_url }}
            style={styles.productImage}
            resizeMode="contain"
          />
        ) : (
          <View style={[styles.productImage, styles.productImagePlaceholder]}>
            <MaterialCommunityIcons
              name="food-variant"
              size={20}
              color={colors.textMuted}
            />
          </View>
        )}
        <View style={styles.nameSection}>
          <Text
            variant="titleSmall"
            numberOfLines={1}
            style={[styles.productName, { color: colors.textPrimary }]}
          >
            {product.name}
          </Text>
          {product.brand && (
            <Text
              variant="bodySmall"
              style={[styles.brand, { color: colors.textSecondary }]}
            >
              {product.brand}
            </Text>
          )}
        </View>
        {indConfig && (
          <View
            style={[styles.indicatorBadge, { backgroundColor: indConfig.bg }]}
          >
            <Text style={[styles.indicatorText, { color: indConfig.color }]}>
              {indConfig.label}
            </Text>
          </View>
        )}
        {onAddToShoppingList && (
          <IconButton
            icon="cart-plus"
            iconColor={colors.primaryMuted}
            size={20}
            onPress={() => onAddToShoppingList(product.id)}
            style={styles.actionBtn}
          />
        )}
        {onWatchlistToggle && (
          <IconButton
            icon={
              isInWatchlist ? "check-circle" : "plus-circle-outline"
            }
            iconColor={
              isInWatchlist ? colors.primaryMuted : colors.textMuted
            }
            size={22}
            onPress={() => onWatchlistToggle(product.id)}
            style={styles.actionBtn}
          />
        )}
      </View>

      {/* Summary line: best PPU + best chain/price */}
      <View style={styles.summaryRow}>
        {best_price_per_unit != null && (
          <Text
            variant="bodySmall"
            style={[styles.ppuSummary, { color: colors.primary }]}
          >
            Da {"\u20AC"}
            {Number(best_price_per_unit).toFixed(2)}/{unit_reference || "kg"}
          </Text>
        )}
        {bestOffer && (
          <Text
            variant="bodySmall"
            style={[styles.bestChainSummary, { color: colors.textSecondary }]}
          >
            {bestOffer.chain_name} {"\u20AC"}
            {Number(bestOffer.offer_price).toFixed(2)}
          </Text>
        )}
        {offers.length > 1 && (
          <TouchableOpacity
            onPress={toggleExpand}
            style={styles.expandBtn}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <MaterialCommunityIcons
              name={expanded ? "chevron-up" : "chevron-down"}
              size={20}
              color={colors.primary}
            />
          </TouchableOpacity>
        )}
      </View>

      {/* Expanded: all chain prices */}
      {expanded && (
        <View style={styles.expandedSection}>
          <View
            style={[styles.divider, { backgroundColor: colors.divider }]}
          />
          {offers.map((offer, idx) => {
            const isBest =
              offers.length > 1 &&
              bestOffer != null &&
              offer.offer_price === bestOffer.offer_price;
            const validTo = offer.valid_to
              ? new Date(offer.valid_to).toLocaleDateString("it-IT", {
                  day: "numeric",
                  month: "short",
                })
              : null;

            return (
              <View
                key={offer.chain_slug + idx}
                style={[
                  styles.offerRow,
                  isBest && {
                    backgroundColor: colors.successSubtle,
                    borderRadius: 8,
                  },
                ]}
              >
                {chainLogos[offer.chain_name] ? (
                  <Image
                    source={{ uri: chainLogos[offer.chain_name]! }}
                    style={styles.chainLogo}
                  />
                ) : null}
                <Text
                  style={[
                    styles.offerChain,
                    { color: isBest ? colors.success : colors.textSecondary },
                    isBest && styles.offerChainBest,
                  ]}
                  numberOfLines={1}
                >
                  {offer.chain_name}
                </Text>
                <View style={styles.offerPriceSection}>
                  {offer.original_price != null &&
                    offer.original_price !== offer.offer_price && (
                      <Text
                        style={[
                          styles.originalPrice,
                          { color: colors.textMuted },
                        ]}
                      >
                        {"\u20AC"}
                        {Number(offer.original_price).toFixed(2)}
                      </Text>
                    )}
                  <Text
                    style={[
                      styles.offerPrice,
                      {
                        color: isBest
                          ? colors.success
                          : colors.textPrimary,
                      },
                      isBest && styles.offerPriceBest,
                    ]}
                  >
                    {"\u20AC"}
                    {Number(offer.offer_price).toFixed(2)}
                  </Text>
                  {offer.discount_pct != null && (
                    <Text
                      style={[styles.discountBadge, { color: colors.accent }]}
                    >
                      -{Number(offer.discount_pct).toFixed(0)}%
                    </Text>
                  )}
                </View>
                <View style={styles.offerMeta}>
                  {offer.price_per_unit != null && (
                    <Text
                      style={[styles.offerPpu, { color: colors.textMuted }]}
                    >
                      {"\u20AC"}
                      {Number(offer.price_per_unit).toFixed(2)}/
                      {offer.unit_reference || "kg"}
                    </Text>
                  )}
                  {validTo && (
                    <Text
                      style={[styles.offerExpiry, { color: colors.textMuted }]}
                    >
                      scad. {validTo}
                    </Text>
                  )}
                </View>
              </View>
            );
          })}
          <TouchableOpacity
            onPress={toggleExpand}
            style={styles.collapseBtn}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <MaterialCommunityIcons
              name="chevron-up"
              size={18}
              color={colors.primary}
            />
          </TouchableOpacity>
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
    alignItems: "flex-start",
  },
  productImage: {
    ...productImage.compact,
    marginRight: 10,
  },
  productImagePlaceholder: {
    ...imagePlaceholder,
  },
  nameSection: { flex: 1, marginRight: 8 },
  productName: { fontWeight: "700" },
  brand: { marginTop: 1 },
  lastKnown: { marginTop: 4, fontStyle: "italic", fontSize: 12 },
  indicatorBadge: {
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  indicatorText: { fontSize: 11, fontWeight: "bold" },
  actionBtn: { margin: 0, marginLeft: 2 },
  summaryRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 6,
    gap: 8,
  },
  ppuSummary: {
    fontWeight: "600",
    fontSize: 12,
  },
  bestChainSummary: {
    fontSize: 12,
    flex: 1,
  },
  expandBtn: {
    padding: 2,
  },
  expandedSection: {
    marginTop: 4,
  },
  divider: {
    height: 1,
    marginBottom: 8,
  },
  offerRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 6,
    paddingHorizontal: 8,
    marginBottom: 2,
  },
  chainLogo: {
    width: 20,
    height: 20,
    borderRadius: 4,
    marginRight: 4,
  },
  offerChain: {
    width: 90,
    fontSize: 13,
  },
  offerChainBest: {
    fontWeight: "700",
  },
  offerPriceSection: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    minWidth: 100,
  },
  originalPrice: {
    fontSize: 12,
    textDecorationLine: "line-through",
  },
  offerPrice: {
    fontSize: 15,
    fontWeight: "bold",
  },
  offerPriceBest: {
    fontWeight: "800",
  },
  discountBadge: {
    fontSize: 11,
    fontWeight: "bold",
  },
  offerMeta: {
    flex: 1,
    alignItems: "flex-end",
  },
  offerPpu: {
    fontSize: 11,
  },
  offerExpiry: {
    fontSize: 10,
  },
  collapseBtn: {
    alignSelf: "flex-end",
    padding: 4,
    marginTop: 2,
  },
});
