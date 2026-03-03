import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { Button, Modal, Portal, SegmentedButtons, Text } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { optimizeTrip, type TripOptimizationResult, type StoreTrip } from "../services/api";
import { glassCard, glassColors } from "../styles/glassStyles";

interface Props {
  visible: boolean;
  onDismiss: () => void;
}

export default function TripOptimizer({ visible, onDismiss }: Props) {
  const [tab, setTab] = useState<string>("single");

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["tripOptimize"],
    queryFn: optimizeTrip,
    enabled: visible,
  });

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={onDismiss}
        contentContainerStyle={styles.modal}
      >
        <View style={styles.header}>
          <MaterialCommunityIcons name="map-marker-path" size={24} color={glassColors.greenDark} />
          <Text variant="titleLarge" style={styles.title}>Ottimizza Spesa</Text>
        </View>

        <SegmentedButtons
          value={tab}
          onValueChange={setTab}
          buttons={[
            { value: "single", label: "Un negozio" },
            { value: "multi", label: "Piu' negozi" },
          ]}
          style={styles.tabs}
        />

        {isLoading ? (
          <Text style={styles.loading}>Analisi in corso...</Text>
        ) : !data ? (
          <Text style={styles.empty}>Aggiungi prodotti alla lista della spesa per ottimizzare.</Text>
        ) : (
          <ScrollView style={styles.content}>
            {tab === "single" ? (
              <AllStoresView data={data} />
            ) : (
              <MultiStoreView data={data} />
            )}
          </ScrollView>
        )}

        <Button mode="text" onPress={onDismiss} style={styles.closeButton}>
          Chiudi
        </Button>
      </Modal>
    </Portal>
  );
}

