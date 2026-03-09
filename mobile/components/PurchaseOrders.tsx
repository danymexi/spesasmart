import { useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  StyleSheet,
  View,
} from "react-native";
import {
  Button,
  Chip,
  Divider,
  IconButton,
  Text,
} from "react-native-paper";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  getPurchaseOrders,
  getPurchaseItems,
  fetchReceiptBlob,
  updatePurchaseOrder,
} from "../services/api";
import type { PurchaseOrderItem } from "../services/api";
import { glassCard, glassColors } from "../styles/glassStyles";

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

export default function PurchaseOrders() {
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

  const { data: items, isLoading: itemsLoading } = useQuery({
    queryKey: ["purchaseItems", order.id],
    queryFn: () => getPurchaseItems(order.id),
  });

  const {
    data: receiptData,
    isLoading: receiptLoading,
  } = useQuery({
    queryKey: ["receipt", order.id],
    queryFn: () => fetchReceiptBlob(order.id),
    enabled: order.has_receipt,
  });

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

      {order.store_name && (
        <Text variant="bodySmall" style={styles.detailStore}>
          {order.store_name}
        </Text>
      )}

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

      <View style={styles.itemsSection}>
        <Text variant="labelSmall" style={styles.detailLabel}>
          Prodotti ({order.items_count})
        </Text>
        {itemsLoading ? (
          <ActivityIndicator size="small" color={glassColors.greenMedium} style={{ marginVertical: 12 }} />
        ) : items && items.length > 0 ? (
          items.map((item) => (
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

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  listContent: { padding: 12, paddingBottom: 100 },
  card: {
    ...(glassCard as object),
    padding: 16,
    marginBottom: 10,
  } as any,
  orderHeader: { flexDirection: "row", alignItems: "center" },
  orderChain: { color: glassColors.greenDark, fontWeight: "700" },
  orderDate: { color: glassColors.textMuted, marginTop: 2 },
  orderRight: { alignItems: "flex-end", marginRight: 4 },
  orderTotal: { color: glassColors.textPrimary, fontWeight: "700" },
  orderItems: { color: glassColors.textMuted, marginTop: 2 },
  storeName: { color: glassColors.textMuted, marginTop: 6, fontSize: 12 },
  sourceChip: { backgroundColor: "rgba(76,175,80,0.12)", height: 22 },
  sourceChipText: { fontSize: 10, color: glassColors.greenDark },
  detailContainer: { marginTop: 4 },
  detailDivider: { backgroundColor: "rgba(255,255,255,0.08)", marginBottom: 12 },
  detailStore: { color: glassColors.textMuted, fontSize: 12, marginBottom: 8 },
  detailLabel: { color: glassColors.textMuted, fontSize: 10, marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 },
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
  receiptSection: { marginBottom: 12 },
  pdfContainer: { borderRadius: 8, overflow: "hidden", marginTop: 4 },
  receiptImage: { width: "100%" as any, height: 300, borderRadius: 8, marginTop: 4, backgroundColor: "rgba(255,255,255,0.04)" },
  itemsSection: { marginBottom: 4 },
  itemRow: { flexDirection: "row", alignItems: "center", paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "rgba(255,255,255,0.06)" },
  itemName: { color: glassColors.textPrimary, fontSize: 13 },
  itemCategory: { color: glassColors.textMuted, fontSize: 10, marginTop: 1 },
  itemPriceCol: { alignItems: "flex-end" },
  itemQty: { color: glassColors.textMuted, fontSize: 10 },
  itemPrice: { color: glassColors.greenDark, fontWeight: "600", fontSize: 13 },
});
