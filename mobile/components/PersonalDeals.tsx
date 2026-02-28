import { Image, StyleSheet, TouchableOpacity, View } from "react-native";
import { Button, Text } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { getUserDeals, type UserDeal } from "../services/api";
import { glassCard, glassColors, glassPanel, productImage, imagePlaceholder } from "../styles/glassStyles";

export default function PersonalDeals() {
  const { data: deals, isLoading } = useQuery({
    queryKey: ["userDeals"],
    queryFn: getUserDeals,
  });

  if (isLoading) {
    return null;
  }

  const hasDeals = deals && deals.length > 0;

  return (
    <View style={styles.section}>
      <Text variant="titleLarge" style={styles.sectionTitle}>
        Le Tue Offerte {hasDeals ? `(${deals.length})` : ""}
      </Text>

      {hasDeals ? (
        <>
          {deals.map((deal, index) => (
            <DealCard key={`${deal.product_id}-${deal.chain_name}-${index}`} deal={deal} />
          ))}
          <View style={styles.ctaContainer}>
            <Text variant="bodySmall" style={styles.ctaText}>
              Vuoi monitorare altri prodotti?
            </Text>
            <Button
              mode="text"
              compact
              onPress={() => router.push("/(tabs)/search")}
              textColor={glassColors.greenDark}
            >
              Sfoglia il catalogo
            </Button>
          </View>
        </>
      ) : (
        <View style={styles.emptyCard}>
          <Text variant="bodyMedium" style={styles.emptyText}>
            Nessuna offerta per i tuoi prodotti questa settimana
          </Text>
          <Button
            mode="contained"
            compact
            onPress={() => router.push("/(tabs)/search")}
            style={styles.emptyButton}
          >
            Sfoglia il Catalogo
          </Button>
        </View>
      )}
    </View>
  );
}

function DealCard({ deal }: { deal: UserDeal }) {
  return (
    <TouchableOpacity
      style={styles.card}
      onPress={() => router.push(`/product/${deal.product_id}`)}
      activeOpacity={0.7}
    >
      <View style={styles.cardInner}>
        {deal.image_url ? (
          <Image
            source={{ uri: deal.image_url }}
            style={styles.dealImage}
            resizeMode="contain"
          />
        ) : (
          <View style={[styles.dealImage, styles.dealImagePlaceholder]}>
            <MaterialCommunityIcons name="food-variant" size={20} color="#ccc" />
          </View>
        )}

        <View style={styles.dealInfo}>
          <Text variant="titleSmall" numberOfLines={1}>
            {deal.product_name}
          </Text>
          {deal.brand && (
            <Text variant="bodySmall" style={styles.brand}>
              {deal.brand}
            </Text>
          )}
          <Text variant="bodySmall" style={styles.chain}>
            {deal.chain_name}
          </Text>
        </View>

        <View style={styles.priceSection}>
          <Text variant="titleMedium" style={styles.offerPrice}>
            {"\u20AC"}{Number(deal.offer_price).toFixed(2)}
          </Text>
          {deal.original_price && (
            <Text variant="bodySmall" style={styles.originalPrice}>
              {"\u20AC"}{Number(deal.original_price).toFixed(2)}
            </Text>
          )}
          {deal.discount_pct && (
            <View style={styles.discountBadge}>
              <Text style={styles.discountText}>
                -{Number(deal.discount_pct).toFixed(0)}%
              </Text>
            </View>
          )}
        </View>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  section: { marginBottom: 8 },
  sectionTitle: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
    fontWeight: "600",
  },
  card: {
    marginHorizontal: 12,
    marginBottom: 8,
    padding: 12,
    ...glassCard,
  } as any,
  cardInner: {
    flexDirection: "row",
    alignItems: "center",
  },
  dealImage: {
    ...productImage.compact,
    marginRight: 10,
  },
  dealImagePlaceholder: {
    ...imagePlaceholder,
  },
  dealInfo: { flex: 1, marginRight: 8 },
  brand: { color: "#666", marginTop: 1 },
  chain: { color: glassColors.greenSubtle, marginTop: 1 },
  priceSection: { alignItems: "flex-end" },
  offerPrice: { color: glassColors.greenDark, fontWeight: "bold" },
  originalPrice: { color: "#999", textDecorationLine: "line-through" },
  discountBadge: {
    backgroundColor: "rgba(255,111,0,0.12)",
    borderRadius: 8,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginTop: 2,
  },
  discountText: { color: "#E65100", fontSize: 11, fontWeight: "bold" },
  ctaContainer: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 4,
  },
  ctaText: { color: "#888" },
  emptyCard: {
    marginHorizontal: 12,
    padding: 20,
    alignItems: "center",
    ...glassCard,
  } as any,
  emptyText: { color: "#888", textAlign: "center", marginBottom: 12 },
  emptyButton: {},
});
