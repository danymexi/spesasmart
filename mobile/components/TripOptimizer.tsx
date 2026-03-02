import { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { Button, Modal, Portal, SegmentedButtons, Text } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { optimizeTrip, type TripOptimizationResult } from "../services/api";
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
              <SingleStoreView data={data} />
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

function SingleStoreView({ data }: { data: TripOptimizationResult }) {
  if (!data.single_store_best) {
    return <Text style={styles.empty}>Nessuna offerta trovata per i prodotti in lista.</Text>;
  }

  const { single_store_best, single_store_total } = data;

  return (
    <View>
      <View style={styles.summaryCard}>
        <MaterialCommunityIcons name="store" size={20} color={glassColors.greenDark} />
        <Text variant="titleMedium" style={styles.storeName}>
          {single_store_best.chain_name}
        </Text>
        <Text variant="titleLarge" style={styles.totalPrice}>
          {"\u20AC"}{Number(single_store_total).toFixed(2)}
        </Text>
      </View>

      {single_store_best.items.map((item, i) => (
        <View key={i} style={styles.itemRow}>
          <Text variant="bodyMedium" style={styles.itemName} numberOfLines={1}>
            {item.product_name}
          </Text>
          <Text variant="bodyMedium" style={styles.itemPrice}>
            {"\u20AC"}{Number(item.offer_price).toFixed(2)}
          </Text>
        </View>
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
      {/* Total savings banner */}
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
  summaryCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "rgba(27,94,32,0.06)",
    borderRadius: 14,
    padding: 14,
    marginBottom: 12,
  },
  storeName: { flex: 1, fontWeight: "600", color: glassColors.greenDark },
  totalPrice: { fontWeight: "bold", color: glassColors.greenDark },
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
