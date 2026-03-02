import { useCallback, useEffect, useMemo, useState } from "react";
import { FlatList, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ActivityIndicator, Chip, Searchbar, Text, useTheme } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { getActiveOffers, getAlternatives, getBestOffers, getBrandDeals, getHistoricLows, getUserBrands, getWatchlist, smartSearch } from "../../services/api";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import OfferCard from "../../components/OfferCard";
import PersonalDeals from "../../components/PersonalDeals";
import SmartCompareCard from "../../components/SmartCompareCard";
import { useAppStore } from "../../stores/useAppStore";
import { glassColors, glassChip, glassPanel, glassSearchbar } from "../../styles/glassStyles";

const CHAINS = ["Esselunga", "Lidl", "Coop", "Iperal"];

export default function HomeScreen() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const [selectedChain, setSelectedChain] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Smart search query
  const { data: searchResults, isLoading: loadingSearch } = useQuery({
    queryKey: ["smartSearch", debouncedQuery],
    queryFn: () => smartSearch(debouncedQuery, 5),
    enabled: debouncedQuery.length >= 2,
  });

  const isSearching = debouncedQuery.length >= 2;

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

  // Check if user has watchlist items (lightweight check)
  const { data: watchlistItems } = useQuery({
    queryKey: ["watchlist"],
    queryFn: getWatchlist,
    enabled: isLoggedIn,
  });

  const hasWatchlist = isLoggedIn && watchlistItems && watchlistItems.length > 0;

  // User brands
  const { data: userBrands } = useQuery({
    queryKey: ["userBrands"],
    queryFn: getUserBrands,
    enabled: isLoggedIn,
  });
  const hasBrands = isLoggedIn && userBrands && userBrands.length > 0;

  // Brand deals
  const {
    data: brandDeals,
    refetch: refetchBrandDeals,
  } = useQuery({
    queryKey: ["brandDeals"],
    queryFn: () => getBrandDeals(),
    enabled: hasBrands,
  });

  // Suggested alternatives
  const {
    data: alternatives,
    refetch: refetchAlternatives,
  } = useQuery({
    queryKey: ["alternatives"],
    queryFn: () => getAlternatives(),
    enabled: hasWatchlist,
  });

  const filteredBrandDeals = useMemo(() => {
    if (!brandDeals) return [];
    if (!selectedChain) return brandDeals;
    return brandDeals.filter(
      (o) => o.chain_name?.toLowerCase() === selectedChain.toLowerCase()
    );
  }, [brandDeals, selectedChain]);

  const onRefresh = useCallback(() => {
    refetchBest();
    refetchActive();
    refetchHistoric();
    if (hasBrands) refetchBrandDeals();
    if (hasWatchlist) refetchAlternatives();
  }, [refetchBest, refetchActive, refetchHistoric, refetchBrandDeals, refetchAlternatives, hasBrands, hasWatchlist]);

  const isLoading = loadingBest || loadingActive || loadingHistoric;

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

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={{ paddingTop: insets.top }}
      refreshControl={<RefreshControl refreshing={isLoading} onRefresh={onRefresh} />}
    >
      {/* Header */}
      <View style={styles.header}>
        <Text variant="headlineMedium" style={styles.headerTitle}>
          SpesaSmart
        </Text>
        <Text variant="bodyMedium" style={styles.headerSubtitle}>
          Monza e Brianza
        </Text>
      </View>

      {/* Smart Search Bar */}
      <View style={styles.searchContainer}>
        <Searchbar
          placeholder="Cerca e confronta prezzi..."
          value={searchQuery}
          onChangeText={setSearchQuery}
          style={styles.searchbar}
          inputStyle={styles.searchInput}
          elevation={0}
        />
      </View>

      {/* Smart Search Results (replaces normal content when searching) */}
      {isSearching ? (
        <View style={styles.searchResults}>
          {loadingSearch ? (
            <ActivityIndicator style={{ marginTop: 20 }} />
          ) : searchResults && searchResults.length > 0 ? (
            searchResults.map((result) => (
              <SmartCompareCard key={result.product.id} result={result} />
            ))
          ) : (
            <Text variant="bodyMedium" style={styles.emptyText}>
              Nessun prodotto trovato per "{debouncedQuery}"
            </Text>
          )}
        </View>
      ) : (
      <>
      {/* Personalized deals section (only for logged-in users with watchlist) */}
      {hasWatchlist && <PersonalDeals />}

      {/* Brand Deals section */}
      {hasBrands && filteredBrandDeals.length > 0 && (
        <>
          <View style={styles.sectionHeader}>
            <MaterialCommunityIcons name="heart" size={22} color={glassColors.greenDark} />
            <Text variant="titleLarge" style={styles.sectionTitleInline}>
              Le Tue Marche in Offerta
            </Text>
          </View>
          <FlatList
            horizontal
            showsHorizontalScrollIndicator={false}
            data={filteredBrandDeals}
            keyExtractor={(item, i) => `${item.product_id}-${item.chain_name}-${i}`}
            renderItem={({ item }) => (
              <View style={styles.horizontalCard}>
                <OfferCard
                  offer={{
                    id: item.product_id,
                    product_id: item.product_id,
                    product_name: item.product_name,
                    brand: item.brand,
                    chain_name: item.chain_name,
                    original_price: item.original_price,
                    offer_price: item.offer_price,
                    discount_pct: item.discount_pct,
                    valid_to: item.valid_to,
                    image_url: item.image_url,
                  }}
                  compact
                />
              </View>
            )}
            contentContainerStyle={styles.horizontalList}
          />
        </>
      )}

      {/* Suggested Alternatives section */}
      {hasWatchlist && alternatives && alternatives.length > 0 && (
        <>
          <View style={styles.sectionHeader}>
            <MaterialCommunityIcons name="lightbulb-on-outline" size={22} color="#E65100" />
            <Text variant="titleLarge" style={styles.sectionTitleInline}>
              Alternative Suggerite
            </Text>
          </View>
          <FlatList
            horizontal
            showsHorizontalScrollIndicator={false}
            data={alternatives}
            keyExtractor={(item, i) => `${item.product_id}-${item.chain_name}-${i}`}
            renderItem={({ item }) => (
              <View style={styles.horizontalCard}>
                <OfferCard
                  offer={{
                    id: item.product_id,
                    product_id: item.product_id,
                    product_name: item.product_name,
                    brand: item.brand,
                    chain_name: item.chain_name,
                    original_price: item.original_price,
                    offer_price: item.offer_price,
                    discount_pct: item.discount_pct,
                    valid_to: item.valid_to,
                    image_url: item.image_url,
                  }}
                  compact
                />
                {item.price_per_unit && (
                  <View style={styles.ppuBadge}>
                    <Text style={styles.ppuText}>
                      {"\u20AC"}{Number(item.price_per_unit).toFixed(2)}/{item.unit_reference || "kg"}
                    </Text>
                  </View>
                )}
              </View>
            )}
            contentContainerStyle={styles.horizontalList}
          />
        </>
      )}

      {/* Chain filters */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chips}>
        {CHAINS.map((chain) => (
          <Chip
            key={chain}
            style={[styles.chip, selectedChain === chain && styles.chipSelected]}
            selected={selectedChain === chain}
            onPress={() =>
              setSelectedChain(selectedChain === chain ? null : chain)
            }
          >
            {chain}
          </Chip>
        ))}
      </ScrollView>

      {/* Best offers section */}
      <Text variant="titleLarge" style={styles.sectionTitle}>
        Migliori Offerte
      </Text>
      {filteredBest.length > 0 ? (
        <FlatList
          horizontal
          showsHorizontalScrollIndicator={false}
          data={filteredBest}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <View style={styles.horizontalCard}>
              <OfferCard offer={item} compact />
            </View>
          )}
          contentContainerStyle={styles.horizontalList}
        />
      ) : (
        <Text variant="bodyMedium" style={styles.emptyText}>
          Nessuna offerta disponibile
        </Text>
      )}

      {/* Historic lows section */}
      <View style={styles.sectionHeader}>
        <MaterialCommunityIcons name="trending-down" size={22} color={glassColors.greenDark} />
        <Text variant="titleLarge" style={styles.sectionTitleInline}>
          Minimi Storici
        </Text>
      </View>
      {filteredHistoric.length > 0 ? (
        <FlatList
          horizontal
          showsHorizontalScrollIndicator={false}
          data={filteredHistoric}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <View style={styles.horizontalCard}>
              <OfferCard offer={item} compact />
            </View>
          )}
          contentContainerStyle={styles.horizontalList}
        />
      ) : (
        <Text variant="bodyMedium" style={styles.emptyText}>
          Nessun minimo storico disponibile
        </Text>
      )}

      {/* All active offers */}
      <Text variant="titleLarge" style={styles.sectionTitle}>
        Offerte Attive
      </Text>
      {filteredActive.map((offer) => (
        <OfferCard key={offer.id} offer={offer} />
      ))}

      <View style={styles.bottomPadding} />
      </>
      )}
    </ScrollView>
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
  searchInput: { fontSize: 14 },
  searchResults: { marginTop: 8 },
  chips: { paddingHorizontal: 12, paddingVertical: 12, flexGrow: 0 },
  chip: {
    marginRight: 8,
    ...glassChip,
  } as any,
  chipSelected: {
    backgroundColor: glassColors.greenAccent,
  },
  sectionTitle: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 8, fontWeight: "700", color: glassColors.greenDark },
  sectionHeader: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingTop: 16, paddingBottom: 8, gap: 6 },
  sectionTitleInline: { fontWeight: "700", color: glassColors.greenDark },
  horizontalList: { paddingHorizontal: 12 },
  horizontalCard: { width: 260, marginRight: 12 },
  emptyText: { paddingHorizontal: 16, color: "#555" },
  ppuBadge: {
    backgroundColor: "rgba(230,81,0,0.10)",
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
    marginTop: 4,
    alignSelf: "flex-start",
    marginLeft: 4,
  },
  ppuText: { color: "#E65100", fontSize: 11, fontWeight: "600" },
  bottomPadding: { height: 96 },
});
