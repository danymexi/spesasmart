import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import {
  Button,
  Chip,
  Divider,
  IconButton,
  SegmentedButtons,
  Text,
  useTheme,
} from "react-native-paper";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { Snackbar } from "react-native-paper";
import {
  getPurchaseOrders,
  getPurchaseItems,
  getPurchaseHabits,
  getSmartList,
  fetchReceiptBlob,
  updatePurchaseOrder,
  addToWatchlist,
  syncSmartListToWatchlist,
  backfillReceiptProducts,
} from "../services/api";
import type {
  PurchaseOrderItem,
  PurchaseItemDetail,
  PurchaseHabit,
  SmartListItem,
} from "../services/api";
import { glassPanel, glassCard, glassColors } from "../styles/glassStyles";
import { useAppStore } from "../stores/useAppStore";

type Tab = "orders" | "habits" | "smart";

const CHAIN_OPTIONS = [
  { slug: "iperal", label: "Iperal" },
  { slug: "esselunga", label: "Esselunga" },
  { slug: "coop", label: "Coop" },
  { slug: "lidl", label: "Lidl" },
  { slug: "carrefour", label: "Carrefour" },
  { slug: "conad", label: "Conad" },
  { slug: "eurospin", label: "Eurospin" },
  { slug: "aldi", label: "Aldi" },
  { slug: "md-discount", label: "MD Discount" },
  { slug: "penny", label: "Penny Market" },
  { slug: "pam", label: "PAM Panorama" },
];

export default function PurchasesScreen() {
  const [tab, setTab] = useState<Tab>("orders");
  const { isLoggedIn } = useAppStore();

  if (!isLoggedIn) {
    return (
      <View style={styles.center}>
        <Text variant="bodyLarge" style={{ color: glassColors.textSecondary }}>
          Accedi per visualizzare il tuo storico acquisti.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.tabBar}>
        <SegmentedButtons
          value={tab}
          onValueChange={(v) => setTab(v as Tab)}
          buttons={[
            { value: "orders", label: "Ordini", icon: "receipt" },
            { value: "habits", label: "Abitudini", icon: "chart-timeline-variant" },
            { value: "smart", label: "Lista Smart", icon: "lightbulb-on" },
          ]}
          style={styles.segmented}
        />
      </View>

      {tab === "orders" && <OrdersTab />}
      {tab === "habits" && <HabitsTab />}
      {tab === "smart" && <SmartListTab />}
    </View>
  );
}

// ── Orders Tab ──────────────────────────────────────────────────────────────

function OrdersTab() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const { data: orders, isLoading } = useQuery({
    queryKey: ["purchaseOrders"],
    queryFn: () => getPurchaseOrders(),
  });

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={glassColors.greenMedium} />
      </View>
    );
  }

  if (!orders || orders.length === 0) {
    return (
      <View style={styles.center}>
        <Text variant="bodyLarge" style={{ color: glassColors.textSecondary }}>
          Nessun ordine trovato. Collega un account o carica scontrini in Impostazioni.
        </Text>
      </View>
    );
  }

  return (
    <FlatList
      data={orders}
      keyExtractor={(item) => item.id}
      contentContainerStyle={styles.listContent}
      renderItem={({ item }) => (
        <OrderCard
          order={item}
          isExpanded={expandedId === item.id}
          onToggle={() => setExpandedId(expandedId === item.id ? null : item.id)}
        />
      )}
    />
  );
}

