import { ScrollView, StyleSheet, View } from "react-native";
import { ActivityIndicator, Button, Text, useTheme } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { getProductCompare, addToShoppingList, CompareOffer } from "../../../services/api";
import { useAppStore } from "../../../stores/useAppStore";
import { glassCard, glassColors } from "../../../styles/glassStyles";

const CHAIN_COLORS: Record<string, string> = {
  esselunga: "#E30613",
  lidl: "#0050AA",
  coop: "#E07000",
  iperal: "#009639",
};

export default function CompareScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["compare", id],
    queryFn: () => getProductCompare(id!),
    enabled: !!id,
  });

  const addToListMutation = useMutation({
    mutationFn: (params: { product_id: string; offer_id: string }) =>
      addToShoppingList(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
    },
  });

  if (isLoading) {
    return <ActivityIndicator style={styles.loader} />;
  }

  if (!data || data.offers.length === 0) {
    return (
      <View style={styles.centered}>
        <MaterialCommunityIcons name="scale-balance" size={48} color="#ccc" />
        <Text variant="titleMedium" style={styles.emptyTitle}>
          Nessun confronto disponibile
        </Text>
        <Text variant="bodyMedium" style={styles.emptyText}>
          Non ci sono offerte attive su piu' catene per questo prodotto.
        </Text>
        <Button mode="outlined" onPress={() => router.back()}>
          Torna al prodotto
        </Button>
      </View>
    );
  }

  // Sort by price ascending, cheapest first
  const sorted = [...data.offers].sort((a, b) => a.offer_price - b.offer_price);
  const cheapestPrice = sorted[0]?.offer_price;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text variant="headlineSmall" style={styles.title}>
        {data.product.name}
      </Text>
      {data.product.brand && (
        <Text variant="bodyMedium" style={styles.brand}>
          {data.product.brand}
        </Text>
      )}

      <Text variant="titleMedium" style={styles.subtitle}>
        Confronto prezzi tra catene
      </Text>

      {sorted.map((offer, idx) => {
        const isCheapest = offer.offer_price === cheapestPrice;
        const chainColor = CHAIN_COLORS[offer.chain_slug] || "#666";

        return (
          <View
            key={offer.chain_slug}
            style={[
              styles.offerCard,
              isCheapest && styles.cheapestCard,
            ]}
          >
            <View style={styles.offerHeader}>
              <View style={[styles.chainDot, { backgroundColor: chainColor }]} />
              <Text variant="titleMedium" style={styles.chainName}>
                {offer.chain_name}
              </Text>
              {isCheapest && (
                <View style={styles.bestBadge}>
                  <Text style={styles.bestBadgeText}>MIGLIOR PREZZO</Text>
                </View>
              )}
            </View>

            <View style={styles.priceRow}>
              <View>
                <Text
                  variant="headlineMedium"
                  style={[
                    styles.price,
                    { color: isCheapest ? glassColors.greenMedium : theme.colors.onSurface },
                  ]}
                >
                  {"\u20AC"}{Number(offer.offer_price).toFixed(2)}
                </Text>
                {offer.price_per_unit != null && (
                  <Text variant="bodySmall" style={styles.ppu}>
                    {Number(offer.price_per_unit).toFixed(2)}{" "}
                    {offer.unit_reference === "l" ? "EUR/L" : offer.unit_reference === "pz" ? "EUR/pz" : "EUR/kg"}
                  </Text>
                )}
              </View>
              <View style={styles.offerDetails}>
                {offer.original_price && (
                  <Text variant="bodySmall" style={styles.original}>
                    Era: {"\u20AC"}{Number(offer.original_price).toFixed(2)}
                  </Text>
                )}
                {offer.discount_pct && (
                  <Text variant="bodySmall" style={styles.discount}>
                    -{Number(offer.discount_pct).toFixed(0)}%
                  </Text>
                )}
                {offer.valid_to && (
                  <Text variant="labelSmall" style={styles.validity}>
                    Fino al {new Date(offer.valid_to).toLocaleDateString("it-IT")}
                  </Text>
                )}
              </View>
            </View>

            {isLoggedIn && (
              <Button
                mode={isCheapest ? "contained" : "outlined"}
                icon="cart-plus"
                compact
                onPress={() =>
                  addToListMutation.mutate({
                    product_id: id!,
                    offer_id: offer.offer_id,
                  })
                }
                style={styles.addBtn}
              >
                Aggiungi alla spesa
              </Button>
            )}
          </View>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  content: { paddingBottom: 120 },
  loader: { marginTop: 60 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center", padding: 20 },
  emptyTitle: { marginTop: 12, marginBottom: 8 },
  emptyText: { color: "#888", textAlign: "center", marginBottom: 16 },
  title: { fontWeight: "bold", marginHorizontal: 16, marginTop: 16 },
  brand: { color: glassColors.greenMedium, marginHorizontal: 16, marginTop: 4 },
  subtitle: { marginHorizontal: 16, marginTop: 16, marginBottom: 8, color: "#666" },
  offerCard: {
    marginHorizontal: 12,
    marginBottom: 10,
    padding: 16,
    ...glassCard,
  } as any,
  cheapestCard: {
    borderWidth: 2,
    borderColor: glassColors.greenMedium,
  },
  offerHeader: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 8,
  },
  chainDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    marginRight: 8,
  },
  chainName: { fontWeight: "bold", flex: 1 },
  bestBadge: {
    backgroundColor: "rgba(73, 177, 112, 0.15)",
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  bestBadgeText: {
    color: glassColors.greenMedium,
    fontSize: 10,
    fontWeight: "bold",
  },
  priceRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  price: { fontWeight: "bold" },
  ppu: { color: "#666", fontStyle: "italic", marginTop: 2 },
  offerDetails: { alignItems: "flex-end" },
  original: { textDecorationLine: "line-through", color: "#999" },
  discount: { color: "#E65100", fontWeight: "bold" },
  validity: { color: "#888", marginTop: 4 },
  addBtn: { marginTop: 12 },
});
