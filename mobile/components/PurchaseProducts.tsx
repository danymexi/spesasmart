import { useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import {
  Button,
  Chip,
  IconButton,
  Snackbar,
  Text,
} from "react-native-paper";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  getSmartList,
  addToWatchlist,
  syncSmartListToWatchlist,
  backfillReceiptProducts,
} from "../services/api";
import type { SmartListItem } from "../services/api";
import { useRouter } from "expo-router";
import { glassCard, glassColors } from "../styles/glassStyles";

export default function PurchaseProducts() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [snackbar, setSnackbar] = useState("");
  const { data: items, isLoading } = useQuery({
    queryKey: ["smartList"],
    queryFn: getSmartList,
  });

  const backfillMutation = useMutation({
    mutationFn: backfillReceiptProducts,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["smartList"] });
      setSnackbar(`Collegati ${data.matched}/${data.total} prodotti al catalogo`);
    },
    onError: () => setSnackbar("Errore durante il collegamento prodotti"),
  });

  const addSingleMutation = useMutation({
    mutationFn: (productId: string) => addToWatchlist(productId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["smartList"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      setSnackbar("Aggiunto alla watchlist");
    },
  });

  const syncAllMutation = useMutation({
    mutationFn: (productIds: string[]) => syncSmartListToWatchlist(productIds),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["smartList"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
      setSnackbar(`${data.added} prodotti aggiunti alla watchlist`);
    },
  });

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={glassColors.greenMedium} />
      </View>
    );
  }

  if (!items || items.length === 0) {
    return (
      <View style={styles.center}>
        <Text variant="bodyLarge" style={{ color: glassColors.textSecondary, textAlign: "center", marginBottom: 12 }}>
          Nessun prodotto rilevato.
        </Text>
        <Text variant="bodySmall" style={{ color: glassColors.textSecondary, textAlign: "center", marginBottom: 16, paddingHorizontal: 24 }}>
          Servono almeno 2 acquisti dello stesso prodotto. Prova a collegare i prodotti al catalogo:
        </Text>
        <Button
          mode="contained"
          icon="link-variant"
          onPress={() => backfillMutation.mutate()}
          loading={backfillMutation.isPending}
          disabled={backfillMutation.isPending}
          style={{ backgroundColor: glassColors.greenMedium }}
        >
          Collega prodotti al catalogo
        </Button>
        <Snackbar visible={!!snackbar} onDismiss={() => setSnackbar("")} duration={3000}>{snackbar}</Snackbar>
      </View>
    );
  }

  const urgencyColor: Record<string, string> = {
    alta: "#C62828",
    media: "#EF6C00",
    bassa: "#2E7D32",
  };

  const withProductId = items.filter((i) => i.product_id !== null);
  const notInWatchlist = withProductId.filter((i) => !i.in_watchlist);
  const hasUnmatched = items.some((i) => i.product_id === null);

  const formatDaysInfo = (item: SmartListItem): string | null => {
    if (item.days_until_due == null) {
      if (item.next_purchase_predicted) {
        return `Prossimo: ${new Date(item.next_purchase_predicted).toLocaleDateString("it-IT", { day: "numeric", month: "short" })}`;
      }
      return null;
    }
    if (item.days_until_due < 0) return `Scaduto da ${Math.abs(item.days_until_due)} giorni`;
    if (item.days_until_due === 0) return "Da comprare oggi";
    return `Tra ${item.days_until_due} giorni`;
  };

  return (
    <View style={{ flex: 1 }}>
      <View style={styles.syncBar}>
        {notInWatchlist.length > 0 ? (
          <Button
            mode="contained"
            icon="sync"
            compact
            onPress={() => syncAllMutation.mutate(notInWatchlist.map((i) => i.product_id!))}
            loading={syncAllMutation.isPending}
            style={styles.syncBtn}
            labelStyle={{ fontSize: 12 }}
          >
            Sincronizza con Watchlist ({notInWatchlist.length})
          </Button>
        ) : (
          <Button
            mode="outlined"
            icon="sync"
            compact
            onPress={() => syncAllMutation.mutate(withProductId.map((i) => i.product_id!))}
            loading={syncAllMutation.isPending}
            disabled={withProductId.length === 0}
            style={styles.forceSyncBtn}
            labelStyle={{ fontSize: 12 }}
          >
            Forza sincronizzazione ({withProductId.length})
          </Button>
        )}
      </View>
      {hasUnmatched && (
        <View style={styles.backfillBanner}>
          <Text variant="bodySmall" style={{ color: glassColors.textSecondary, flex: 1 }}>
            Alcuni prodotti non sono collegati al catalogo.
          </Text>
          <Button
            mode="text"
            icon="link-variant"
            compact
            onPress={() => backfillMutation.mutate()}
            loading={backfillMutation.isPending}
            disabled={backfillMutation.isPending}
            labelStyle={{ fontSize: 11, color: glassColors.greenDark }}
          >
            Collega
          </Button>
        </View>
      )}
      <FlatList
        data={items}
        keyExtractor={(item) => item.product_id || item.product_name}
        contentContainerStyle={styles.listContent}
        renderItem={({ item }) => {
          const daysText = formatDaysInfo(item);
          return (
            <Pressable
              style={styles.card}
              onPress={() => {
                if (item.product_id) {
                  router.push(`/product/${item.product_id}`);
                }
              }}
            >
              <View style={styles.smartHeader}>
                <View style={{ flex: 1 }}>
                  <Text variant="titleSmall" style={styles.habitName}>
                    {item.product_name}
                  </Text>
                  {item.brand && (
                    <Text variant="bodySmall" style={styles.habitBrand}>
                      {item.brand}
                    </Text>
                  )}
                </View>
                {item.product_id !== null && (
                  <IconButton
                    icon={item.in_watchlist ? "star" : "star-outline"}
                    size={20}
                    iconColor={item.in_watchlist ? "#FFD200" : glassColors.textMuted}
                    onPress={() => {
                      if (!item.in_watchlist && item.product_id) {
                        addSingleMutation.mutate(item.product_id);
                      }
                    }}
                    disabled={item.in_watchlist || addSingleMutation.isPending}
                    style={{ margin: 0 }}
                  />
                )}
                {item.urgency && (
                  <Chip
                    compact
                    style={{
                      backgroundColor: `${urgencyColor[item.urgency]}15`,
                    }}
                    textStyle={{
                      color: urgencyColor[item.urgency],
                      fontSize: 11,
                      fontWeight: "700",
                    }}
                  >
                    {item.urgency.toUpperCase()}
                  </Chip>
                )}
              </View>

              <Text variant="bodySmall" style={styles.statsRow}>
                {item.total_purchases} acquisti{" "}
                {item.avg_interval_days > 0 && `\u00B7 ogni ${Math.round(item.avg_interval_days)}gg `}
                {item.avg_price != null && `\u00B7 \u20AC${item.avg_price.toFixed(2)}`}
              </Text>

              <View style={styles.smartDetails}>
                {item.best_current_price != null && (
                  <View style={styles.smartPriceRow}>
                    <Text variant="bodySmall" style={styles.statLabel}>
                      Miglior prezzo:
                    </Text>
                    <Text variant="bodyMedium" style={styles.smartPrice}>
                      {item.best_current_price.toFixed(2)}
                    </Text>
                    {item.best_chain && (
                      <Text variant="bodySmall" style={styles.smartChain}>
                        ({item.best_chain})
                      </Text>
                    )}
                  </View>
                )}
                {item.savings_vs_avg != null && item.savings_vs_avg > 0 && (
                  <Text variant="bodySmall" style={styles.savings}>
                    Risparmi {item.savings_vs_avg.toFixed(2)} vs media storica
                  </Text>
                )}
                {daysText && (
                  <Text variant="bodySmall" style={styles.daysInfo}>
                    {daysText}
                  </Text>
                )}
              </View>
            </Pressable>
          );
        }}
      />
      <Snackbar
        visible={!!snackbar}
        onDismiss={() => setSnackbar("")}
        duration={3000}
        style={styles.snackbar}
      >
        {snackbar}
      </Snackbar>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  listContent: { padding: 12, paddingBottom: 100 },
  card: {
    ...(glassCard as object),
    padding: 16,
    marginBottom: 10,
  } as any,
  habitName: { color: glassColors.textPrimary, fontWeight: "600" },
  habitBrand: { color: glassColors.textMuted, marginTop: 2 },
  statLabel: { color: glassColors.textMuted, fontSize: 10, marginBottom: 2 },
  statsRow: { color: glassColors.textMuted, fontSize: 12, marginTop: 8 },
  backfillBanner: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: "rgba(255,210,0,0.08)",
    borderRadius: 8,
    marginHorizontal: 12,
    marginTop: 4,
  },
  smartHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  smartDetails: { marginTop: 10 },
  smartPriceRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  smartPrice: { color: glassColors.greenDark, fontWeight: "700" },
  smartChain: { color: glassColors.textMuted },
  savings: { color: "#2E7D32", fontWeight: "600", marginTop: 4, fontSize: 12 },
  daysInfo: { color: glassColors.textMuted, marginTop: 4, fontSize: 12 },
  syncBar: { paddingHorizontal: 12, paddingTop: 8, paddingBottom: 4 },
  syncBtn: { backgroundColor: glassColors.greenDark, borderRadius: 8 },
  forceSyncBtn: { borderColor: glassColors.greenDark, borderRadius: 8 },
  snackbar: { backgroundColor: "#1a1a2e" },
});
