import { ScrollView, StyleSheet, View } from "react-native";
import { Button, Card, Divider, Text, useTheme, ActivityIndicator } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { getProduct, getProductHistory, getProductBestPrice, addToWatchlist } from "../../services/api";
import { useAppStore } from "../../stores/useAppStore";
import PriceChart from "../../components/PriceChart";
import PriceIndicator from "../../components/PriceIndicator";
import ProductComparison from "../../components/ProductComparison";

export default function ProductDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const userId = useAppStore((s) => s.userId);
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
    mutationFn: () => addToWatchlist(userId!, id!),
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
    <ScrollView style={styles.container}>
      {/* Product header */}
      <Card style={styles.headerCard}>
        <Card.Content>
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
                Unità: {product.unit}
              </Text>
            )}
          </View>
        </Card.Content>
      </Card>

      {/* Best price card */}
      {bestPrice && (
        <Card style={styles.priceCard}>
          <Card.Content>
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
          </Card.Content>
        </Card>
      )}

      <Divider style={styles.divider} />

      {/* Price comparison across chains */}
      <Text variant="titleMedium" style={styles.sectionTitle}>
        Confronto Prezzi
      </Text>
      <ProductComparison productId={id!} />

      <Divider style={styles.divider} />

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

      {/* Add to watchlist */}
      {userId && (
        <Button
          mode="contained"
          icon="star-plus-outline"
          onPress={() => addMutation.mutate()}
          loading={addMutation.isPending}
          style={styles.watchlistButton}
        >
          Aggiungi alla Lista
        </Button>
      )}

      <View style={styles.bottomPadding} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  loader: { marginTop: 60 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center" },
  headerCard: { margin: 12 },
  productName: { fontWeight: "bold" },
  brand: { color: "#555", marginTop: 4 },
  metaRow: { flexDirection: "row", gap: 16, marginTop: 8 },
  category: { color: "#888" },
  unit: { color: "#888" },
  priceCard: { marginHorizontal: 12, marginBottom: 8 },
  sectionLabel: { marginBottom: 8, color: "#555" },
  bestPriceRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  originalPrice: { textDecorationLine: "line-through", color: "#999", marginTop: 4 },
  discount: { color: "#E65100", fontWeight: "bold", marginTop: 2 },
  validUntil: { color: "#888", marginTop: 4 },
  divider: { marginVertical: 8, marginHorizontal: 12 },
  sectionTitle: { paddingHorizontal: 16, paddingVertical: 8, fontWeight: "600" },
  noDataText: { paddingHorizontal: 16, color: "#888" },
  watchlistButton: { margin: 16 },
  bottomPadding: { height: 30 },
});
