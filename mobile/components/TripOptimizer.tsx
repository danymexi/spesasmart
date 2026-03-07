import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { Button, Chip, Modal, Portal, SegmentedButtons, Text, TextInput } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { optimizeTrip, type TripOptimizationResult, type StoreTrip, type OptimizeParams } from "../services/api";
import { glassCard, glassColors } from "../styles/glassStyles";

interface Props {
  visible: boolean;
  onDismiss: () => void;
  listId?: string;
}

const MAX_STORES_OPTIONS = [1, 2, 3, 4, 5];

export default function TripOptimizer({ visible, onDismiss, listId }: Props) {
  const [tab, setTab] = useState<string>("single");
  const [showSettings, setShowSettings] = useState(false);
  const [maxStores, setMaxStores] = useState(3);
  const [radiusKm, setRadiusKm] = useState("15");
  const [travelCost, setTravelCost] = useState("2.00");

  const params: OptimizeParams = {
    list_id: listId,
    max_stores: maxStores,
    radius_km: parseFloat(radiusKm) || 15,
    travel_cost_per_store: parseFloat(travelCost) || 2,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["tripOptimize", listId, maxStores, radiusKm, travelCost],
    queryFn: () => optimizeTrip(params),
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
          <Pressable onPress={() => setShowSettings(!showSettings)} style={styles.settingsBtn}>
            <MaterialCommunityIcons
              name={showSettings ? "chevron-up" : "tune-variant"}
              size={22}
              color={glassColors.greenDark}
            />
          </Pressable>
        </View>

        {/* Collapsible settings panel */}
        {showSettings && (
          <View style={styles.settingsPanel}>
            <Text variant="labelMedium" style={styles.settingsLabel}>Max negozi</Text>
            <View style={styles.chipRow}>
              {MAX_STORES_OPTIONS.map((n) => (
                <Chip
                  key={n}
                  selected={maxStores === n}
                  onPress={() => setMaxStores(n)}
                  style={[styles.chip, maxStores === n && styles.chipSelected]}
                  compact
                >
                  {n}
                </Chip>
              ))}
            </View>

            <View style={styles.settingsRow}>
              <View style={styles.settingsField}>
                <Text variant="labelMedium" style={styles.settingsLabel}>Raggio (km)</Text>
                <TextInput
                  value={radiusKm}
                  onChangeText={setRadiusKm}
                  keyboardType="numeric"
                  mode="outlined"
                  dense
                  style={styles.settingsInput}
                />
              </View>
              <View style={styles.settingsField}>
                <Text variant="labelMedium" style={styles.settingsLabel}>Costo viaggio ({"\u20AC"})</Text>
                <TextInput
                  value={travelCost}
                  onChangeText={setTravelCost}
                  keyboardType="numeric"
                  mode="outlined"
                  dense
                  style={styles.settingsInput}
                />
              </View>
            </View>
          </View>
        )}

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

            {/* Missing items section */}
            {data.missing_items.length > 0 && (
              <View style={styles.missingSection}>
                <Text variant="labelMedium" style={styles.missingSectionTitle}>
                  Prodotti senza offerte ({data.missing_items.length})
                </Text>
                {data.missing_items.map((item, i) => (
                  <Text key={i} variant="bodySmall" style={styles.missingItem}>
                    {item.search_term ? `${item.search_term} → ` : ""}{item.product_name}
                  </Text>
                ))}
              </View>
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
  const coveragePct = Math.round(store.coverage_pct * 100);

  return (
    <View style={[styles.storeRow, isCheapest && styles.storeRowCheapest]}>
      <Pressable onPress={() => setExpanded(!expanded)} style={styles.storeRowHeader}>
        <MaterialCommunityIcons name="store" size={18} color={isCheapest ? glassColors.greenDark : "#555"} />
        <View style={styles.storeRowInfo}>
          <Text variant="titleSmall" style={[styles.storeRowName, isCheapest && styles.storeRowNameCheapest]}>
            {store.chain_name}
          </Text>
          <View style={styles.badgeRow}>
            <Text variant="labelSmall" style={styles.coverageBadge}>
              {store.items_covered}/{itemsTotal} ({coveragePct}%)
            </Text>
            {store.distance_km != null && (
              <Text variant="labelSmall" style={styles.distanceBadge}>
                {store.distance_km} km
              </Text>
            )}
          </View>
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
              <View style={styles.itemNameColumn}>
                {item.search_term && (
                  <Text variant="labelSmall" style={styles.searchTermLabel} numberOfLines={1}>
                    {item.search_term}
                  </Text>
                )}
                <Text variant="bodySmall" style={styles.itemName} numberOfLines={1}>
                  {item.product_name}
                </Text>
              </View>
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
        <Text variant="bodyMedium" style={styles.totalLabel}>Totale prodotti</Text>
        <Text variant="titleMedium" style={styles.totalPrice}>
          {"\u20AC"}{Number(data.multi_store_total).toFixed(2)}
        </Text>
      </View>

      {data.travel_cost > 0 && (
        <View style={styles.totalRow}>
          <Text variant="bodyMedium" style={styles.totalLabel}>
            Costo viaggio ({data.multi_store_plan.length} negozi)
          </Text>
          <Text variant="bodyMedium" style={styles.travelCostText}>
            +{"\u20AC"}{Number(data.travel_cost).toFixed(2)}
          </Text>
        </View>
      )}

      {data.multi_store_plan.map((trip) => (
        <View key={trip.chain_name} style={styles.storeSection}>
          <View style={styles.storeHeader}>
            <MaterialCommunityIcons name="store" size={16} color={glassColors.greenDark} />
            <Text variant="titleSmall" style={styles.storeSectionName}>
              {trip.chain_name}
            </Text>
            {trip.distance_km != null && (
              <Text variant="labelSmall" style={styles.distanceBadge}>
                {trip.distance_km} km
              </Text>
            )}
            <Text variant="bodySmall" style={styles.storeSubtotal}>
              {"\u20AC"}{Number(trip.total).toFixed(2)}
            </Text>
          </View>
          {trip.items.map((item, i) => (
            <View key={i} style={styles.itemRow}>
              <View style={styles.itemNameColumn}>
                {item.search_term && (
                  <Text variant="labelSmall" style={styles.searchTermLabel} numberOfLines={1}>
                    {item.search_term}
                  </Text>
                )}
                <Text variant="bodySmall" style={styles.itemName} numberOfLines={1}>
                  {item.product_name}
                </Text>
              </View>
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
  title: { fontWeight: "600", color: glassColors.greenDark, flex: 1 },
  settingsBtn: {
    padding: 4,
  },
  tabs: { marginBottom: 16 },
  content: { maxHeight: 400 },
  loading: { textAlign: "center", color: "#888", paddingVertical: 20 },
  empty: { textAlign: "center", color: "#888", paddingVertical: 20 },
  closeButton: { marginTop: 12 },

  // Settings panel
  settingsPanel: {
    backgroundColor: "rgba(0,0,0,0.03)",
    borderRadius: 12,
    padding: 12,
    marginBottom: 12,
  },
  settingsLabel: { color: "#555", marginBottom: 4 },
  chipRow: { flexDirection: "row", gap: 6, marginBottom: 10 },
  chip: { backgroundColor: "rgba(0,0,0,0.04)" },
  chipSelected: { backgroundColor: glassColors.greenAccent },
  settingsRow: { flexDirection: "row", gap: 12 },
  settingsField: { flex: 1 },
  settingsInput: { backgroundColor: "white", height: 36 },

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
  badgeRow: { flexDirection: "row", gap: 8, marginTop: 1 },
  coverageBadge: {
    color: "#888",
  },
  distanceBadge: {
    color: "#888",
    fontSize: 11,
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

  // Missing items
  missingSection: {
    marginTop: 16,
    backgroundColor: "rgba(245,127,23,0.06)",
    borderRadius: 10,
    padding: 12,
  },
  missingSectionTitle: {
    color: "#E65100",
    fontWeight: "600",
    marginBottom: 6,
  },
  missingItem: {
    color: "#888",
    paddingVertical: 2,
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
  itemNameColumn: { flex: 1, marginRight: 8 },
  itemName: {},
  searchTermLabel: { color: "#999", fontSize: 10, marginBottom: 1 },
  itemPrice: { fontWeight: "600", alignSelf: "center" },

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
  travelCostText: { color: "#E65100", fontWeight: "600" },
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
