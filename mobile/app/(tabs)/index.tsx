import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ActivityIndicator, Avatar, Button, Chip, Searchbar, Snackbar, Text } from "react-native-paper";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import type { SmartSearchResult } from "../../services/api";
import {
  addToShoppingList,
  getActiveOffers,
  getBestOffers,
  getChains,
  getHistoricLows,
  getShoppingListCount,
  getShoppingListCompare,
  smartSearch,
} from "../../services/api";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import OfferCard from "../../components/OfferCard";
import SmartCompareCard from "../../components/SmartCompareCard";
import BudgetProgressBar from "../../components/BudgetProgressBar";
import HomeSpesaSummary from "../../components/HomeSpesaSummary";
import { SkeletonList } from "../../components/Skeleton";
import { useAppStore } from "../../stores/useAppStore";
import { glassCard, glassColors, glassChip, glassPanel, glassSearchbar } from "../../styles/glassStyles";
import { useGlassTheme } from "../../styles/useGlassTheme";

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const glass = useGlassTheme();
  const queryClient = useQueryClient();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const catalogProducts = useAppStore((s) => s.catalogProducts);
  const nearbyChains = useAppStore((s) => s.nearbyChains);
  const { data: chainsData } = useQuery({
    queryKey: ["chains"],
    queryFn: getChains,
    staleTime: 3600000,
  });
  const [selectedChain, setSelectedChain] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [snackMsg, setSnackMsg] = useState("");
  const [selectedProducts, setSelectedProducts] = useState<Map<string, SmartSearchResult>>(new Map());

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const isSearching = debouncedQuery.length >= 2;

  // Local search: filter pre-loaded catalog when typing
  const localResults = useMemo(() => {
    if (!isSearching || catalogProducts.length === 0) return [];
    const q = debouncedQuery.toLowerCase();
    return catalogProducts
      .filter((p) => p.name.toLowerCase().includes(q))
      .slice(0, 8);
  }, [debouncedQuery, catalogProducts, isSearching]);

  // Smart search (API) — fires alongside local results
  const { data: searchResults, isLoading: loadingSearch } = useQuery({
    queryKey: ["smartSearch", debouncedQuery],
    queryFn: () => smartSearch(debouncedQuery, 15),
    enabled: isSearching,
  });

  // Shopping list count
  const { data: shoppingListCount } = useQuery({
    queryKey: ["shoppingListCount"],
    queryFn: () => getShoppingListCount(),
    enabled: isLoggedIn,
  });
  const hasShoppingList = isLoggedIn && (shoppingListCount ?? 0) > 0;

  // Shopping list compare data
  const { data: compareData, isLoading: loadingCompare } = useQuery({
    queryKey: ["shoppingListCompare", nearbyChains],
    queryFn: () =>
      getShoppingListCompare(
        nearbyChains.length > 0 ? nearbyChains.join(",") : undefined
      ),
    enabled: hasShoppingList,
  });

  // Add to shopping list mutation (for quick-add and multi-select)
  const addMutation = useMutation({
    mutationFn: (params: { product_id?: string; product_ids?: string[]; custom_name?: string }) =>
      addToShoppingList(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCompare"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListSuggestions"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      setSnackMsg("Aggiunto alla lista");
    },
  });

  // Offers (for non-logged-in or empty list state)
  const {
    data: bestOffers,
    isLoading: loadingBest,
    refetch: refetchBest,
  } = useQuery({
    queryKey: ["bestOffers"],
    queryFn: () => getBestOffers(10),
  });

  const {
    data: activeOffers,
    isLoading: loadingActive,
    refetch: refetchActive,
  } = useQuery({
    queryKey: ["activeOffers"],
    queryFn: () => getActiveOffers({ limit: 20 }),
  });

  const {
    data: historicLows,
    isLoading: loadingHistoric,
    refetch: refetchHistoric,
  } = useQuery({
    queryKey: ["historicLows"],
    queryFn: () => getHistoricLows(10),
  });

  // Chain-filtered offers
  const filteredBest = useMemo(() => {
    if (!bestOffers) return [];
    if (!selectedChain) return bestOffers;
    return bestOffers.filter(
      (o) => o.chain_name?.toLowerCase() === selectedChain.toLowerCase()
    );
  }, [bestOffers, selectedChain]);

  const filteredActive = useMemo(() => {
    if (!activeOffers) return [];
    if (!selectedChain) return activeOffers;
    return activeOffers.filter(
      (o) => o.chain_name?.toLowerCase() === selectedChain.toLowerCase()
    );
  }, [activeOffers, selectedChain]);

  const filteredHistoric = useMemo(() => {
    if (!historicLows) return [];
    if (!selectedChain) return historicLows;
    return historicLows.filter(
      (o) => o.chain_name?.toLowerCase() === selectedChain.toLowerCase()
    );
  }, [historicLows, selectedChain]);

  const isLoading = loadingBest || loadingActive || loadingHistoric;

  const onRefresh = useCallback(() => {
    refetchBest();
    refetchActive();
    refetchHistoric();
  }, [refetchBest, refetchActive, refetchHistoric]);

  // Quick-add: submit search query as custom_name to shopping list
  const handleQuickAdd = () => {
    if (!isLoggedIn || !searchQuery.trim()) return;
    addMutation.mutate({ custom_name: searchQuery.trim() });
    setSearchQuery("");
  };

  // Toggle product selection for multi-add
  const toggleProductSelection = useCallback((result: SmartSearchResult) => {
    setSelectedProducts((prev) => {
      const next = new Map(prev);
      if (next.has(result.product.id)) {
        next.delete(result.product.id);
      } else {
        next.set(result.product.id, result);
      }
      return next;
    });
  }, []);

  // Multi-add: add selected products as linked items
  const handleMultiAdd = () => {
    if (!isLoggedIn || selectedProducts.size === 0) return;
    const ids = Array.from(selectedProducts.keys());
    addMutation.mutate({
      product_ids: ids,
      custom_name: searchQuery.trim() || undefined,
    });
    setSelectedProducts(new Map());
    setSearchQuery("");
  };

  return (
    <>
      <ScrollView
        style={styles.container}
        contentContainerStyle={{ paddingTop: insets.top }}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={onRefresh} />}
      >
        {/* Header */}
        <View style={[styles.header, glass.panel, { backgroundColor: glass.colors.primarySubtle }]}>
          <Text variant="headlineMedium" style={[styles.headerTitle, { color: glass.colors.primary }]}>
            SpesaSmart
          </Text>
          <Text variant="bodyMedium" style={[styles.headerSubtitle, { color: glass.colors.textSecondary }]}>
            La tua spesa intelligente
          </Text>
        </View>

        {/* Quick-add search bar */}
        <View style={styles.searchContainer}>
          <Searchbar
            placeholder={
              isLoggedIn
                ? "Cerca e aggiungi alla lista..."
                : "Cerca e confronta prezzi..."
            }
            value={searchQuery}
            onChangeText={setSearchQuery}
            onSubmitEditing={handleQuickAdd}
            style={[styles.searchbar, glass.searchbar]}
            inputStyle={styles.searchInput}
            elevation={0}
            right={() =>
              isLoggedIn && searchQuery.trim().length > 0 ? (
                <MaterialCommunityIcons
                  name="cart-plus"
                  size={22}
                  color={glass.colors.primaryMuted}
                  style={{ marginRight: 12 }}
                  onPress={handleQuickAdd}
                />
              ) : null
            }
          />
        </View>

        {/* Search results */}
        {isSearching ? (
          <View style={styles.searchResults}>
            {loadingSearch && localResults.length === 0 ? (
              <SkeletonList count={3} />
            ) : searchResults && searchResults.length > 0 ? (
              searchResults.map((result) => (
                <SmartCompareCard
                  key={result.product.id}
                  result={result}
                  selectable={isLoggedIn}
                  isSelected={selectedProducts.has(result.product.id)}
                  onToggleSelect={() => toggleProductSelection(result)}
                />
              ))
            ) : (
              <Text variant="bodyMedium" style={[styles.emptyText, { color: glass.colors.textSecondary }]}>
                Nessun prodotto trovato per "{debouncedQuery}"
              </Text>
            )}
          </View>
        ) : (
          <>
            {/* ─── Budget progress ─── */}
            {isLoggedIn && <BudgetProgressBar />}

            {/* ─── Shopping list summary ─── */}
            {hasShoppingList && (
              compareData ? (
                <HomeSpesaSummary
                  compareData={compareData}
                  itemCount={shoppingListCount ?? 0}
                />
              ) : (
                <Pressable
                  style={[styles.shoppingBanner, glass.card, { borderColor: glass.colors.primarySubtle }]}
                  onPress={() => router.push("/(tabs)/watchlist")}
                >
                  <MaterialCommunityIcons
                    name="cart-check"
                    size={20}
                    color={glass.colors.primary}
                  />
                  <Text style={[styles.bannerText, { color: glass.colors.primary }]}>
                    {shoppingListCount} articol{shoppingListCount === 1 ? "o" : "i"} nella lista
                  </Text>
                  {loadingCompare ? (
                    <ActivityIndicator size={14} color={glass.colors.primaryMuted} />
                  ) : (
                    <MaterialCommunityIcons
                      name="chevron-right"
                      size={18}
                      color={glass.colors.textMuted}
                    />
                  )}
                </Pressable>
              )
            )}

            {/* ─── STATE 2: Logged in but empty list ─── */}
            {isLoggedIn && !hasShoppingList && (
              <View style={styles.emptyState}>
                <MaterialCommunityIcons
                  name="cart-outline"
                  size={48}
                  color={glass.colors.primaryFaded}
                />
                <Text style={[styles.emptyStateTitle, { color: glass.colors.primary }]}>
                  La tua lista della spesa e' vuota
                </Text>
                <Text style={[styles.emptyStateSubtitle, { color: glass.colors.textMuted }]}>
                  Aggiungi prodotti per confrontare i prezzi tra catene
                </Text>
                <Button
                  mode="contained"
                  onPress={() => router.push("/(tabs)/search")}
                  style={[styles.emptyStateBtn, { backgroundColor: glass.colors.primary }]}
                  labelStyle={{ fontWeight: "600" }}
                >
                  Sfoglia il Catalogo
                </Button>
              </View>
            )}

            {/* ─── STATE 3: Not logged in ─── */}
            {!isLoggedIn && (
              <View style={styles.emptyState}>
                <MaterialCommunityIcons
                  name="account-outline"
                  size={48}
                  color={glass.colors.primaryFaded}
                />
                <Text style={[styles.emptyStateTitle, { color: glass.colors.primary }]}>
                  Accedi per la spesa personalizzata
                </Text>
                <Text style={[styles.emptyStateSubtitle, { color: glass.colors.textMuted }]}>
                  Confronta prezzi, ottimizza la spesa e risparmia
                </Text>
                <Button
                  mode="contained"
                  onPress={() => router.push("/(tabs)/settings")}
                  style={[styles.emptyStateBtn, { backgroundColor: glass.colors.primary }]}
                  labelStyle={{ fontWeight: "600" }}
                >
                  Accedi
                </Button>
              </View>
            )}

            {/* ─── Offers section (always visible below) ─── */}
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={styles.chips}
            >
              {(chainsData ?? []).map((chain) => (
                <Chip
                  key={chain.slug}
                  style={[
                    styles.chip,
                    glass.chip,
                    selectedChain === chain.name && [styles.chipSelected, { backgroundColor: glass.colors.primarySubtle }],
                  ]}
                  selected={selectedChain === chain.name}
                  onPress={() =>
                    setSelectedChain(selectedChain === chain.name ? null : chain.name)
                  }
                  avatar={chain.logo_url ? <Avatar.Image size={24} source={{ uri: chain.logo_url }} /> : undefined}
                >
                  {chain.name}
                </Chip>
              ))}
            </ScrollView>

            {/* Best offers */}
            <Text variant="titleLarge" style={[styles.sectionTitle, { color: glass.colors.primary }]}>
              Migliori Offerte
            </Text>
            {filteredBest.length > 0 ? (
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.horizontalList}
              >
                {filteredBest.map((item) => (
                  <View key={item.id} style={styles.horizontalCard}>
                    <OfferCard offer={item} compact />
                  </View>
                ))}
              </ScrollView>
            ) : (
              <Text variant="bodyMedium" style={[styles.emptyText, { color: glass.colors.textSecondary }]}>
                Nessuna offerta disponibile
              </Text>
            )}

            {/* Historic lows */}
            <View style={styles.sectionHeader}>
              <MaterialCommunityIcons
                name="trending-down"
                size={22}
                color={glass.colors.primary}
              />
              <Text variant="titleLarge" style={[styles.sectionTitleInline, { color: glass.colors.primary }]}>
                Minimi Storici
              </Text>
            </View>
            {filteredHistoric.length > 0 ? (
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.horizontalList}
              >
                {filteredHistoric.map((item) => (
                  <View key={item.id} style={styles.horizontalCard}>
                    <OfferCard offer={item} compact />
                  </View>
                ))}
              </ScrollView>
            ) : (
              <Text variant="bodyMedium" style={[styles.emptyText, { color: glass.colors.textSecondary }]}>
                Nessun minimo storico disponibile
              </Text>
            )}

            {/* All active offers */}
            <Text variant="titleLarge" style={[styles.sectionTitle, { color: glass.colors.primary }]}>
              Offerte Attive
            </Text>
            {filteredActive.map((offer) => (
              <OfferCard key={offer.id} offer={offer} />
            ))}

            <View style={styles.bottomPadding} />
          </>
        )}
      </ScrollView>

      {/* Floating action: multi-add to shopping list */}
      {selectedProducts.size > 0 && (
        <View style={[styles.floatingAction, { backgroundColor: glass.colors.surface }]}>
          <Button
            mode="contained"
            onPress={handleMultiAdd}
            loading={addMutation.isPending}
            style={[styles.floatingBtn, { backgroundColor: glass.colors.primary }]}
            labelStyle={styles.floatingBtnLabel}
            icon="cart-plus"
          >
            Aggiungi {selectedProducts.size} alla lista
          </Button>
          <Button
            mode="text"
            onPress={() => setSelectedProducts(new Map())}
            labelStyle={[styles.floatingCancelLabel, { color: glass.colors.textMuted }]}
          >
            Annulla
          </Button>
        </View>
      )}

      {/* Snackbar */}
      <Snackbar
        visible={!!snackMsg}
        onDismiss={() => setSnackMsg("")}
        duration={2000}
        style={styles.snackbar}
      >
        {snackMsg}
      </Snackbar>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  header: {
    marginHorizontal: 12,
    marginTop: 12,
    padding: 20,
    paddingBottom: 16,
    ...glassPanel,
    backgroundColor: "rgba(46,125,50,0.12)",
  } as any,
  headerTitle: { color: glassColors.greenDark, fontWeight: "bold" },
  headerSubtitle: { color: glassColors.greenSubtle, marginTop: 2 },
  searchContainer: { paddingHorizontal: 12, marginTop: 12 },
  searchbar: { ...glassSearchbar } as any,
  searchInput: { fontSize: 16 },
  searchResults: { marginTop: 8 },
  chips: { paddingHorizontal: 12, paddingVertical: 12, flexGrow: 0 },
  chip: {
    marginRight: 8,
    ...glassChip,
  } as any,
  chipSelected: {
    backgroundColor: glassColors.greenAccent,
  },
  sectionTitle: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
    fontWeight: "700",
    color: glassColors.greenDark,
  },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
    gap: 6,
  },
  sectionTitleInline: { fontWeight: "700", color: glassColors.greenDark },
  horizontalList: { paddingHorizontal: 12 },
  horizontalCard: { width: 260, marginRight: 12 },
  emptyText: { paddingHorizontal: 16, color: "#555" },
  emptyState: {
    alignItems: "center",
    paddingVertical: 32,
    paddingHorizontal: 24,
    gap: 8,
  },
  emptyStateTitle: {
    fontSize: 17,
    fontWeight: "700",
    color: glassColors.greenDark,
    textAlign: "center",
  },
  emptyStateSubtitle: {
    fontSize: 14,
    color: glassColors.textMuted,
    textAlign: "center",
  },
  emptyStateBtn: {
    marginTop: 12,
    borderRadius: 16,
    backgroundColor: glassColors.greenMedium,
  },
  shoppingBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginHorizontal: 12,
    marginTop: 12,
    paddingVertical: 12,
    paddingHorizontal: 16,
    ...glassCard,
    borderColor: "rgba(46,125,50,0.2)",
  } as any,
  bannerText: {
    flex: 1,
    fontSize: 14,
    fontWeight: "600",
    color: glassColors.greenDark,
  },
  floatingAction: {
    position: "absolute",
    bottom: 80,
    left: 12,
    right: 12,
    backgroundColor: "rgba(255,255,255,0.95)",
    borderRadius: 16,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: "center",
    zIndex: 100,
    elevation: 8,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
  },
  floatingBtn: {
    width: "100%",
    borderRadius: 12,
    backgroundColor: glassColors.greenDark,
  },
  floatingBtnLabel: {
    fontWeight: "700",
    fontSize: 15,
  },
  floatingCancelLabel: {
    color: "#666",
    fontSize: 13,
  },
  snackbar: {
    marginBottom: 80,
  },
  bottomPadding: { height: 96 },
});
