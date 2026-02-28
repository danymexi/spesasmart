import { FlatList, RefreshControl, StyleSheet, View } from "react-native";
import { Button, IconButton, Text, useTheme } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { getWatchlist, removeFromWatchlist } from "../../services/api";
import { useAppStore } from "../../stores/useAppStore";
import PriceIndicator from "../../components/PriceIndicator";
import { glassCard, glassColors, alertBadgeGlass } from "../../styles/glassStyles";

export default function WatchlistScreen() {
  const theme = useTheme();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const queryClient = useQueryClient();

  const {
    data: items,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => getWatchlist(),
    enabled: isLoggedIn,
  });

  const removeMutation = useMutation({
    mutationFn: ({ productId }: { productId: string }) =>
      removeFromWatchlist(productId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  if (!isLoggedIn) {
    return (
      <View style={styles.centered}>
        <Text variant="titleMedium" style={styles.emptyTitle}>
          Accedi per usare la lista
        </Text>
        <Text variant="bodyMedium" style={styles.emptyText}>
          Per salvare prodotti nella tua lista, accedi o registrati nelle Impostazioni.
        </Text>
        <Button mode="contained" onPress={() => router.push("/(tabs)/settings")}>
          Vai alle Impostazioni
        </Button>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} />}
        renderItem={({ item }) => {
          const hasOffer = item.best_current_price != null;

          return (
            <View
              style={styles.card}
            >
              <View style={styles.cardContent}>
                <View style={styles.infoSection}>
                  <Text
                    variant="titleMedium"
                    numberOfLines={2}
                    onPress={() => router.push(`/product/${item.product_id}`)}
                  >
                    {item.product_name}
                  </Text>
                  {item.brand && (
                    <Text variant="bodySmall" style={styles.brand}>
                      {item.brand}
                    </Text>
                  )}
                  {item.target_price && (
                    <Text variant="labelSmall" style={styles.targetPrice}>
                      Prezzo target: {"\u20AC"}{Number(item.target_price).toFixed(2)}
                    </Text>
                  )}
                </View>
                <View style={styles.priceSection}>
                  {hasOffer ? (
                    <>
                      <Text
                        variant="headlineSmall"
                        style={{ color: theme.colors.primary, fontWeight: "bold" }}
                      >
                        {"\u20AC"}{Number(item.best_current_price).toFixed(2)}
                      </Text>
                      <Text variant="labelSmall" style={styles.chainText}>
                        {item.best_chain}
                      </Text>
                      {item.target_price &&
                        Number(item.best_current_price) <= Number(item.target_price) && (
                          <View style={styles.alertBadge}>
                            <Text style={styles.alertText}>SOTTO TARGET</Text>
                          </View>
                        )}
                    </>
                  ) : (
                    <Text variant="bodySmall" style={{ color: "#999" }}>
                      Nessuna offerta
                    </Text>
                  )}
                </View>
                <IconButton
                  icon="delete-outline"
                  size={20}
                  onPress={() => removeMutation.mutate({ productId: item.product_id })}
                />
              </View>
            </View>
          );
        }}
        ListEmptyComponent={
          <View style={styles.centered}>
            <Text variant="titleMedium" style={styles.emptyTitle}>
              Lista vuota
            </Text>
            <Text variant="bodyMedium" style={styles.emptyText}>
              Cerca prodotti e aggiungili alla tua lista per monitorare i prezzi.
            </Text>
            <Button mode="contained" onPress={() => router.push("/(tabs)/search")}>
              Sfoglia il Catalogo
            </Button>
          </View>
        }
        contentContainerStyle={items?.length === 0 ? styles.emptyContainer : styles.listContent}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  centered: { flex: 1, justifyContent: "center", alignItems: "center", padding: 20 },
  emptyContainer: { flexGrow: 1 },
  card: {
    marginHorizontal: 12,
    marginBottom: 8,
    padding: 12,
    ...glassCard,
  } as any,
  cardContent: { flexDirection: "row", alignItems: "center" },
  infoSection: { flex: 1 },
  brand: { color: "#666", marginTop: 2 },
  targetPrice: { color: "#999", marginTop: 4 },
  priceSection: { alignItems: "flex-end", marginRight: 4 },
  chainText: { color: "#666", marginTop: 2 },
  alertBadge: {
    marginTop: 4,
    ...alertBadgeGlass,
  },
  alertText: { color: glassColors.greenMedium, fontSize: 10, fontWeight: "bold" },
  emptyTitle: { marginBottom: 8 },
  emptyText: { color: "#888", textAlign: "center", marginBottom: 16 },
  listContent: { paddingTop: 12, paddingBottom: 96 },
});
