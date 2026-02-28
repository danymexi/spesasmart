import { Image, ScrollView, StyleSheet, View } from "react-native";
import { Button, Text, useTheme, ActivityIndicator } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";
import { getProduct, getProductHistory, getProductBestPrice, addToWatchlist } from "../../services/api";
import { useAppStore } from "../../stores/useAppStore";
import PriceChart from "../../components/PriceChart";
import PriceIndicator from "../../components/PriceIndicator";
import ProductComparison from "../../components/ProductComparison";
import {
  glassCard,
  glassColors,
  imagePlaceholder,
  productImage,
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
    <SafeAreaView style={styles.wrapper} edges={["bottom"]}>
    <ScrollView style={styles.container}>
      {/* Product hero image */}
      {product.image_url ? (
        <View style={styles.heroContainer}>
          <Image
            source={{ uri: product.image_url }}
            style={styles.heroImage}
            resizeMode="contain"
          />
        </View>
      ) : (
        <View style={[styles.heroContainer, styles.heroPlaceholder]}>
          <MaterialCommunityIcons name="food-variant" size={64} color="#ccc" />
        </View>
      )}

      {/* Product header */}
      <View style={styles.headerCard}>
        <Text variant="headlineSmall" style={styles.productName}>
          {product.name}
        </Text>
        {product.brand && (
          <Text variant="titleMedium" style={styles.brand}>
            {product.brand}
          </Text>
        )}
        <View style={styles.metaRow}>
          {product.category && (
            <Text variant="bodySmall" style={styles.category}>
              {product.category}
            </Text>
          )}
          {product.unit && (
            <Text variant="bodySmall" style={styles.unit}>
              Unita: {product.unit}
            </Text>
          )}
        </View>
      </View>

      {/* Best price card */}
      {bestPrice && (
        <View style={styles.priceCard}>
          <Text variant="titleMedium" style={styles.sectionLabel}>
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
            <PriceIndicator productId={id!} />
          </View>
        </View>
      )}

      {/* Price comparison across chains */}
      <Text variant="titleMedium" style={styles.sectionTitle}>
        Confronto Prezzi
      </Text>
      <ProductComparison productId={id!} />

      {/* Price history chart */}
      <Text variant="titleMedium" style={styles.sectionTitle}>
        Storico Prezzi
      </Text>
      {history && history.history.length > 0 ? (
        <PriceChart data={history.history} />
      ) : (
        <Text variant="bodyMedium" style={styles.noDataText}>
          Storico non disponibile
        </Text>
      )}

      <View style={{ height: isLoggedIn ? 80 : 16 }} />
    </ScrollView>

    {/* Sticky bottom button */}
    {isLoggedIn && (
      <View style={styles.bottomBar}>
        <Button
          mode="contained"
          icon="star-plus-outline"
          onPress={() => addMutation.mutate()}
          loading={addMutation.isPending}
          style={styles.watchlistButton}
        >
          Aggiungi alla Lista
        </Button>
      </View>
    )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  wrapper: { flex: 1 },
  container: { flex: 1, backgroundColor: "transparent" },
  loader: { marginTop: 60 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center" },
  heroContainer: {
    marginHorizontal: 12,
    marginTop: 12,
    borderRadius: 16,
    overflow: "hidden",
    alignItems: "center",
    ...glassCard,
    padding: 16,
  } as any,
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
  headerCard: {
    margin: 12,
    padding: 16,
    ...glassCard,
  } as any,
  productName: { fontWeight: "bold" },
  brand: { color: "#555", marginTop: 4 },
  metaRow: { flexDirection: "row", gap: 16, marginTop: 8 },
  category: { color: "#888" },
  unit: { color: "#888" },
  priceCard: {
    marginHorizontal: 12,
    marginBottom: 8,
    padding: 16,
    ...glassCard,
  } as any,
  sectionLabel: { marginBottom: 8, color: "#555" },
  bestPriceRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  originalPrice: { textDecorationLine: "line-through", color: "#999", marginTop: 4 },
  discount: { color: "#E65100", fontWeight: "bold", marginTop: 2 },
  validUntil: { color: "#888", marginTop: 4 },
  sectionTitle: { paddingHorizontal: 16, paddingVertical: 8, fontWeight: "600" },
  noDataText: { paddingHorizontal: 16, color: "#888" },
  bottomBar: {
    backgroundColor: "rgba(255,255,255,0.95)",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#ddd",
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  watchlistButton: {},
});
