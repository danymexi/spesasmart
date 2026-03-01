import { Image, ScrollView, StyleSheet, View } from "react-native";
import { Button, Text, useTheme, ActivityIndicator } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { getProduct, getProductHistory, getProductBestPrice, getProductPriceTrends, addToWatchlist } from "../../services/api";
import { useAppStore } from "../../stores/useAppStore";
import PriceChart from "../../components/PriceChart";
import PriceTrendChart from "../../components/PriceTrendChart";
import PriceIndicator from "../../components/PriceIndicator";
import ProductComparison from "../../components/ProductComparison";
import {
  glassCard,
  glassColors,
  imagePlaceholder,
} from "../../styles/glassStyles";

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

  const addMutation = useMutation({
    mutationFn: () => addToWatchlist(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  if (loadingProduct) {
    return <ActivityIndicator style={styles.loader} />;
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
            <PriceIndicator productId={id!} />
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

      {/* Add to watchlist */}
      {isLoggedIn && (
        <Button
          mode="contained"
          icon="star-plus-outline"
          onPress={() => addMutation.mutate()}
          loading={addMutation.isPending}
          style={styles.watchlistBtn}
        >
          Aggiungi alla Lista
        </Button>
      )}

      {/* Price comparison */}
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
  metaText: { color: "#888" },
  watchlistBtn: {
    marginHorizontal: 12,
    marginTop: 12,
  },
  sectionCard: {
    marginHorizontal: 12,
    marginTop: 12,
    padding: 16,
    ...glassCard,
  } as any,
  sectionHeader: { marginBottom: 8, fontWeight: "600", color: "#555" },
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
  pricePerUnit: { color: "#666", marginTop: 4, fontStyle: "italic" },
  discount: { color: "#E65100", fontWeight: "bold", marginTop: 2 },
  validUntil: { color: "#888", marginTop: 4 },
  noDataText: { color: "#888" },
});