function StoreRow({ store, itemsTotal, isCheapest }: { store: StoreTrip; itemsTotal: number; isCheapest: boolean }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <View style={[styles.storeRow, isCheapest && styles.storeRowCheapest]}>
      <Pressable onPress={() => setExpanded(!expanded)} style={styles.storeRowHeader}>
        <MaterialCommunityIcons name="store" size={18} color={isCheapest ? glassColors.greenDark : "#555"} />
        <View style={styles.storeRowInfo}>
          <Text variant="titleSmall" style={[styles.storeRowName, isCheapest && styles.storeRowNameCheapest]}>
            {store.chain_name}
          </Text>
          <Text variant="labelSmall" style={styles.coverageBadge}>
            {store.items_covered}/{itemsTotal} prodotti
          </Text>
        </View>
        <Text variant="titleMedium" style={[styles.storeRowTotal, isCheapest && styles.storeRowTotalCheapest]}>
          {"\u20AC"}{Number(store.total).toFixed(2)}
        </Text>
        <MaterialCommunityIcons
          name={expanded ? "chevron-up" : "chevron-down"}
          size={20}
          color="#888"
        />
      </Pressable>
      {expanded && (
        <View style={styles.storeRowItems}>
          {store.items.map((item, i) => (
            <View key={i} style={styles.itemRow}>
              <Text variant="bodySmall" style={styles.itemName} numberOfLines={1}>
                {item.product_name}
              </Text>
              <Text variant="bodySmall" style={styles.itemPrice}>
                {"\u20AC"}{Number(item.offer_price).toFixed(2)}
              </Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function AllStoresView({ data }: { data: TripOptimizationResult }) {
  const stores = data.all_single_stores;

  if (stores.length === 0) {
    return <Text style={styles.empty}>Nessuna offerta trovata per i prodotti in lista.</Text>;
  }

  // Find cheapest store (by total, among those with max coverage)
  const maxCoverage = Math.max(...stores.map((s) => s.items_covered));
  const cheapestAmongBest = stores
    .filter((s) => s.items_covered === maxCoverage)
    .reduce((a, b) => (a.total < b.total ? a : b));

  return (
    <View>
      {data.items_not_covered > 0 && (
        <View style={styles.warningBanner}>
          <Text variant="bodySmall" style={styles.warningText}>
            {data.items_not_covered} prodott{data.items_not_covered === 1 ? "o" : "i"} senza offerte attive
          </Text>
        </View>
      )}

      {stores.map((store) => (
        <StoreRow
          key={store.chain_name}
          store={store}
          itemsTotal={data.items_total}
          isCheapest={store.chain_name === cheapestAmongBest.chain_name}
        />
      ))}

      {data.potential_savings > 0 && (
        <View style={styles.savingsHint}>
          <Text variant="bodySmall" style={styles.savingsText}>
            Con piu' negozi potresti risparmiare {"\u20AC"}{Number(data.potential_savings).toFixed(2)}
          </Text>
        </View>
      )}
    </View>
  );
}

function MultiStoreView({ data }: { data: TripOptimizationResult }) {
  if (data.multi_store_plan.length === 0) {
    return <Text style={styles.empty}>Nessuna offerta trovata per i prodotti in lista.</Text>;
  }

  return (
    <View>
      {data.potential_savings > 0 && (
        <View style={styles.savingsBanner}>
          <Text variant="titleSmall" style={styles.savingsBannerText}>
            Risparmio: {"\u20AC"}{Number(data.potential_savings).toFixed(2)}
          </Text>
        </View>
      )}

      <View style={styles.totalRow}>
        <Text variant="bodyMedium" style={styles.totalLabel}>Totale</Text>
        <Text variant="titleMedium" style={styles.totalPrice}>
          {"\u20AC"}{Number(data.multi_store_total).toFixed(2)}
        </Text>
      </View>

      {data.multi_store_plan.map((trip) => (
        <View key={trip.chain_name} style={styles.storeSection}>
          <View style={styles.storeHeader}>
            <MaterialCommunityIcons name="store" size={16} color={glassColors.greenDark} />
            <Text variant="titleSmall" style={styles.storeSectionName}>
              {trip.chain_name}
            </Text>
            <Text variant="bodySmall" style={styles.storeSubtotal}>
              {"\u20AC"}{Number(trip.total).toFixed(2)}
            </Text>
          </View>
          {trip.items.map((item, i) => (
            <View key={i} style={styles.itemRow}>
              <Text variant="bodySmall" style={styles.itemName} numberOfLines={1}>
                {item.product_name}
              </Text>
              <Text variant="bodySmall" style={styles.itemPrice}>
                {"\u20AC"}{Number(item.offer_price).toFixed(2)}
              </Text>
            </View>
          ))}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  modal: {
    backgroundColor: "white",
    margin: 16,
    borderRadius: 20,
    padding: 20,
    maxHeight: "85%",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 16,
  },
  title: { fontWeight: "600", color: glassColors.greenDark },
  tabs: { marginBottom: 16 },
  content: { maxHeight: 400 },
  loading: { textAlign: "center", color: "#888", paddingVertical: 20 },
  empty: { textAlign: "center", color: "#888", paddingVertical: 20 },
  closeButton: { marginTop: 12 },

  // All-stores ranked view
  storeRow: {
    marginBottom: 8,
    borderRadius: 12,
    backgroundColor: "rgba(0,0,0,0.02)",
    overflow: "hidden",
  },
  storeRowCheapest: {
    backgroundColor: "rgba(27,94,32,0.06)",
    borderWidth: 1,
    borderColor: "rgba(27,94,32,0.15)",
  },
  storeRowHeader: {
    flexDirection: "row",
    alignItems: "center",
    padding: 12,
    gap: 8,
  },
  storeRowInfo: {
    flex: 1,
  },
  storeRowName: {
    fontWeight: "600",
    color: "#333",
  },
  storeRowNameCheapest: {
    color: glassColors.greenDark,
  },
  coverageBadge: {
    color: "#888",
    marginTop: 1,
  },
  storeRowTotal: {
    fontWeight: "bold",
    color: "#333",
    marginRight: 4,
  },
  storeRowTotalCheapest: {
    color: glassColors.greenDark,
  },
  storeRowItems: {
    paddingHorizontal: 12,
    paddingBottom: 8,
    borderTopWidth: 1,
    borderTopColor: "rgba(0,0,0,0.05)",
  },
  warningBanner: {
    backgroundColor: "rgba(245,127,23,0.08)",
    borderRadius: 10,
    padding: 10,
    marginBottom: 12,
    alignItems: "center",
  },
  warningText: {
    color: "#E65100",
  },

  // Shared item styles
  itemRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 6,
    paddingHorizontal: 4,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(0,0,0,0.05)",
  },
  itemName: { flex: 1, marginRight: 8 },
  itemPrice: { fontWeight: "600" },

  // Savings
  savingsHint: {
    marginTop: 12,
    backgroundColor: "rgba(245,127,23,0.08)",
    borderRadius: 10,
    padding: 10,
  },
  savingsText: { color: "#E65100", textAlign: "center" },
  savingsBanner: {
    backgroundColor: "rgba(27,94,32,0.10)",
    borderRadius: 12,
    padding: 12,
    marginBottom: 12,
    alignItems: "center",
  },
  savingsBannerText: { color: glassColors.greenDark, fontWeight: "bold" },
  totalPrice: { fontWeight: "bold", color: glassColors.greenDark },
  totalRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
    paddingHorizontal: 4,
  },
  totalLabel: { color: "#666" },
  storeSection: {
    marginBottom: 14,
  },
  storeHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 4,
    paddingHorizontal: 4,
  },
  storeSectionName: { flex: 1, color: glassColors.greenDark, fontWeight: "600" },
  storeSubtotal: { color: "#666" },
});