function OrderCard({
  order,
  isExpanded,
  onToggle,
}: {
  order: PurchaseOrderItem;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <View style={styles.card}>
      <Pressable onPress={onToggle} style={styles.orderHeader}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Text variant="titleSmall" style={styles.orderChain}>
              {order.chain_slug.charAt(0).toUpperCase() + order.chain_slug.slice(1)}
            </Text>
            {order.source === "receipt_upload" && (
              <Chip compact style={styles.sourceChip} textStyle={styles.sourceChipText}>
                Scontrino
              </Chip>
            )}
          </View>
          <Text variant="bodySmall" style={styles.orderDate}>
            {new Date(order.order_date).toLocaleDateString("it-IT", {
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          </Text>
        </View>
        <View style={styles.orderRight}>
          {order.total_amount != null && (
            <Text variant="titleMedium" style={styles.orderTotal}>
              {order.total_amount.toFixed(2)} €
            </Text>
          )}
          <Text variant="bodySmall" style={styles.orderItems}>
            {order.items_count} prodotti
          </Text>
        </View>
        <IconButton
          icon={isExpanded ? "chevron-up" : "chevron-down"}
          size={20}
          iconColor={glassColors.textMuted}
          style={{ margin: 0 }}
        />
      </Pressable>
      {order.store_name && !isExpanded && (
        <Text variant="bodySmall" style={styles.storeName}>
          {order.store_name}
        </Text>
      )}
      {isExpanded && <OrderDetail order={order} />}
    </View>
  );
}

function OrderDetail({ order }: { order: PurchaseOrderItem }) {
  const queryClient = useQueryClient();
  const [editingChain, setEditingChain] = useState(false);
  const [selectedChain, setSelectedChain] = useState(order.chain_slug);

  // Fetch items
  const { data: items, isLoading: itemsLoading } = useQuery({
    queryKey: ["purchaseItems", order.id],
    queryFn: () => getPurchaseItems(order.id),
  });

  // Fetch receipt blob
  const {
    data: receiptData,
    isLoading: receiptLoading,
  } = useQuery({
    queryKey: ["receipt", order.id],
    queryFn: () => fetchReceiptBlob(order.id),
    enabled: order.has_receipt,
  });

  // Update chain mutation
  const updateMutation = useMutation({
    mutationFn: (chainSlug: string) => updatePurchaseOrder(order.id, { chain_slug: chainSlug }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["purchaseOrders"] });
      setEditingChain(false);
    },
  });

  return (
    <View style={styles.detailContainer}>
      <Divider style={styles.detailDivider} />

      {/* Store info */}
      {order.store_name && (
        <Text variant="bodySmall" style={styles.detailStore}>
          {order.store_name}
        </Text>
      )}

      {/* Chain editor */}
      <View style={styles.chainSection}>
        <Text variant="labelSmall" style={styles.detailLabel}>Supermercato</Text>
        {editingChain ? (
          <View>
            <View style={styles.chainChips}>
              {CHAIN_OPTIONS.map((c) => (
                <Chip
                  key={c.slug}
                  selected={selectedChain === c.slug}
                  onPress={() => setSelectedChain(c.slug)}
                  compact
                  style={[
                    styles.chainChip,
                    selectedChain === c.slug && styles.chainChipSelected,
                  ]}
                  textStyle={[
                    styles.chainChipText,
                    selectedChain === c.slug && styles.chainChipTextSelected,
                  ]}
                >
                  {c.label}
                </Chip>
              ))}
            </View>
            <View style={styles.chainActions}>
              <Button
                mode="contained"
                compact
                onPress={() => updateMutation.mutate(selectedChain)}
                loading={updateMutation.isPending}
                disabled={selectedChain === order.chain_slug}
                style={styles.saveBtn}
                labelStyle={{ fontSize: 12 }}
              >
                Salva
              </Button>
              <Button
                mode="text"
                compact
                onPress={() => { setEditingChain(false); setSelectedChain(order.chain_slug); }}
                labelStyle={{ fontSize: 12, color: glassColors.textMuted }}
              >
                Annulla
              </Button>
            </View>
          </View>
        ) : (
          <Pressable onPress={() => setEditingChain(true)} style={styles.chainDisplay}>
            <Text variant="bodyMedium" style={styles.chainDisplayText}>
              {order.chain_slug.charAt(0).toUpperCase() + order.chain_slug.slice(1)}
            </Text>
            <IconButton icon="pencil" size={16} iconColor={glassColors.textMuted} style={{ margin: 0 }} />
          </Pressable>
        )}
      </View>

      {/* Receipt viewer */}
      {order.has_receipt && (
        <View style={styles.receiptSection}>
          <Text variant="labelSmall" style={styles.detailLabel}>Scontrino</Text>
          {receiptLoading ? (
            <ActivityIndicator size="small" color={glassColors.greenMedium} style={{ marginVertical: 12 }} />
          ) : receiptData ? (
            receiptData.isPdf ? (
              <View style={styles.pdfContainer}>
                <iframe
                  src={receiptData.url}
                  style={{ width: "100%", height: 400, border: "none", borderRadius: 8 } as any}
                  title="Scontrino PDF"
                />
              </View>
            ) : (
              <Image
                source={{ uri: receiptData.url }}
                style={styles.receiptImage}
                resizeMode="contain"
              />
            )
          ) : null}
        </View>
      )}

      {/* Items list */}
      <View style={styles.itemsSection}>
        <Text variant="labelSmall" style={styles.detailLabel}>
          Prodotti ({order.items_count})
        </Text>
        {itemsLoading ? (
          <ActivityIndicator size="small" color={glassColors.greenMedium} style={{ marginVertical: 12 }} />
        ) : items && items.length > 0 ? (
          items.map((item, idx) => (
            <View key={item.id} style={styles.itemRow}>
              <View style={{ flex: 1 }}>
                <Text variant="bodySmall" style={styles.itemName}>
                  {item.external_name}
                </Text>
                {item.category && (
                  <Text variant="labelSmall" style={styles.itemCategory}>
                    {item.category}
                  </Text>
                )}
              </View>
              <View style={styles.itemPriceCol}>
                {item.quantity != null && item.quantity !== 1 && (
                  <Text variant="labelSmall" style={styles.itemQty}>
                    x{item.quantity}
                  </Text>
                )}
                {item.total_price != null && (
                  <Text variant="bodySmall" style={styles.itemPrice}>
                    {item.total_price.toFixed(2)} €
                  </Text>
                )}
              </View>
            </View>
          ))
        ) : (
          <Text variant="bodySmall" style={{ color: glassColors.textMuted, marginTop: 8 }}>
            Nessun prodotto trovato.
          </Text>
        )}
      </View>
    </View>
  );
}

// ── Habits Tab ──────────────────────────────────────────────────────────────

function HabitsTab() {
  const queryClient = useQueryClient();
  const [snackbar, setSnackbar] = useState("");
  const { data: habits, isLoading } = useQuery({
    queryKey: ["purchaseHabits"],
    queryFn: getPurchaseHabits,
  });

  const backfillMutation = useMutation({
    mutationFn: backfillReceiptProducts,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["purchaseHabits"] });
      queryClient.invalidateQueries({ queryKey: ["smartList"] });
      setSnackbar(`Collegati ${data.matched}/${data.total} prodotti al catalogo`);
    },
    onError: () => setSnackbar("Errore durante il collegamento prodotti"),
  });

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={glassColors.greenMedium} />
      </View>
    );
  }

  if (!habits || habits.length === 0) {
    return (
      <View style={styles.center}>
        <Text variant="bodyLarge" style={{ color: glassColors.textSecondary, textAlign: "center", marginBottom: 12 }}>
          Nessuna abitudine rilevata.
        </Text>
        <Text variant="bodySmall" style={{ color: glassColors.textSecondary, textAlign: "center", marginBottom: 16, paddingHorizontal: 24 }}>
          Servono almeno 2 acquisti dello stesso prodotto in date diverse. Prova a collegare i prodotti al catalogo:
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

  return (
    <FlatList
      data={habits}
      keyExtractor={(item) => item.product_id || item.product_name}
      contentContainerStyle={styles.listContent}
      renderItem={({ item }) => (
        <View style={styles.card}>
          <Text variant="titleSmall" style={styles.habitName}>
            {item.product_name}
          </Text>
          {item.brand && (
            <Text variant="bodySmall" style={styles.habitBrand}>
              {item.brand}
            </Text>
          )}
          <View style={styles.habitStats}>
            <View style={styles.habitStat}>
              <Text variant="labelSmall" style={styles.statLabel}>
                Acquisti
              </Text>
              <Text variant="bodyMedium" style={styles.statValue}>
                {item.total_purchases}
              </Text>
            </View>
            <View style={styles.habitStat}>
              <Text variant="labelSmall" style={styles.statLabel}>
                Ogni
              </Text>
              <Text variant="bodyMedium" style={styles.statValue}>
                {item.avg_interval_days} gg
              </Text>
            </View>
            {item.avg_price != null && (
              <View style={styles.habitStat}>
                <Text variant="labelSmall" style={styles.statLabel}>
                  Prezzo medio
                </Text>
                <Text variant="bodyMedium" style={styles.statValue}>
                  {item.avg_price.toFixed(2)}
                </Text>
              </View>
            )}
            {item.next_purchase_predicted && (
              <View style={styles.habitStat}>
                <Text variant="labelSmall" style={styles.statLabel}>
                  Prossimo
                </Text>
                <Text variant="bodyMedium" style={styles.statValue}>
                  {new Date(item.next_purchase_predicted).toLocaleDateString("it-IT", {
                    day: "numeric",
                    month: "short",
                  })}
                </Text>
              </View>
            )}
          </View>
        </View>
      )}
    />
  );
}

// ── Smart List Tab ──────────────────────────────────────────────────────────

function SmartListTab() {
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
      queryClient.invalidateQueries({ queryKey: ["purchaseHabits"] });
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
          Nessun suggerimento disponibile.
        </Text>
        <Text variant="bodySmall" style={{ color: glassColors.textSecondary, textAlign: "center", marginBottom: 16, paddingHorizontal: 24 }}>
          Servono almeno 2 scontrini con lo stesso prodotto. Prova a collegare i prodotti degli scontrini al catalogo:
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

  const urgencyColor = {
    alta: "#C62828",
    media: "#EF6C00",
    bassa: "#2E7D32",
  };

  const notInWatchlist = items.filter((i) => !i.in_watchlist && i.product_id !== null);

  return (
    <View style={{ flex: 1 }}>
      {notInWatchlist.length > 0 && (
        <View style={styles.syncBar}>
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
        </View>
      )}
      <FlatList
        data={items}
        keyExtractor={(item) => item.product_id || item.product_name}
        contentContainerStyle={styles.listContent}
        renderItem={({ item }) => (
          <View style={styles.card}>
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
              <Chip
                compact
                style={{
                  backgroundColor: `${urgencyColor[item.urgency as keyof typeof urgencyColor]}15`,
                }}
                textStyle={{
                  color: urgencyColor[item.urgency as keyof typeof urgencyColor],
                  fontSize: 11,
                  fontWeight: "700",
                }}
              >
                {item.urgency.toUpperCase()}
              </Chip>
            </View>

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
              <Text variant="bodySmall" style={styles.daysInfo}>
                {item.days_until_due < 0
                  ? `Scaduto da ${Math.abs(item.days_until_due)} giorni`
                  : item.days_until_due === 0
                  ? "Da comprare oggi"
                  : `Tra ${item.days_until_due} giorni`}
              </Text>
            </View>
          </View>
        )}
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
  container: { flex: 1, backgroundColor: "transparent" },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  tabBar: { paddingHorizontal: 12, paddingTop: 12, paddingBottom: 4 },
  segmented: { borderRadius: 16 },
  listContent: { padding: 12, paddingBottom: 100 },
  card: {
    ...(glassCard as object),
    padding: 16,
    marginBottom: 10,
  } as any,

  // Orders
  orderHeader: { flexDirection: "row", alignItems: "center" },
  orderChain: { color: glassColors.greenDark, fontWeight: "700" },
  orderDate: { color: glassColors.textMuted, marginTop: 2 },
  orderRight: { alignItems: "flex-end", marginRight: 4 },
  orderTotal: { color: glassColors.textPrimary, fontWeight: "700" },
  orderItems: { color: glassColors.textMuted, marginTop: 2 },
  storeName: { color: glassColors.textMuted, marginTop: 6, fontSize: 12 },
  sourceChip: { backgroundColor: "rgba(76,175,80,0.12)", height: 22 },
  sourceChipText: { fontSize: 10, color: glassColors.greenDark },

  // Order detail
  detailContainer: { marginTop: 4 },
  detailDivider: { backgroundColor: "rgba(255,255,255,0.08)", marginBottom: 12 },
  detailStore: { color: glassColors.textMuted, fontSize: 12, marginBottom: 8 },
  detailLabel: { color: glassColors.textMuted, fontSize: 10, marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 },

  // Chain editor
  chainSection: { marginBottom: 12 },
  chainChips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chainChip: { backgroundColor: "rgba(255,255,255,0.06)" },
  chainChipSelected: { backgroundColor: "rgba(76,175,80,0.2)" },
  chainChipText: { fontSize: 12, color: glassColors.textSecondary },
  chainChipTextSelected: { color: glassColors.greenDark, fontWeight: "600" },
  chainActions: { flexDirection: "row", alignItems: "center", marginTop: 8, gap: 8 },
  saveBtn: { backgroundColor: glassColors.greenDark, borderRadius: 8 },
  chainDisplay: { flexDirection: "row", alignItems: "center" },
  chainDisplayText: { color: glassColors.textPrimary, fontWeight: "600" },

  // Receipt viewer
  receiptSection: { marginBottom: 12 },
  pdfContainer: { borderRadius: 8, overflow: "hidden", marginTop: 4 },
  receiptImage: { width: "100%" as any, height: 300, borderRadius: 8, marginTop: 4, backgroundColor: "rgba(255,255,255,0.04)" },

  // Items list
  itemsSection: { marginBottom: 4 },
  itemRow: { flexDirection: "row", alignItems: "center", paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "rgba(255,255,255,0.06)" },
  itemName: { color: glassColors.textPrimary, fontSize: 13 },
  itemCategory: { color: glassColors.textMuted, fontSize: 10, marginTop: 1 },
  itemPriceCol: { alignItems: "flex-end" },
  itemQty: { color: glassColors.textMuted, fontSize: 10 },
  itemPrice: { color: glassColors.greenDark, fontWeight: "600", fontSize: 13 },

  // Habits
  habitName: { color: glassColors.textPrimary, fontWeight: "600" },
  habitBrand: { color: glassColors.textMuted, marginTop: 2 },
  habitStats: { flexDirection: "row", marginTop: 12, gap: 16 },
  habitStat: { alignItems: "center" },
  statLabel: { color: glassColors.textMuted, fontSize: 10, marginBottom: 2 },
  statValue: { color: glassColors.greenDark, fontWeight: "600" },

  // Smart list
  smartHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  smartDetails: { marginTop: 10 },
  smartPriceRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  smartPrice: { color: glassColors.greenDark, fontWeight: "700" },
  smartChain: { color: glassColors.textMuted },
  savings: { color: "#2E7D32", fontWeight: "600", marginTop: 4, fontSize: 12 },
  daysInfo: { color: glassColors.textMuted, marginTop: 4, fontSize: 12 },

  // Sync bar
  syncBar: { paddingHorizontal: 12, paddingTop: 8, paddingBottom: 4 },
  syncBtn: { backgroundColor: glassColors.greenDark, borderRadius: 8 },
  snackbar: { backgroundColor: "#1a1a2e" },
});
