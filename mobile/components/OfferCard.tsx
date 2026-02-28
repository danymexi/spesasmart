import { Image, StyleSheet, View } from "react-native";
import { Text, useTheme } from "react-native-paper";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { Pressable } from "react-native";
import {
  glassCard,
  glassColors,
  chainBadgeGlass,
  discountBadgeGlass,
  productImage,
  imagePlaceholder,
} from "../styles/glassStyles";

interface Offer {
  id: string;
  product_id: string;
  product_name: string;
  brand?: string | null;
  category?: string | null;
  chain_name: string;
  original_price?: number | null;
  offer_price: number;
  discount_pct?: number | null;
  discount_type?: string | null;
  quantity?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  image_url?: string | null;
  previous_price?: number | null;
  previous_date?: string | null;
  previous_chain?: string | null;
}

interface Props {
  offer: Offer;
  compact?: boolean;
}

const MONTH_ABBR = [
  "gen", "feb", "mar", "apr", "mag", "giu",
  "lug", "ago", "set", "ott", "nov", "dic",
];

function formatShortDate(iso: string): string {
  const d = new Date(iso);
  const month = MONTH_ABBR[d.getMonth()];
  const year = String(d.getFullYear()).slice(2);
  return `${month} '${year}`;
}

export default function OfferCard({ offer, compact }: Props) {
  const theme = useTheme();
  const imgSize = compact ? productImage.compact : productImage.card;

  // Previous price trend
  const prevPrice = offer.previous_price != null ? Number(offer.previous_price) : null;
  const curPrice = Number(offer.offer_price);
  let trendIcon: "arrow-down" | "arrow-up" | "minus" = "minus";
  let trendColor = "#888";
  if (prevPrice != null) {
    if (curPrice < prevPrice) {
      trendIcon = "arrow-down";
      trendColor = "#2E7D32"; // green
    } else if (curPrice > prevPrice) {
      trendIcon = "arrow-up";
      trendColor = "#C62828"; // red
    }
  }

  return (
    <Pressable
      style={compact ? styles.compactCard : styles.card}
      onPress={() => router.push(`/product/${offer.product_id}`)}
    >
      <View style={styles.content}>
        {/* Product image */}
        {offer.image_url ? (
          <Image
            source={{ uri: offer.image_url }}
            style={[styles.image, imgSize]}
            resizeMode="contain"
          />
        ) : (
          <View style={[styles.image, imgSize, styles.placeholder]}>
            <MaterialCommunityIcons
              name="food-variant"
              size={compact ? 24 : 32}
              color="#ccc"
            />
          </View>
        )}

        <View style={styles.textSection}>
          {/* Chain badge */}
          <View style={styles.chainBadge}>
            <Text variant="labelSmall" style={styles.chainText}>
              {offer.chain_name}
            </Text>
          </View>

          {/* Product name */}
          <Text variant="titleSmall" numberOfLines={compact ? 1 : 2} style={styles.productName}>
            {offer.product_name}
          </Text>

          {offer.brand && (
            <Text variant="bodySmall" style={styles.brand}>
              {offer.brand}
            </Text>
          )}

          {/* Price row */}
          <View style={styles.priceRow}>
            <Text variant="titleLarge" style={{ color: theme.colors.primary, fontWeight: "bold" }}>
              {"\u20AC"}{Number(offer.offer_price).toFixed(2)}
            </Text>
            {offer.original_price && (
              <Text variant="bodyMedium" style={styles.originalPrice}>
                {"\u20AC"}{Number(offer.original_price).toFixed(2)}
              </Text>
            )}
            {offer.discount_pct && (
              <View style={styles.discountBadge}>
                <Text style={styles.discountText}>
                  -{Number(offer.discount_pct).toFixed(0)}%
                </Text>
              </View>
            )}
          </View>

          {/* Previous price trend */}
          {prevPrice != null && offer.previous_date && (
            <View style={styles.previousPriceRow}>
              <MaterialCommunityIcons name={trendIcon} size={14} color={trendColor} />
              <Text variant="labelSmall" style={[styles.previousPrice, { color: trendColor }]}>
                Prima: {"\u20AC"}{prevPrice.toFixed(2)} ({formatShortDate(offer.previous_date)})
              </Text>
            </View>
          )}

          {/* Quantity & dates */}
          {!compact && (
            <View style={styles.footer}>
              {offer.quantity && (
                <Text variant="labelSmall" style={styles.quantity}>
                  {offer.quantity}
                </Text>
              )}
              {offer.valid_to && (
                <Text variant="labelSmall" style={styles.validTo}>
                  Fino al {new Date(offer.valid_to).toLocaleDateString("it-IT")}
                </Text>
              )}
            </View>
          )}
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 12,
    marginBottom: 8,
    padding: 12,
    ...glassCard,
  } as any,
  compactCard: {
    marginBottom: 0,
    padding: 10,
    ...glassCard,
  } as any,
  content: {
    flexDirection: "row",
    alignItems: "flex-start",
  },
  image: {
    marginRight: 12,
  },
  placeholder: {
    ...imagePlaceholder,
  },
  textSection: {
    flex: 1,
  },
  chainBadge: {
    alignSelf: "flex-start",
    marginBottom: 6,
    ...chainBadgeGlass,
  },
  chainText: { color: glassColors.greenDark, fontWeight: "bold", fontSize: 11 },
  productName: { fontWeight: "500", marginBottom: 2 },
  brand: { color: "#666", marginBottom: 4 },
  priceRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 4 },
  previousPriceRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  previousPrice: { fontSize: 11 },
  originalPrice: { textDecorationLine: "line-through", color: "#999" },
  discountBadge: {
    ...discountBadgeGlass,
  },
  discountText: { color: "#E65100", fontWeight: "bold", fontSize: 12 },
  footer: { flexDirection: "row", justifyContent: "space-between", marginTop: 6 },
  quantity: { color: "#888" },
  validTo: { color: "#888" },
});
