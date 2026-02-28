import { useCallback, useState } from "react";
import { FlatList, Image, StyleSheet, TouchableOpacity, View } from "react-native";
import { Searchbar, Chip, Text, useTheme, ActivityIndicator, IconButton, Snackbar } from "react-native-paper";
import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import {
  getCatalogProducts,
  getCategories,
  getWatchlistIds,
  addToWatchlist,
  removeFromWatchlist,
  type CatalogProduct,
} from "../../services/api";
import { useAppStore } from "../../stores/useAppStore";
import {
  glassCard,
  glassChip,
  glassColors,
  glassSearchbar,
  productImage,
  imagePlaceholder,
} from "../../styles/glassStyles";

const PAGE_SIZE = 50;

export default function CatalogScreen() {
  const theme = useTheme();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [snackbar, setSnackbar] = useState<{ visible: boolean; message: string }>({
    visible: false,
    message: "",
  });

  // Fetch categories dynamically
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  // Fetch catalog products with infinite scroll
  const {
    data: catalogPages,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["catalog", query, selectedCategory],
    queryFn: ({ pageParam = 0 }) =>
      getCatalogProducts({
        q: query || undefined,
        category: selectedCategory ?? undefined,
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (lastPage.length < PAGE_SIZE) return undefined;
      return allPages.reduce((sum, page) => sum + page.length, 0);
    },
  });

  const products = catalogPages?.pages.flat() ?? [];

  // Fetch watchlist IDs for highlighting
  const { data: watchlistData } = useQuery({
    queryKey: ["watchlistIds"],
    queryFn: getWatchlistIds,
    enabled: isLoggedIn,
  });
  const watchlistIds = new Set(watchlistData?.product_ids ?? []);

  // Add to watchlist mutation
  const addMutation = useMutation({
    mutationFn: (productId: string) => addToWatchlist(productId),
    onSuccess: (_data, productId) => {
      queryClient.invalidateQueries({ queryKey: ["watchlistIds"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      const product = products.find((p) => p.id === productId);
      setSnackbar({
        visible: true,
        message: `"${product?.name ?? "Prodotto"}" aggiunto alla lista`,
      });
    },
  });

  // Remove from watchlist mutation
  const removeMutation = useMutation({
    mutationFn: (productId: string) => removeFromWatchlist(productId),
    onSuccess: (_data, productId) => {
      queryClient.invalidateQueries({ queryKey: ["watchlistIds"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      const product = products.find((p) => p.id === productId);
      setSnackbar({
        visible: true,
        message: `"${product?.name ?? "Prodotto"}" rimosso dalla lista`,
      });
    },
  });

  const toggleWatchlist = useCallback(
    (productId: string) => {
      if (watchlistIds.has(productId)) {
        removeMutation.mutate(productId);
      } else {
        addMutation.mutate(productId);
      }
    },
    [watchlistIds, addMutation, removeMutation]
  );

  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const renderProduct = useCallback(
    ({ item }: { item: CatalogProduct }) => {
      const inWatchlist = watchlistIds.has(item.id);

      return (
        <TouchableOpacity
          style={styles.resultCard}
          onPress={() => router.push(`/product/${item.id}`)}
          activeOpacity={0.7}
        >
          <View style={styles.resultCardInner}>
            {item.image_url ? (
              <Image
                source={{ uri: item.image_url }}
                style={styles.resultImage}
                resizeMode="contain"
              />
            ) : (
              <View style={[styles.resultImage, styles.resultImagePlaceholder]}>
                <MaterialCommunityIcons name="food-variant" size={24} color="#ccc" />
              </View>
            )}

            <View style={styles.resultRow}>
              <View style={styles.resultInfo}>
                <Text variant="titleMedium" numberOfLines={2}>
                  {item.name}
                </Text>
                <View style={styles.metaRow}>
                  {item.brand && (
                    <Text variant="bodySmall" style={styles.brandText}>
                      {item.brand}
                    </Text>
                  )}
                  {item.brand && item.category && (
                    <Text variant="bodySmall" style={styles.separator}>|</Text>
                  )}
                  {item.category && (
                    <Text variant="bodySmall" style={styles.categoryText}>
                      {item.category}
                    </Text>
                  )}
                </View>
                {item.has_active_offer ? (
                  <View style={styles.offerRow}>
                    <Text variant="bodySmall" style={styles.offerLabel}>
                      In offerta:{" "}
                    </Text>
                    <Text variant="bodyMedium" style={styles.offerPrice}>
                      {"\u20AC"}{Number(item.best_offer_price).toFixed(2)}
                    </Text>
                    {item.best_chain_name && (
                      <Text variant="bodySmall" style={styles.chainLabel}>
                        {" "}({item.best_chain_name})
                      </Text>
                    )}
                  </View>
                ) : (
                  <Text variant="bodySmall" style={styles.noOffer}>
                    Nessuna offerta attiva
                  </Text>
                )}
              </View>

              {isLoggedIn && (
                <IconButton
                  icon={inWatchlist ? "check-circle" : "plus-circle-outline"}
                  iconColor={inWatchlist ? glassColors.greenMedium : "#999"}
                  size={28}
                  onPress={() => toggleWatchlist(item.id)}
                  style={styles.watchlistBtn}
                />
              )}
            </View>
          </View>
        </TouchableOpacity>
      );
    },
    [watchlistIds, isLoggedIn, toggleWatchlist]
  );

  return (
    <View style={styles.container}>
      <Searchbar
        placeholder="Cerca prodotti..."
        onChangeText={setQuery}
        value={query}
        style={styles.searchbar}
      />

      {/* Category chips */}
      <FlatList
        horizontal
        showsHorizontalScrollIndicator={false}
        data={categories ?? []}
        keyExtractor={(item) => item.name}
        renderItem={({ item }) => (
          <Chip
            selected={selectedCategory === item.name}
            onPress={() =>
              setSelectedCategory(selectedCategory === item.name ? null : item.name)
            }
            style={styles.filterChip}
            compact
          >
            {item.name} ({item.count})
          </Chip>
        )}
        contentContainerStyle={styles.categoryRow}
        style={{ flexGrow: 0 }}
      />

      {/* Results count */}
      {products.length > 0 && (
        <Text variant="labelMedium" style={styles.resultCount}>
          Prodotti ({products.length}{hasNextPage ? "+" : ""})
        </Text>
      )}

      {/* Product list */}
      {isLoading ? (
        <ActivityIndicator style={styles.loader} />
      ) : (
        <FlatList
          data={products}
          keyExtractor={(item) => item.id}
          renderItem={renderProduct}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          ListFooterComponent={
            isFetchingNextPage ? <ActivityIndicator style={styles.footerLoader} /> : null
          }
          ListEmptyComponent={
            <Text style={styles.emptyText}>
              {query
                ? `Nessun risultato per "${query}"`
                : "Sfoglia il catalogo per categoria o cerca un prodotto"}
            </Text>
          }
          contentContainerStyle={styles.listContent}
        />
      )}

      <Snackbar
        visible={snackbar.visible}
        onDismiss={() => setSnackbar((s) => ({ ...s, visible: false }))}
        duration={2000}
        style={styles.snackbar}
      >
        {snackbar.message}
      </Snackbar>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  searchbar: {
    margin: 12,
    ...glassSearchbar,
  } as any,
  filterChip: {
    marginBottom: 6,
    ...glassChip,
  } as any,
  categoryRow: { paddingHorizontal: 12, paddingVertical: 4, gap: 6 },
  resultCount: { paddingHorizontal: 16, paddingVertical: 4, color: "#666" },
  loader: { marginTop: 40 },
  footerLoader: { paddingVertical: 16 },
  resultCard: {
    marginHorizontal: 12,
    marginBottom: 8,
    padding: 12,
    ...glassCard,
  } as any,
  resultCardInner: {
    flexDirection: "row",
    alignItems: "flex-start",
  },
  resultImage: {
    ...productImage.search,
    marginRight: 12,
  },
  resultImagePlaceholder: {
    ...imagePlaceholder,
  },
  resultRow: { flex: 1, flexDirection: "row", alignItems: "center" },
  resultInfo: { flex: 1 },
  metaRow: { flexDirection: "row", alignItems: "center", marginTop: 2 },
  brandText: { color: "#666" },
  separator: { color: "#ccc", marginHorizontal: 4 },
  categoryText: { color: "#888" },
  offerRow: { flexDirection: "row", alignItems: "center", marginTop: 4 },
  offerLabel: { color: "#666" },
  offerPrice: { color: glassColors.greenDark, fontWeight: "bold" },
  chainLabel: { color: "#666" },
  noOffer: { color: "#999", marginTop: 4 },
  watchlistBtn: { margin: 0 },
  emptyText: { textAlign: "center", marginTop: 40, color: "#888", paddingHorizontal: 20 },
  listContent: { paddingBottom: 96 },
  snackbar: { marginBottom: 80 },
});
