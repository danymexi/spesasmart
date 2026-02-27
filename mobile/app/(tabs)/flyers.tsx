import { FlatList, RefreshControl, StyleSheet, View } from "react-native";
import { Text, useTheme, Chip } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { getFlyers } from "../../services/api";
import { glassCard, glassColors } from "../../styles/glassStyles";

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
};

export default function FlyersScreen() {
  const theme = useTheme();

  const {
    data: flyers,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["flyers"],
    queryFn: () => getFlyers(),
  });

  return (
    <View style={styles.container}>
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
              style={styles.card}
            >
              <View
                style={styles.cardInner}
                onTouchEnd={() => router.push(`/flyer/${item.id}`)}
              >
                <View style={[styles.chainBanner, { backgroundColor: `${chainColor}20` }]}>
                  <Text variant="titleMedium" style={[styles.chainName, { color: chainColor }]}>
                    {item.chain_name ?? "Supermercato"}
                  </Text>
                </View>
                <View style={styles.cardContent}>
                  <Text variant="bodyMedium" numberOfLines={2} style={styles.flyerTitle}>
                    {item.title ?? "Volantino"}
                  </Text>
                  <Text variant="bodySmall" style={styles.dates}>
                    {formatDate(item.valid_from)} - {formatDate(item.valid_to)}
                  </Text>
                  {item.pages_count && (
                    <Text variant="labelSmall" style={styles.pages}>
                      {item.pages_count} pagine
                    </Text>
                  )}
                  <View
                    style={[
                      styles.countdownChip,
                      {
                        backgroundColor: daysLeft <= 2
                          ? glassColors.redAccent
                          : glassColors.greenAccent,
                      },
                    ]}
                  >
                    <Text
                      style={{
                        color: daysLeft <= 2 ? "#C62828" : "#2E7D32",
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
              </View>
            </View>
          );
        }}
        ListEmptyComponent={
          <Text style={styles.emptyText}>Nessun volantino attivo</Text>
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
    borderRadius: 20,
  },
  chainBanner: { paddingVertical: 10, paddingHorizontal: 12 },
  chainName: { fontWeight: "bold" },
  cardContent: { paddingHorizontal: 12, paddingTop: 8, paddingBottom: 12 },
  flyerTitle: { fontWeight: "500", marginBottom: 4 },
  dates: { color: "#666", marginBottom: 4 },
  pages: { color: "#999", marginBottom: 6 },
  countdownChip: {
    alignSelf: "flex-start",
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  emptyText: { textAlign: "center", marginTop: 40, color: "#888" },
  listContent: { paddingTop: 12, paddingBottom: 96 },
});
