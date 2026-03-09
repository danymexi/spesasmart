import { useState } from "react";
import { FlatList, Pressable, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import { Text, useTheme, Avatar, Chip } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { getChains, getFlyers } from "../../services/api";
import { glassCard, glassChip, glassColors } from "../../styles/glassStyles";
import { useGlassTheme } from "../../styles/useGlassTheme";

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr);
  const now = new Date();
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("it-IT", {
    day: "numeric",
    month: "short",
  });
}

const CHAIN_COLORS: Record<string, string> = {
  Esselunga: "#D32F2F",
  Lidl: "#0039A6",
  Coop: "#E53935",
  Iperal: "#1565C0",
  Carrefour: "#004E9A",
  Conad: "#E31E24",
  Eurospin: "#1A4D8F",
  Aldi: "#00205B",
  "MD Discount": "#E5007D",
  "Penny Market": "#CD1719",
  "PAM Panorama": "#E4002B",
};

export default function FlyersScreen() {
  const theme = useTheme();
  const glass = useGlassTheme();
  const [selectedChain, setSelectedChain] = useState<string | null>(null);

  const { data: chainsData } = useQuery({
    queryKey: ["chains"],
    queryFn: getChains,
    staleTime: 3600000,
  });

  const {
    data: flyers,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["flyers", selectedChain],
    queryFn: () => getFlyers(selectedChain ? selectedChain.toLowerCase() : undefined),
  });

  return (
    <View style={styles.container}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chainChips}
        contentContainerStyle={styles.chainChipsContent}
      >
        {(chainsData ?? []).map((ch) => (
          <Chip
            key={ch.slug}
            selected={selectedChain === ch.name}
            onPress={() => setSelectedChain(selectedChain === ch.name ? null : ch.name)}
            style={[
              styles.chainChip,
              glass.chip,
              selectedChain === ch.name && { backgroundColor: glass.colors.primarySubtle },
            ]}
            avatar={ch.logo_url ? <Avatar.Image size={24} source={{ uri: ch.logo_url }} /> : undefined}
            compact
          >
            {ch.name}
          </Chip>
        ))}
      </ScrollView>
      <FlatList
        data={flyers}
        keyExtractor={(item) => item.id}
        numColumns={2}
        columnWrapperStyle={styles.row}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} />}
        renderItem={({ item }) => {
          const daysLeft = daysUntil(item.valid_to);
          const chainColor = CHAIN_COLORS[item.chain_name ?? ""] ?? theme.colors.primary;

          return (
            <View
              style={[styles.card, glass.card]}
            >
              <Pressable
                style={styles.cardInner}
                onPress={() => router.push(`/flyer/${item.id}`)}
              >
                <View style={[styles.chainBanner, { backgroundColor: `${chainColor}20` }]}>
                  <Text variant="titleMedium" style={[styles.chainName, { color: chainColor }]}>
                    {item.chain_name ?? "Supermercato"}
                  </Text>
                </View>
                <View style={styles.cardContent}>
                  <Text variant="bodyMedium" numberOfLines={2} style={[styles.flyerTitle, { color: glass.colors.textPrimary }]}>
                    {item.title ?? "Volantino"}
                  </Text>
                  <Text variant="bodySmall" style={[styles.dates, { color: glass.colors.textSecondary }]}>
                    {formatDate(item.valid_from)} - {formatDate(item.valid_to)}
                  </Text>
                  {item.pages_count && (
                    <Text variant="labelSmall" style={[styles.pages, { color: glass.colors.textMuted }]}>
                      {item.pages_count} pagine
                    </Text>
                  )}
                  <View
                    style={[
                      styles.countdownChip,
                      {
                        backgroundColor: daysLeft <= 2
                          ? glass.colors.errorSubtle
                          : glass.colors.successSubtle,
                      },
                    ]}
                  >
                    <Text
                      style={{
                        color: daysLeft <= 2 ? glass.colors.error : glass.colors.success,
                        fontSize: 11,
                        fontWeight: "600",
                      }}
                    >
                      {daysLeft <= 0
                        ? "Scaduto"
                        : daysLeft === 1
                          ? "Scade domani"
                          : `${daysLeft} giorni`}
                    </Text>
                  </View>
                </View>
              </Pressable>
            </View>
          );
        }}
        ListEmptyComponent={
          <Text style={[styles.emptyText, { color: glass.colors.textSecondary }]}>Nessun volantino attivo</Text>
        }
        contentContainerStyle={styles.listContent}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  row: { justifyContent: "space-between", paddingHorizontal: 12 },
  card: {
    width: "48%",
    marginBottom: 12,
    overflow: "hidden",
    ...glassCard,
  } as any,
  cardInner: {
    overflow: "hidden",
    borderRadius: 16,
  },
  chainBanner: { paddingVertical: 10, paddingHorizontal: 12 },
  chainName: { fontWeight: "bold" },
  cardContent: { paddingHorizontal: 12, paddingTop: 8, paddingBottom: 12 },
  flyerTitle: { fontWeight: "600", marginBottom: 4, color: "#1a1a1a" },
  dates: { color: "#555", marginBottom: 4 },
  pages: { color: "#666", marginBottom: 6 },
  countdownChip: {
    alignSelf: "flex-start",
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  chainChips: { flexGrow: 0, paddingTop: 12 },
  chainChipsContent: { paddingHorizontal: 12, gap: 8 },
  chainChip: { ...glassChip } as any,
  emptyText: { textAlign: "center", marginTop: 40, color: "#555" },
  listContent: { paddingTop: 12, paddingBottom: 96 },
});
