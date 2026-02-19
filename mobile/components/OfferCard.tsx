import { StyleSheet, View } from "react-native";
import { Card, Text, useTheme } from "react-native-paper";
import { router } from "expo-router";

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
}

interface Props {
  offer: Offer;
  compact?: boolean;
}

export default function OfferCard({ offer, compact }: Props) {
  const theme = useTheme();

  return (
    <Card
      style={compact ? styles.compactCard : styles.card}
      onPress={() => router.push(`/product/${offer.product_id}`)}
    >
      <Card.Content style={compact ? styles.compactContent : undefined}>
        {/* Chain badge */}
        <View style={[styles.chainBadge, { backgroundColor: theme.colors.primary }]}>
          <Text variant="labelSmall" style={styles.chainText}>
            {offer.chain_name}
          </Text>
        </View>

        {/* Product name */}
        <Text variant="titleSmall" numberOfLines={compact ? 1 : 2} style={styles.productName}>
          {offer.product_name}
        </Text>

        {offer.brand && !compact && (
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
      </Card.Content>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { marginHorizontal: 12, marginBottom: 8 },
  compactCard: { marginBottom: 0 },
  compactContent: { paddingVertical: 8 },
  chainBadge: {
    alignSelf: "flex-start",
    borderRadius: 4,
    paddingHorizontal: 8,
    paddingVertical: 2,
    marginBottom: 6,
  },
  chainText: { color: "#fff", fontWeight: "bold", fontSize: 11 },
  productName: { fontWeight: "500", marginBottom: 2 },
  brand: { color: "#666", marginBottom: 4 },
  priceRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 4 },
  originalPrice: { textDecorationLine: "line-through", color: "#999" },
  discountBadge: {
    backgroundColor: "#FFF3E0",
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  discountText: { color: "#E65100", fontWeight: "bold", fontSize: 12 },
  footer: { flexDirection: "row", justifyContent: "space-between", marginTop: 6 },
  quantity: { color: "#888" },
  validTo: { color: "#888" },
});
