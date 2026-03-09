import { ScrollView, StyleSheet, View } from "react-native";
import { Button, Card, Chip, Text } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import {
  getAdminScrapingStatus,
  getAdminProductStats,
  adminTriggerScraping,
  type AdminChainStatus,
} from "../services/api";
import { glassCard, glassColors } from "../styles/glassStyles";
import { useGlassTheme } from "../styles/useGlassTheme";

function ChainStatusCard({ chain }: { chain: AdminChainStatus }) {
  const glass = useGlassTheme();
  const queryClient = useQueryClient();
  const triggerMutation = useMutation({
    mutationFn: () => adminTriggerScraping(chain.chain_slug),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["adminScraping"] }),
  });

  const isStale = chain.hours_since_update != null && chain.hours_since_update > 48;
  const statusColor = isStale ? "#E65100" : glassColors.greenDark;

  return (
    <View style={[styles.chainCard, glass.card]}>
      <View style={styles.chainHeader}>
        <MaterialCommunityIcons name="store" size={20} color={statusColor} />
        <Text variant="titleMedium" style={[styles.chainName, { color: statusColor }]}>
          {chain.chain_name}
        </Text>
        {isStale && (
          <Chip compact style={styles.staleBadge} textStyle={styles.staleBadgeText}>
            Stale
          </Chip>
        )}
      </View>
      <View style={styles.chainStats}>
        <View style={styles.stat}>
          <Text variant="headlineSmall" style={styles.statValue}>{chain.active_offers}</Text>
          <Text variant="labelSmall" style={styles.statLabel}>Offerte attive</Text>
        </View>
        <View style={styles.stat}>
          <Text variant="headlineSmall" style={styles.statValue}>{chain.total_products}</Text>
          <Text variant="labelSmall" style={styles.statLabel}>Prodotti</Text>
        </View>
        <View style={styles.stat}>
          <Text variant="bodyMedium" style={styles.statValue}>
            {chain.hours_since_update != null ? `${chain.hours_since_update}h` : "—"}
          </Text>
          <Text variant="labelSmall" style={styles.statLabel}>Ultimo aggiorn.</Text>
        </View>
      </View>
      <Button
        mode="outlined"
        icon="refresh"
        compact
        onPress={() => triggerMutation.mutate()}
        loading={triggerMutation.isPending}
        style={styles.triggerBtn}
      >
        Avvia Scraping
      </Button>
    </View>
  );
}

