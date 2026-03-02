import { useMemo } from "react";
import { Image, StyleSheet, TouchableOpacity, View } from "react-native";
import { Button, Text } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { getUserDeals, type UserDeal } from "../services/api";
import { glassCard, glassColors, glassPanel, productImage, imagePlaceholder } from "../styles/glassStyles";

interface GroupedDeal {
  product_id: string;
  product_name: string;
  brand: string | null;
  image_url: string | null;
  offers: {
    chain_name: string;
    offer_price: number;
    original_price: number | null;
    discount_pct: number | null;
    valid_to: string | null;
  }[];
}

function groupDealsByProduct(deals: UserDeal[]): GroupedDeal[] {
  const map = new Map<string, GroupedDeal>();
  for (const deal of deals) {
    const existing = map.get(deal.product_id);
    if (existing) {
      existing.offers.push({
        chain_name: deal.chain_name,
        offer_price: deal.offer_price,
        original_price: deal.original_price,
        discount_pct: deal.discount_pct,
        valid_to: deal.valid_to,
      });
      if (!existing.image_url && deal.image_url) {
        existing.image_url = deal.image_url;
      }
    } else {
      map.set(deal.product_id, {
        product_id: deal.product_id,
        product_name: deal.product_name,
        brand: deal.brand,
        image_url: deal.image_url,
        offers: [{
          chain_name: deal.chain_name,
          offer_price: deal.offer_price,
          original_price: deal.original_price,
          discount_pct: deal.discount_pct,
          valid_to: deal.valid_to,
        }],
      });
    }
  }
  return Array.from(map.values());
}

export default function PersonalDeals() {
  const { data: deals, isLoading } = useQuery({
    queryKey: ["userDeals"],
    queryFn: getUserDeals,
  });

  const grouped = useMemo(() => {
    if (!deals) return [];
    return groupDealsByProduct(deals);
  }, [deals]);

  if (isLoading) {
    return null;
  }

  const hasDeals = grouped.length > 0;

  return (
    <View style={styles.section}>
      <Text variant="titleLarge" style={styles.sectionTitle}>
        Le Tue Offerte {hasDeals ? `(${grouped.length})` : ""}
      </Text>

      {hasDeals ? (
        <>
          {grouped.map((group) => (
            <DealCard key={group.product_id} group={group} />
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

function DealCard({ group }: { group: GroupedDeal }) {
  const bestPrice = Math.min(...group.offers.map((o) => o.offer_price));

  return (
    <TouchableOpacity
      style={styles.card}
      onPress={() => router.push(`/product/${group.product_id}`)}
      activeOpacity={0.7}
    >
      <View style={styles.cardInner}>
        {group.image_url ? (
          <Image
            source={{ uri: group.image_url }}
            style={styles.dealImage}
            resizeMode="contain"
          />
        ) : (
          <View style={[styles.dealImage, styles.dealImagePlaceholder]}>
            <MaterialCommunityIcons name="food-variant" size={20} color="#ccc" />
          </View>
        )}

        <View style={styles.dealInfo}>
          <Text variant="titleSmall" numberOfLines={1} style={styles.productName}>
            {group.product_name}
          </Text>
          {group.brand && (
            <Text variant="bodySmall" style={styles.brand}>
              {group.brand}
            </Text>
          )}
        </View>
      </View>

      {/* Chain prices side by side */}
      <View style={styles.chainPricesRow}>
        {group.offers.map((offer) => {
          const isBest = group.offers.length > 1 && offer.offer_price === bestPrice;
          return (
            <View
              key={offer.chain_name}
              style={[
                styles.chainPriceCell,
                isBest && styles.chainPriceCellBest,
              ]}
            >
              <Text
                variant="labelSmall"
                style={[styles.chainLabel, isBest && styles.chainLabelBest]}
                numberOfLines={1}
              >
                {offer.chain_name}
              </Text>
              <Text
                variant="titleMedium"
                style={[styles.offerPrice, isBest && styles.offerPriceBest]}
              >
                {"\u20AC"}{Number(offer.offer_price).toFixed(2)}
              </Text>
              {offer.original_price && (
                <Text variant="bodySmall" style={styles.originalPrice}>
                  {"\u20AC"}{Number(offer.original_price).toFixed(2)}
                </Text>
              )}
              {offer.discount_pct && (
                <View style={[styles.discountBadge, isBest && styles.discountBadgeBest]}>
                  <Text style={[styles.discountText, isBest && styles.discountTextBest]}>
                    -{Number(offer.discount_pct).toFixed(0)}%
                  </Text>
                </View>
              )}
            </View>
          );
        })}
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
    fontWeight: "700",
    color: glassColors.greenDark,
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
  productName: { color: "#1a1a1a", fontWeight: "600" },
  brand: { color: "#444", marginTop: 1 },
  chainPricesRow: {
    flexDirection: "row",
    marginTop: 8,
    gap: 8,
  },
  chainPriceCell: {
    flex: 1,
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.03)",
    borderRadius: 12,
    paddingVertical: 8,
    paddingHorizontal: 6,
  },
  chainPriceCellBest: {
    backgroundColor: "rgba(27,94,32,0.08)",
  },
  chainLabel: {
    color: "#555",
    fontSize: 11,
    marginBottom: 2,
  },
  chainLabelBest: {
    color: glassColors.greenDark,
    fontWeight: "600",
  },
  offerPrice: { color: glassColors.greenDark, fontWeight: "bold" },
  offerPriceBest: { color: glassColors.greenDark },
  originalPrice: { color: "#999", textDecorationLine: "line-through", fontSize: 11, marginTop: 1 },
  discountBadge: {
    backgroundColor: "rgba(255,111,0,0.12)",
    borderRadius: 8,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginTop: 3,
  },
  discountBadgeBest: {
    backgroundColor: "rgba(27,94,32,0.12)",
  },
  discountText: { color: "#E65100", fontSize: 11, fontWeight: "bold" },
  discountTextBest: { color: glassColors.greenDark },
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
