import { useCallback, useEffect, useMemo, useState } from "react";
import { FlatList, ScrollView, StyleSheet, View } from "react-native";
import { Searchbar, Avatar, Chip, Text, ActivityIndicator, Snackbar } from "react-native-paper";
import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import {
  addToShoppingList,
  getCatalogGrouped,
  getCatalogHome,
  getChains,
  getWatchlistIds,
  addToWatchlist,
  removeFromWatchlist,
  type SmartSearchResult,
} from "../../services/api";
import { useAppStore } from "../../stores/useAppStore";
import ExpandableCatalogCard from "../../components/ExpandableCatalogCard";
import { SkeletonList } from "../../components/Skeleton";
import {
  glassChip,
  glassColors,
  glassSearchbar,
} from "../../styles/glassStyles";
import { useGlassTheme } from "../../styles/useGlassTheme";

const PAGE_SIZE = 50;

const SORT_OPTIONS = [
  { key: "name", label: "A-Z" },
  { key: "price", label: "Prezzo" },
  { key: "price_per_unit", label: "Prezzo/unita'" },
] as const;

export default function CatalogScreen() {
  const glass = useGlassTheme();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const catalogProducts = useAppStore((s) => s.catalogProducts);
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSort, setSelectedSort] = useState<string>("name");
  const [selectedChain, setSelectedChain] = useState<string | null>(null);
  const { data: chainsData } = useQuery({
    queryKey: ["chains"],
    queryFn: getChains,
    staleTime: 3600000,
  });
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [snackbar, setSnackbar] = useState<{ visible: boolean; message: string }>({
    visible: false,
    message: "",
  });

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 300);
    return () => clearTimeout(timer);
  }, [query]);

  // Are we browsing (have any filter/search active)?
  const isBrowsing = !!debouncedQuery || !!selectedCategory || !!selectedChain;

  // Catalog home data for browse-mode category chips
  const { data: catalogHomeData } = useQuery({
    queryKey: ["catalogHome"],
    queryFn: getCatalogHome,
    staleTime: 300_000,
  });

  // Local search from preloaded catalog (instant results while API loads)
  const localResults = useMemo(() => {
    if (!query || catalogProducts.length === 0) return [];
    const q = query.toLowerCase();
    return catalogProducts
      .filter((p) => p.name.toLowerCase().includes(q))
      .slice(0, 10);
  }, [query, catalogProducts]);

  // Fetch grouped catalog products with infinite scroll
  const {
    data: catalogPages,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["catalogGrouped", debouncedQuery, selectedCategory, selectedSort, selectedChain],
    queryFn: ({ pageParam = 0 }) =>
      getCatalogGrouped({
        q: debouncedQuery || undefined,
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
    enabled: isBrowsing,
  });

  const rawResults = catalogPages?.pages.flat() ?? [];

  // Insert a separator between active and inactive products
  type ListItem = SmartSearchResult | { _separator: true };
  const results: ListItem[] = useMemo(() => {
    const firstNoOffer = rawResults.findIndex(
      (r) => r.has_active_offers === false
    );
    if (firstNoOffer <= 0) return rawResults;
    return [
      ...rawResults.slice(0, firstNoOffer),
      { _separator: true as const },
      ...rawResults.slice(firstNoOffer),
    ];
  }, [rawResults]);

  // Fetch watchlist IDs for highlighting
  const { data: watchlistData } = useQuery({
    queryKey: ["watchlistIds"],
    queryFn: getWatchlistIds,
    enabled: isLoggedIn,
  });
  const watchlistIds = new Set(watchlistData?.product_ids ?? []);

  // Add to watchlist mutation
  const addWatchlistMut = useMutation({
    mutationFn: (productId: string) => addToWatchlist(productId),
    onSuccess: (_data, productId) => {
      queryClient.invalidateQueries({ queryKey: ["watchlistIds"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      const item = rawResults.find((r) => r.product.id === productId);
      setSnackbar({
        visible: true,
        message: `"${item?.product.name ?? "Prodotto"}" aggiunto alla lista`,
      });
    },
  });

  // Remove from watchlist mutation
  const removeWatchlistMut = useMutation({
    mutationFn: (productId: string) => removeFromWatchlist(productId),
    onSuccess: (_data, productId) => {
      queryClient.invalidateQueries({ queryKey: ["watchlistIds"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      const item = rawResults.find((r) => r.product.id === productId);
      setSnackbar({
        visible: true,
        message: `"${item?.product.name ?? "Prodotto"}" rimosso dalla lista`,
      });
    },
  });

  // Add to shopping list mutation
  const addToListMut = useMutation({
    mutationFn: (productId: string) =>
      addToShoppingList({ product_id: productId }),
    onSuccess: (_data, productId) => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCompare"] });
      const item = rawResults.find((r) => r.product.id === productId);
      setSnackbar({
        visible: true,
        message: `"${item?.product.name ?? "Prodotto"}" aggiunto alla spesa`,
      });
    },
  });

  const toggleWatchlist = useCallback(
    (productId: string) => {
      if (watchlistIds.has(productId)) {
        removeWatchlistMut.mutate(productId);
      } else {
        addWatchlistMut.mutate(productId);
      }
    },
    [watchlistIds, addWatchlistMut, removeWatchlistMut]
  );

  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const renderItem = useCallback(
    ({ item }: { item: ListItem }) => {
      if ("_separator" in item) {
        return (
          <View style={styles.separator}>
            <View style={[styles.separatorLine, { backgroundColor: glass.colors.divider }]} />
            <Text style={[styles.separatorText, { color: glass.colors.textMuted }]}>
              Prodotti senza offerte attive
            </Text>
            <View style={[styles.separatorLine, { backgroundColor: glass.colors.divider }]} />
          </View>
        );
      }
      return (
        <ExpandableCatalogCard
          result={item}
          isInWatchlist={isLoggedIn ? watchlistIds.has(item.product.id) : undefined}
          onWatchlistToggle={isLoggedIn ? toggleWatchlist : undefined}
          onAddToShoppingList={
            isLoggedIn ? (id) => addToListMut.mutate(id) : undefined
          }
        />
      );
    },
    [watchlistIds, isLoggedIn, toggleWatchlist, addToListMut, glass.colors]
  );

  return (
    <View style={styles.container}>
      <Searchbar
        placeholder="Cerca prodotti..."
        onChangeText={setQuery}
        value={query}
        style={[styles.searchbar, glass.searchbar]}
        right={() => (
          <MaterialCommunityIcons
            name="barcode-scan"
            size={22}
            color={glass.colors.primaryMuted}
            style={{ marginRight: 12 }}
            onPress={() => router.push("/barcode-scanner")}
          />
        )}
      />

      {/* Category chips — always visible */}
      {catalogHomeData && catalogHomeData.categories.length > 0 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipRow}
          style={{ flexGrow: 0 }}
        >
          {catalogHomeData.categories.map((cat) => (
            <Chip
              key={cat.slug}
              icon={() => (
                <MaterialCommunityIcons
                  name={cat.icon as any}
                  size={16}
                  color={
                    selectedCategory === cat.name
                      ? glass.colors.primary
                      : glass.colors.textMuted
                  }
                />
              )}
              selected={selectedCategory === cat.name}
              onPress={() =>
                setSelectedCategory(selectedCategory === cat.name ? null : cat.name)
              }
              style={[
                styles.filterChip,
                glass.chip,
                selectedCategory === cat.name && [styles.chipSelected, { backgroundColor: glass.colors.primarySubtle }],
              ]}
              compact
            >
              {cat.name}
            </Chip>
          ))}
        </ScrollView>
      )}

      {/* Idle state: empty state prompt */}
      {!isBrowsing ? (
        <View style={styles.idleContainer}>
          <MaterialCommunityIcons
            name="cart-outline"
            size={48}
            color={glass.colors.textMuted}
          />
          <Text style={[styles.idleText, { color: glass.colors.textSecondary }]}>
            Cerca un prodotto o{"\n"}scegli una categoria
          </Text>
        </View>
      ) : (
        <>
          {/* Sort + Chain chips — single row */}
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chipRow}
            style={{ flexGrow: 0 }}
          >
            {SORT_OPTIONS.map((opt) => (
              <Chip
                key={opt.key}
                selected={selectedSort === opt.key}
                onPress={() => setSelectedSort(opt.key)}
                style={[styles.filterChip, glass.chip, selectedSort === opt.key && [styles.chipSelected, { backgroundColor: glass.colors.primarySubtle }]]}
                compact
              >
                {opt.label}
              </Chip>
            ))}
            <View style={[styles.chipDivider, { backgroundColor: glass.colors.divider }]} />
            {(chainsData ?? []).map((ch) => (
              <Chip
                key={ch.slug}
                selected={selectedChain === ch.name}
                onPress={() => setSelectedChain(selectedChain === ch.name ? null : ch.name)}
                style={[styles.filterChip, glass.chip, selectedChain === ch.name && [styles.chipSelected, { backgroundColor: glass.colors.primarySubtle }]]}
                avatar={ch.logo_url ? <Avatar.Image size={24} source={{ uri: ch.logo_url }} /> : undefined}
                compact
              >
                {ch.name}
              </Chip>
            ))}
          </ScrollView>

          {/* Results count */}
          {rawResults.length > 0 && (
            <Text variant="labelMedium" style={[styles.resultCount, { color: glass.colors.textSecondary }]}>
              Prodotti ({rawResults.length}{hasNextPage ? "+" : ""})
            </Text>
          )}

          {/* Product list */}
          {isLoading ? (
            <SkeletonList count={5} />
          ) : (
            <FlatList
              data={results}
              keyExtractor={(item, index) =>
                "_separator" in item ? `separator-${index}` : item.product.id
              }
              renderItem={renderItem}
              onEndReached={loadMore}
              onEndReachedThreshold={0.5}
              ListFooterComponent={
                isFetchingNextPage ? (
                  <ActivityIndicator style={styles.footerLoader} />
                ) : null
              }
              ListEmptyComponent={
                <Text style={[styles.emptyText, { color: glass.colors.textSecondary }]}>
                  {query
                    ? `Nessun risultato per "${query}"`
                    : selectedCategory
                    ? `Nessun prodotto in "${selectedCategory}"`
                    : "Sfoglia il catalogo per categoria o cerca un prodotto"}
                </Text>
              }
              contentContainerStyle={styles.listContent}
            />
          )}
        </>
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
  resultCount: { paddingHorizontal: 16, paddingVertical: 4, color: "#444" },
  loader: { marginTop: 40 },
  footerLoader: { paddingVertical: 16 },
  emptyText: { textAlign: "center", marginTop: 40, color: "#555", paddingHorizontal: 20 },
  idleContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    gap: 12,
    paddingBottom: 80,
  },
  idleText: {
    fontSize: 15,
    textAlign: "center",
    lineHeight: 22,
  },
  chipDivider: {
    width: 1,
    height: 24,
    alignSelf: "center",
    marginHorizontal: 2,
  },
  listContent: { paddingBottom: 96 },
  snackbar: { marginBottom: 80 },
  separator: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 10,
  },
  separatorLine: {
    flex: 1,
    height: 1,
  },
  separatorText: {
    fontSize: 12,
    fontWeight: "600",
  },
});
