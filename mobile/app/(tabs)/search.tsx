import { useCallback, useState } from "react";
import { FlatList, StyleSheet, View } from "react-native";
import { Searchbar, Chip, Text, ActivityIndicator, Snackbar } from "react-native-paper";
import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from "@tanstack/react-query";
import {
  getCatalogGrouped,
  getCategories,
  getWatchlistIds,
  addToWatchlist,
  removeFromWatchlist,
  type SmartSearchResult,
} from "../../services/api";
import { useAppStore } from "../../stores/useAppStore";
import SmartCompareCard from "../../components/SmartCompareCard";
import {
  glassChip,
  glassColors,
  glassSearchbar,
} from "../../styles/glassStyles";

const PAGE_SIZE = 50;

const SORT_OPTIONS = [
  { key: "name", label: "A-Z" },
  { key: "price", label: "Prezzo" },
  { key: "price_per_unit", label: "Prezzo/unita'" },
] as const;

const CHAINS = ["Esselunga", "Lidl", "Coop", "Iperal"];

export default function CatalogScreen() {
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSort, setSelectedSort] = useState<string>("name");
  const [selectedChain, setSelectedChain] = useState<string | null>(null);
  const [snackbar, setSnackbar] = useState<{ visible: boolean; message: string }>({
    visible: false,
    message: "",
  });

  // Fetch categories dynamically
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: getCategories,
  });

  // Fetch grouped catalog products with infinite scroll
  const {
    data: catalogPages,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["catalogGrouped", query, selectedCategory, selectedSort, selectedChain],
    queryFn: ({ pageParam = 0 }) =>
      getCatalogGrouped({
        q: query || undefined,
        category: selectedCategory ?? undefined,
        sort: selectedSort !== "name" ? selectedSort : undefined,
        chain: selectedChain ? selectedChain.toLowerCase() : undefined,
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (lastPage.length < PAGE_SIZE) return undefined;
      return allPages.reduce((sum, page) => sum + page.length, 0);
    },
  });

  const results = catalogPages?.pages.flat() ?? [];

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
      const item = results.find((r) => r.product.id === productId);
      setSnackbar({
        visible: true,
        message: `"${item?.product.name ?? "Prodotto"}" aggiunto alla lista`,
      });
    },
  });

  // Remove from watchlist mutation
  const removeMutation = useMutation({
    mutationFn: (productId: string) => removeFromWatchlist(productId),
    onSuccess: (_data, productId) => {
      queryClient.invalidateQueries({ queryKey: ["watchlistIds"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      const item = results.find((r) => r.product.id === productId);
      setSnackbar({
        visible: true,
        message: `"${item?.product.name ?? "Prodotto"}" rimosso dalla lista`,
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

  const renderItem = useCallback(
    ({ item }: { item: SmartSearchResult }) => (
      <SmartCompareCard
        result={item}
        isInWatchlist={isLoggedIn ? watchlistIds.has(item.product.id) : undefined}
        onWatchlistToggle={isLoggedIn ? toggleWatchlist : undefined}
      />
    ),
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

      {/* Sort chips */}
      <View style={styles.chipRow}>
        {SORT_OPTIONS.map((opt) => (
          <Chip
            key={opt.key}
            selected={selectedSort === opt.key}
            onPress={() => setSelectedSort(opt.key)}
            style={[styles.filterChip, selectedSort === opt.key && styles.chipSelected]}
            compact
          >
            {opt.label}
          </Chip>
        ))}
      </View>

      {/* Chain chips */}
      <View style={styles.chipRow}>
        {CHAINS.map((ch) => (
          <Chip
            key={ch}
            selected={selectedChain === ch}
            onPress={() => setSelectedChain(selectedChain === ch ? null : ch)}
            style={[styles.filterChip, selectedChain === ch && styles.chipSelected]}
            compact
          >
            {ch}
          </Chip>
        ))}
      </View>

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
      {results.length > 0 && (
        <Text variant="labelMedium" style={styles.resultCount}>
          Prodotti ({results.length}{hasNextPage ? "+" : ""})
        </Text>
      )}

      {/* Product list */}
      {isLoading ? (
        <ActivityIndicator style={styles.loader} />
      ) : (
        <FlatList
          data={results}
          keyExtractor={(item) => item.product.id}
          renderItem={renderItem}
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
  chipRow: { flexDirection: "row", paddingHorizontal: 12, paddingVertical: 4, gap: 6 },
  chipSelected: { backgroundColor: glassColors.greenAccent },
  categoryRow: { paddingHorizontal: 12, paddingVertical: 4, gap: 6 },
  resultCount: { paddingHorizontal: 16, paddingVertical: 4, color: "#555" },
  loader: { marginTop: 40 },
  footerLoader: { paddingVertical: 16 },
  emptyText: { textAlign: "center", marginTop: 40, color: "#666", paddingHorizontal: 20 },
  listContent: { paddingBottom: 96 },
  snackbar: { marginBottom: 80 },
});