export default function AdminScreen() {
  const glass = useGlassTheme();
  const { data: scraping, isLoading: loadingScraping } = useQuery({
    queryKey: ["adminScraping"],
    queryFn: getAdminScrapingStatus,
  });

  const { data: stats, isLoading: loadingStats } = useQuery({
    queryKey: ["adminStats"],
    queryFn: getAdminProductStats,
  });

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Stack.Screen options={{ title: "Admin Panel" }} />

      {/* Scraping Status */}
      <Text variant="titleLarge" style={styles.sectionTitle}>Scraping Status</Text>

      {loadingScraping ? (
        <Text style={styles.loading}>Caricamento...</Text>
      ) : scraping ? (
        <>
          <View style={styles.summaryRow}>
            <View style={[styles.summaryCard, glass.card]}>
              <Text variant="headlineMedium" style={styles.summaryValue}>
                {scraping.total_offers}
              </Text>
              <Text variant="labelSmall" style={styles.summaryLabel}>Offerte totali</Text>
            </View>
            <View style={[styles.summaryCard, glass.card]}>
              <Text variant="headlineMedium" style={styles.summaryValue}>
                {scraping.total_products}
              </Text>
              <Text variant="labelSmall" style={styles.summaryLabel}>Prodotti totali</Text>
            </View>
          </View>

          {scraping.chains.map((chain) => (
            <ChainStatusCard key={chain.chain_slug} chain={chain} />
          ))}
        </>
      ) : null}

      {/* Product Stats */}
      <Text variant="titleLarge" style={[styles.sectionTitle, { marginTop: 24 }]}>
        Statistiche Prodotti
      </Text>

      {loadingStats ? (
        <Text style={styles.loading}>Caricamento...</Text>
      ) : stats ? (
        <View style={styles.statsGrid}>
          <View style={[styles.statsCard, glass.card]}>
            <Text variant="headlineSmall" style={styles.statsCardValue}>
              {stats.total_products}
            </Text>
            <Text variant="labelSmall" style={styles.statsCardLabel}>Prodotti totali</Text>
          </View>
          <View style={[styles.statsCard, glass.card]}>
            <Text variant="headlineSmall" style={styles.statsCardValue}>
              {stats.products_with_images}
            </Text>
            <Text variant="labelSmall" style={styles.statsCardLabel}>Con immagine</Text>
          </View>
          <View style={[styles.statsCard, glass.card]}>
            <Text variant="headlineSmall" style={[styles.statsCardValue, { color: "#E65100" }]}>
              {stats.products_without_images}
            </Text>
            <Text variant="labelSmall" style={styles.statsCardLabel}>Senza immagine</Text>
          </View>
          <View style={[styles.statsCard, glass.card]}>
            <Text variant="headlineSmall" style={styles.statsCardValue}>
              {stats.total_active_offers}
            </Text>
            <Text variant="labelSmall" style={styles.statsCardLabel}>Offerte attive</Text>
          </View>
          {stats.avg_discount_pct != null && (
            <View style={[styles.statsCard, glass.card]}>
              <Text variant="headlineSmall" style={styles.statsCardValue}>
                {stats.avg_discount_pct}%
              </Text>
              <Text variant="labelSmall" style={styles.statsCardLabel}>Sconto medio</Text>
            </View>
          )}
        </View>
      ) : null}

      {/* Categories breakdown */}
      {stats && Object.keys(stats.products_by_category).length > 0 && (
        <View style={[styles.categorySection, glass.card]}>
          <Text variant="titleMedium" style={styles.categoryTitle}>Per categoria</Text>
          {Object.entries(stats.products_by_category)
            .sort(([, a], [, b]) => b - a)
            .map(([name, count]) => (
              <View key={name} style={styles.categoryRow}>
                <Text variant="bodyMedium" style={styles.categoryName}>{name}</Text>
                <Text variant="bodyMedium" style={styles.categoryCount}>{count}</Text>
              </View>
            ))}
        </View>
      )}

      <View style={{ height: 100 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  content: { padding: 16 },
  sectionTitle: { fontWeight: "700", color: glassColors.greenDark, marginBottom: 12 },
  loading: { color: "#888", textAlign: "center", paddingVertical: 20 },

  // Summary
  summaryRow: { flexDirection: "row", gap: 12, marginBottom: 16 },
  summaryCard: {
    flex: 1,
    alignItems: "center",
    padding: 16,
    ...glassCard,
  } as any,
  summaryValue: { fontWeight: "bold", color: glassColors.greenDark },
  summaryLabel: { color: "#666", marginTop: 4 },

  // Chain cards
  chainCard: {
    marginBottom: 12,
    padding: 16,
    ...glassCard,
  } as any,
  chainHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 },
  chainName: { fontWeight: "600", flex: 1 },
  staleBadge: { backgroundColor: "rgba(245,127,23,0.15)" },
  staleBadgeText: { color: "#E65100", fontSize: 10 },
  chainStats: { flexDirection: "row", gap: 16, marginBottom: 12 },
  stat: { alignItems: "center" },
  statValue: { fontWeight: "600", color: "#333" },
  statLabel: { color: "#888" },
  triggerBtn: { alignSelf: "flex-start" },

  // Product stats
  statsGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  statsCard: {
    width: "47%",
    alignItems: "center",
    padding: 16,
    ...glassCard,
  } as any,
  statsCardValue: { fontWeight: "bold", color: glassColors.greenDark },
  statsCardLabel: { color: "#666", marginTop: 4, textAlign: "center" },

  // Categories
  categorySection: {
    marginTop: 16,
    padding: 16,
    ...glassCard,
  } as any,
  categoryTitle: { fontWeight: "600", color: glassColors.greenDark, marginBottom: 8 },
  categoryRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(0,0,0,0.05)",
  },
  categoryName: { color: "#333" },
  categoryCount: { color: "#666", fontWeight: "600" },
});
