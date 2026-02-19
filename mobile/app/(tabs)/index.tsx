import { useCallback } from "react";
import { FlatList, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { Card, Chip, Text, useTheme } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { getActiveOffers, getBestOffers } from "../../services/api";
import OfferCard from "../../components/OfferCard";

export default function HomeScreen() {
  const theme = useTheme();

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

  const onRefresh = useCallback(() => {
    refetchBest();
    refetchActive();
  }, [refetchBest, refetchActive]);

  const isLoading = loadingBest || loadingActive;

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={isLoading} onRefresh={onRefresh} />}
    >
      {/* Header */}
      <View style={[styles.header, { backgroundColor: theme.colors.primary }]}>
        <Text variant="headlineMedium" style={styles.headerTitle}>
          SpesaSmart
        </Text>
        <Text variant="bodyMedium" style={styles.headerSubtitle}>
          Monza e Brianza
        </Text>
      </View>

      {/* Chain filters */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chips}>
        {["Esselunga", "Lidl", "Coop", "Iperal"].map((chain) => (
          <Chip
            key={chain}
            style={styles.chip}
            onPress={() => router.push(`/search?chain=${chain.toLowerCase()}`)}
          >
            {chain}
          </Chip>
        ))}
      </ScrollView>

      {/* Best offers section */}
      <Text variant="titleLarge" style={styles.sectionTitle}>
        Migliori Offerte
      </Text>
      {bestOffers && bestOffers.length > 0 ? (
        <FlatList
          horizontal
          showsHorizontalScrollIndicator={false}
          data={bestOffers}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <View style={styles.horizontalCard}>
              <OfferCard offer={item} compact />
            </View>
          )}
          contentContainerStyle={styles.horizontalList}
          scrollEnabled={false}
        />
      ) : (
        <Text variant="bodyMedium" style={styles.emptyText}>
          Nessuna offerta disponibile
        </Text>
      )}

      {/* All active offers */}
      <Text variant="titleLarge" style={styles.sectionTitle}>
        Offerte Attive
      </Text>
      {activeOffers?.map((offer) => (
        <OfferCard key={offer.id} offer={offer} />
      ))}

      <View style={styles.bottomPadding} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  header: { padding: 20, paddingTop: 12, paddingBottom: 16 },
  headerTitle: { color: "#fff", fontWeight: "bold" },
  headerSubtitle: { color: "rgba(255,255,255,0.8)", marginTop: 2 },
  chips: { paddingHorizontal: 12, paddingVertical: 12, flexGrow: 0 },
  chip: { marginRight: 8 },
  sectionTitle: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 8, fontWeight: "600" },
  horizontalList: { paddingHorizontal: 12 },
  horizontalCard: { width: 260, marginRight: 12 },
  emptyText: { paddingHorizontal: 16, color: "#888" },
  bottomPadding: { height: 24 },
});
