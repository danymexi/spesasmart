import { Image, Platform, ScrollView, Share, StyleSheet, View } from "react-native";
import { Button, IconButton, Text, useTheme, ActivityIndicator } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Stack, useLocalSearchParams, router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { getProduct, getProductHistory, getProductBestPrice, getProductPriceTrends, addToWatchlist, removeFromWatchlist, getWatchlistIds, addToShoppingList } from "../../../services/api";
import { useAppStore } from "../../../stores/useAppStore";
import PriceChart from "../../../components/PriceChart";
import PriceTrendChart from "../../../components/PriceTrendChart";
import PriceIndicator from "../../../components/PriceIndicator";
import ProductComparison from "../../../components/ProductComparison";
import { SkeletonList } from "../../../components/Skeleton";
import {
  glassCard,
  glassColors,
  imagePlaceholder,
} from "../../../styles/glassStyles";

export default function ProductDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const queryClient = useQueryClient();

  const { data: product, isLoading: loadingProduct } = useQuery({
    queryKey: ["product", id],
    queryFn: () => getProduct(id!),
    enabled: !!id,
  });

  const { data: history } = useQuery({
    queryKey: ["productHistory", id],
    queryFn: () => getProductHistory(id!),
    enabled: !!id,
  });

  const { data: bestPrice } = useQuery({
    queryKey: ["bestPrice", id],
    queryFn: () => getProductBestPrice(id!),
    enabled: !!id,
  });

  const { data: priceTrends } = useQuery({
    queryKey: ["priceTrends", id],
    queryFn: () => getProductPriceTrends(id!),
    enabled: !!id,
  });

  // Watchlist state
  const { data: watchlistData } = useQuery({
    queryKey: ["watchlistIds"],
    queryFn: getWatchlistIds,
    enabled: isLoggedIn,
  });
  const isInWatchlist = watchlistData?.product_ids?.includes(id!) ?? false;

  const addMutation = useMutation({
    mutationFn: () => addToWatchlist(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      queryClient.invalidateQueries({ queryKey: ["watchlistIds"] });
      queryClient.invalidateQueries({ queryKey: ["userDeals"] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: () => removeFromWatchlist(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      queryClient.invalidateQueries({ queryKey: ["watchlistIds"] });
      queryClient.invalidateQueries({ queryKey: ["userDeals"] });
    },
  });

  const addToListMutation = useMutation({
    mutationFn: () => addToShoppingList({ product_id: id! }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
    },
  });

  const handleShare = async () => {
    const priceText = bestPrice ? ` a ${Number(bestPrice.best_price).toFixed(2)}\u20AC` : "";
    const chainText = bestPrice ? ` da ${bestPrice.chain_name}` : "";
    const text = `${product?.name}${priceText}${chainText} - SpesaSmart`;
    const url = `https://spesasmart.spazioitech.it/product/${id}`;

    if (Platform.OS === "web" && navigator.share) {
      try {
        await navigator.share({ title: product?.name || "SpesaSmart", text, url });
      } catch { /* user cancelled */ }
    } else if (Platform.OS !== "web") {
      Share.share({ message: `${text}\n${url}` });
    }
  };

  if (loadingProduct) {
    return <SkeletonList count={4} />;
  }

  if (!product) {
    return (
      <View style={styles.centered}>
        <Text>Prodotto non trovato</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.contentContainer}>
      <Stack.Screen
        options={{
          title: product?.name ?? "Dettaglio Prodotto",
          headerLeft: Platform.OS === "web"
            ? () => (
                <IconButton
                  icon="arrow-left"
                  onPress={() =>
                    router.canGoBack() ? router.back() : router.replace("/(tabs)/search")
                  }
                />
              )
            : undefined,
        }}
      />
      {/* Hero card: image + info + watchlist button */}
      <View style={styles.heroCard}>
        {product.image_url ? (
          <View style={styles.heroImageWrap}>
            <Image
              source={{ uri: product.image_url }}
              style={styles.heroImage}
              resizeMode="contain"
            />
          </View>
        ) : (
          <View style={[styles.heroImageWrap, styles.heroPlaceholder]}>
            <MaterialCommunityIcons name="food-variant" size={64} color="#ccc" />
          </View>
        )}

        <View style={styles.heroInfoSection}>
          <View style={styles.nameRow}>
            <Text variant="headlineSmall" style={styles.productName}>
              {product.name}
            </Text>
            <PriceIndicator indicator={bestPrice?.price_indicator} />
          </View>
          {product.brand && (
            <Text variant="titleMedium" style={styles.brandText}>
              {product.brand}
            </Text>
          )}
          <View style={styles.metaRow}>
            {product.category && (
              <Text variant="bodySmall" style={styles.metaText}>
                {product.category}
              </Text>
            )}
            {product.unit && (
              <Text variant="bodySmall" style={styles.metaText}>
                Unita: {product.unit}
              </Text>
            )}
          </View>

        </View>
      </View>

      {/* Best price card */}
      {bestPrice && (
        <View style={styles.sectionCard}>
          <Text variant="titleMedium" style={styles.sectionHeader}>
            Miglior Prezzo Attuale
          </Text>
          <View style={styles.bestPriceRow}>
            <View>
              <Text
                variant="displaySmall"
                style={{ color: theme.colors.primary, fontWeight: "bold" }}
              >
                {"\u20AC"}{Number(bestPrice.best_price).toFixed(2)}
              </Text>
              <Text variant="titleMedium">{bestPrice.chain_name}</Text>
              {bestPrice.price_per_unit != null && (
                <Text variant="bodyMedium" style={styles.pricePerUnit}>
                  {Number(bestPrice.price_per_unit).toFixed(2)} {bestPrice.unit_reference === "l" ? "EUR/L" : bestPrice.unit_reference === "pz" ? "EUR/pz" : "EUR/kg"}
                </Text>
              )}
              {bestPrice.original_price && (
                <Text variant="bodyMedium" style={styles.originalPrice}>
                  Prezzo pieno: {"\u20AC"}{Number(bestPrice.original_price).toFixed(2)}
                </Text>
              )}
              {bestPrice.discount_pct && (
                <Text variant="bodyMedium" style={styles.discount}>
                  Sconto: {Number(bestPrice.discount_pct).toFixed(0)}%
                </Text>
              )}
              {bestPrice.valid_until && (
                <Text variant="bodySmall" style={styles.validUntil}>
                  Valido fino al{" "}
                  {new Date(bestPrice.valid_until).toLocaleDateString("it-IT")}
                </Text>
              )}
            </View>
          </View>
        </View>
      )}

      {/* Action buttons */}
      <View style={styles.buttonRow}>
        {isLoggedIn && (
          <Button
            mode={isInWatchlist ? "outlined" : "contained"}
            icon={isInWatchlist ? "check-circle" : "star-plus-outline"}
            onPress={() =>
              isInWatchlist ? removeMutation.mutate() : addMutation.mutate()
            }
            loading={addMutation.isPending || removeMutation.isPending}
            style={styles.actionBtn}
            compact
          >
            {isInWatchlist ? "Monitorato" : "Monitora"}
          </Button>
        )}
        {isLoggedIn && (
          <Button
            mode="contained"
            icon="cart-plus"
            onPress={() => addToListMutation.mutate()}
            loading={addToListMutation.isPending}
            style={styles.actionBtn}
            compact
          >
            Spesa
          </Button>
        )}
        <Button
          mode="outlined"
          icon="share-variant"
          onPress={handleShare}
          style={styles.actionBtn}
          compact
        >
          Condividi
        </Button>
      </View>

      {/* Detailed compare */}
      <Button
        mode="outlined"
        icon="scale-balance"
        onPress={() => router.push(`/product/${id}/compare`)}
        style={styles.compareBtn}
      >
        Confronta Prezzi tra Catene
      </Button>

      {/* Price comparison (inline) */}
      <View style={styles.sectionCard}>
        <Text variant="titleMedium" style={styles.sectionHeader}>
          Confronto Prezzi
        </Text>
        <ProductComparison productId={id!} />
      </View>

      {/* Price history */}
      <View style={styles.sectionCard}>
        <Text variant="titleMedium" style={styles.sectionHeader}>
          Storico Prezzi
        </Text>
        {history && history.history.length > 0 ? (
          <PriceChart data={history.history} />
        ) : (
          <Text variant="bodyMedium" style={styles.noDataText}>
            Storico non disponibile
          </Text>
        )}
      </View>

      {/* Price trends */}
      {priceTrends && priceTrends.trends.length >= 2 && (
        <View style={styles.sectionCard}>
          <Text variant="titleMedium" style={styles.sectionHeader}>
            Andamento Prezzo al {priceTrends.unit_reference === "l" ? "litro" : "kg"}
          </Text>
          <PriceTrendChart
            trends={priceTrends.trends}
            unitReference={priceTrends.unit_reference}
          />
        </View>
      )}

    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  contentContainer: { paddingBottom: 150 },
  loader: { marginTop: 60 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center" },
  heroCard: {
    marginHorizontal: 12,
    marginTop: 12,
    padding: 0,
    ...glassCard,
  } as any,
  heroImageWrap: {
    padding: 16,
    alignItems: "center",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    overflow: "hidden",
  },
  heroImage: {
    width: "100%",
    height: 200,
    borderRadius: 16,
  } as any,
  heroPlaceholder: {
    height: 200,
    justifyContent: "center",
    ...imagePlaceholder,
  },
  heroInfoSection: {
    padding: 16,
  },
  nameRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  productName: { fontWeight: "bold", flex: 1, marginRight: 8 },
  brandText: {
    color: glassColors.greenMedium,
    fontWeight: "600",
    marginTop: 2,
  },
  metaRow: { flexDirection: "row", gap: 16, marginTop: 8 },
  metaText: { color: "#555" },
  buttonRow: {
    flexDirection: "row",
    marginHorizontal: 12,
    marginTop: 12,
    gap: 8,
  },
  actionBtn: { flex: 1 },
  compareBtn: {
    marginHorizontal: 12,
    marginTop: 8,
  },
  sectionCard: {
    marginHorizontal: 12,
    marginTop: 12,
    padding: 16,
    ...glassCard,
  } as any,
  sectionHeader: { marginBottom: 8, fontWeight: "700", color: "#333" },
  bestPriceRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  originalPrice: {
    textDecorationLine: "line-through",
    color: "#999",
    marginTop: 4,
  },
  pricePerUnit: { color: "#555", marginTop: 4, fontStyle: "italic" },
  discount: { color: "#E65100", fontWeight: "bold", marginTop: 2 },
  validUntil: { color: "#666", marginTop: 4 },
  noDataText: { color: "#666" },
});
