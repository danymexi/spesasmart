import { useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, View } from "react-native";
import { Button, IconButton, SegmentedButtons, Snackbar, Text, useTheme } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import {
  getWatchlist,
  removeFromWatchlist,
  addToShoppingList,
  bulkAddToShoppingList,
  createShoppingList,
  deleteShoppingList,
  duplicateShoppingList,
  updateShoppingList,
  shareShoppingList,
  type ShoppingListMeta,
} from "../../services/api";
import { useAppStore } from "../../stores/useAppStore";
import PriceIndicator from "../../components/PriceIndicator";
import ShoppingList from "../../components/ShoppingList";
import ListPicker from "../../components/ListPicker";
import ListSettingsModal from "../../components/ListSettingsModal";
import ShareListModal from "../../components/ShareListModal";
import PurchaseOrders from "../../components/PurchaseOrders";
import PurchaseProducts from "../../components/PurchaseProducts";
import { glassCard, glassColors, alertBadgeGlass } from "../../styles/glassStyles";
import { useGlassTheme } from "../../styles/useGlassTheme";

type TabValue = "watchlist" | "shopping" | "history";
type HistorySubTab = "orders" | "products";

export default function WatchlistScreen() {
  const theme = useTheme();
  const glass = useGlassTheme();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const activeListId = useAppStore((s) => s.activeListId);
  const setActiveListId = useAppStore((s) => s.setActiveListId);
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabValue>("watchlist");
  const [showCreateList, setShowCreateList] = useState(false);
  const [shareList, setShareList] = useState<ShoppingListMeta | null>(null);
  const [snackbar, setSnackbar] = useState("");
  const [historySubTab, setHistorySubTab] = useState<HistorySubTab>("orders");

  const {
    data: items,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => getWatchlist(),
    enabled: isLoggedIn,
  });

  const removeMutation = useMutation({
    mutationFn: ({ productId }: { productId: string }) =>
      removeFromWatchlist(productId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  const addToListMutation = useMutation({
    mutationFn: ({ productId }: { productId: string }) =>
      addToShoppingList({ product_id: productId, list_id: activeListId ?? undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingLists"] });
    },
  });

  const addAllToListMutation = useMutation({
    mutationFn: (productIds: string[]) =>
      bulkAddToShoppingList(
        productIds.map((id) => ({ product_id: id })),
        activeListId ?? undefined,
      ),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingLists"] });
      setSnackbar(`${data.added} prodotti aggiunti alla spesa`);
    },
  });

  const createListMutation = useMutation({
    mutationFn: createShoppingList,
    onSuccess: (newList) => {
      queryClient.invalidateQueries({ queryKey: ["shoppingLists"] });
      setActiveListId(newList.id);
      setShowCreateList(false);
    },
  });

  return (
    <View style={styles.container}>
      {/* Tab switcher */}
      <View style={styles.tabRow}>
        <SegmentedButtons
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as TabValue)}
          buttons={[
            { value: "watchlist", label: "Watchlist", icon: "star" },
            { value: "shopping", label: "Spesa", icon: "cart" },
            { value: "history", label: "Storico", icon: "history" },
          ]}
          style={styles.segmented}
        />
      </View>

      {activeTab === "shopping" ? (
        <View style={{ flex: 1 }}>
          <ListPicker onCreateList={() => setShowCreateList(true)} />
          <ShoppingList listId={activeListId ?? undefined} />
          <ListSettingsModal
            visible={showCreateList}
            onDismiss={() => setShowCreateList(false)}
            onSave={(data) => createListMutation.mutate({
              name: data.name,
              emoji: data.emoji ?? undefined,
              color: data.color ?? undefined,
            })}
          />
        </View>
      ) : activeTab === "history" ? (
        <View style={{ flex: 1 }}>
          <View style={styles.subTabRow}>
            <SegmentedButtons
              value={historySubTab}
              onValueChange={(v) => setHistorySubTab(v as HistorySubTab)}
              buttons={[
                { value: "orders", label: "Ordini", icon: "receipt" },
                { value: "products", label: "I miei prodotti", icon: "basket" },
              ]}
              density="small"
              style={styles.subSegmented}
            />
          </View>
          {historySubTab === "orders" ? <PurchaseOrders /> : <PurchaseProducts />}
        </View>
      ) : (
      <>
        {items && items.length > 0 && (
          <View style={styles.bulkBar}>
            <Button
              mode="contained"
              icon="cart-arrow-down"
              compact
              onPress={() => addAllToListMutation.mutate(items.map((i) => i.product_id))}
              loading={addAllToListMutation.isPending}
              disabled={addAllToListMutation.isPending}
              style={styles.bulkBtn}
              labelStyle={{ fontSize: 12 }}
            >
              Aggiungi tutto alla spesa ({items.length})
            </Button>
          </View>
        )}
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} />}
          renderItem={({ item }) => {
            const hasOffer = item.best_current_price != null;

            return (
              <Pressable
                style={[styles.card, glass.card, { padding: 12, marginHorizontal: 12, marginBottom: 8 }]}
                onPress={() => router.push(`/product/${item.product_id}`)}
              >
                <View style={styles.cardContent}>
                  <View style={styles.infoSection}>
                    <Text
                      variant="titleMedium"
                      numberOfLines={2}
                      style={{ color: glass.colors.textPrimary, fontWeight: "600" }}
                    >
                      {item.product_name}
                    </Text>
                    {item.brand && (
                      <Text variant="bodySmall" style={{ color: glass.colors.textSecondary, marginTop: 2 }}>
                        {item.brand}
                      </Text>
                    )}
                    {item.target_price && (
                      <Text variant="labelSmall" style={{ color: glass.colors.textMuted, marginTop: 4 }}>
                        Prezzo target: {"\u20AC"}{Number(item.target_price).toFixed(2)}
                      </Text>
                    )}
                  </View>
                  <View style={styles.priceSection}>
                    {hasOffer ? (
                      <>
                        <Text
                          variant="headlineSmall"
                          style={{ color: theme.colors.primary, fontWeight: "bold" }}
                        >
                          {"\u20AC"}{Number(item.best_current_price).toFixed(2)}
                        </Text>
                        <Text variant="labelSmall" style={{ color: glass.colors.textSecondary, marginTop: 2 }}>
                          {item.best_chain}
                        </Text>
                        {item.target_price &&
                          Number(item.best_current_price) <= Number(item.target_price) && (
                            <View style={[{ marginTop: 4 }, glass.alertBadge]}>
                              <Text style={{ color: glass.colors.primaryMuted, fontSize: 10, fontWeight: "bold" }}>SOTTO TARGET</Text>
                            </View>
                          )}
                      </>
                    ) : (
                      <Text variant="bodySmall" style={{ color: glass.colors.textMuted }}>
                        Nessuna offerta
                      </Text>
                    )}
                  </View>
                  <View style={styles.actionButtons}>
                    <IconButton
                      icon="cart-plus"
                      size={20}
                      onPress={(e) => {
                        e.stopPropagation?.();
                        addToListMutation.mutate({ productId: item.product_id });
                      }}
                    />
                    <IconButton
                      icon="delete-outline"
                      size={20}
                      onPress={(e) => {
                        e.stopPropagation?.();
                        removeMutation.mutate({ productId: item.product_id });
                      }}
                    />
                  </View>
                </View>
              </Pressable>
            );
          }}
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text variant="titleMedium" style={[styles.emptyTitle, { color: glass.colors.textPrimary }]}>
                Lista vuota
              </Text>
              <Text variant="bodyMedium" style={[styles.emptyText, { color: glass.colors.textSecondary }]}>
                Cerca prodotti e aggiungili alla tua lista per monitorare i prezzi.
              </Text>
              <Button mode="contained" onPress={() => router.push("/(tabs)/search")}>
                Sfoglia il Catalogo
              </Button>
            </View>
          }
          contentContainerStyle={items?.length === 0 ? styles.emptyContainer : styles.listContent}
        />
        <Snackbar visible={!!snackbar} onDismiss={() => setSnackbar("")} duration={3000} style={{ backgroundColor: "#1a1a2e" }}>
          {snackbar}
        </Snackbar>
      </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  centered: { flex: 1, justifyContent: "center", alignItems: "center", padding: 20 },
  emptyContainer: { flexGrow: 1 },
  tabRow: {
    paddingHorizontal: 12,
    paddingTop: 12,
    paddingBottom: 4,
  },
  segmented: {},
  subTabRow: {
    paddingHorizontal: 16,
    paddingTop: 4,
    paddingBottom: 4,
  },
  subSegmented: {
    borderRadius: 12,
  },
  card: {
    marginHorizontal: 12,
    marginBottom: 8,
    padding: 12,
    ...glassCard,
  } as any,
  cardContent: { flexDirection: "row", alignItems: "center" },
  infoSection: { flex: 1 },
  productName: { color: "#1a1a1a", fontWeight: "600" },
  brand: { color: "#444", marginTop: 2 },
  targetPrice: { color: "#666", marginTop: 4 },
  priceSection: { alignItems: "flex-end", marginRight: 4 },
  chainText: { color: "#555", marginTop: 2 },
  actionButtons: { flexDirection: "column", marginLeft: 4 },
  alertBadge: {
    marginTop: 4,
    ...alertBadgeGlass,
  },
  alertText: { color: glassColors.greenMedium, fontSize: 10, fontWeight: "bold" },
  emptyTitle: { marginBottom: 8, color: "#1a1a1a" },
  emptyText: { color: "#555", textAlign: "center", marginBottom: 16 },
  bulkBar: { paddingHorizontal: 12, paddingTop: 8, paddingBottom: 4 },
  bulkBtn: { backgroundColor: glassColors.greenDark, borderRadius: 8 },
  listContent: { paddingTop: 12, paddingBottom: 96 },
});
