import { useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import {
  Button,
  Chip,
  Divider,
  List,
  SegmentedButtons,
  Text,
  useTheme,
} from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import {
  getPurchaseOrders,
  getPurchaseHabits,
  getSmartList,
} from "../services/api";
import type {
  PurchaseOrderItem,
  PurchaseHabit,
  SmartListItem,
} from "../services/api";
import { glassPanel, glassCard, glassColors } from "../styles/glassStyles";
import { useAppStore } from "../stores/useAppStore";

type Tab = "orders" | "habits" | "smart";

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
          Nessun ordine trovato. Collega un account in Impostazioni.
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
        <View style={styles.card}>
          <View style={styles.orderHeader}>
            <View style={{ flex: 1 }}>
              <Text variant="titleSmall" style={styles.orderChain}>
                {item.chain_slug.charAt(0).toUpperCase() + item.chain_slug.slice(1)}
              </Text>
              <Text variant="bodySmall" style={styles.orderDate}>
                {new Date(item.order_date).toLocaleDateString("it-IT", {
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}
              </Text>
            </View>
            <View style={styles.orderRight}>
              {item.total_amount != null && (
                <Text variant="titleMedium" style={styles.orderTotal}>
                  {item.total_amount.toFixed(2)}
                </Text>
              )}
              <Text variant="bodySmall" style={styles.orderItems}>
                {item.items_count} prodotti
              </Text>
            </View>
          </View>
          {item.store_name && (
            <Text variant="bodySmall" style={styles.storeName}>
              {item.store_name}
            </Text>
          )}
        </View>
      )}
    />
  );
}

// ── Habits Tab ──────────────────────────────────────────────────────────────

function HabitsTab() {
  const { data: habits, isLoading } = useQuery({
    queryKey: ["purchaseHabits"],
    queryFn: getPurchaseHabits,
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
        <Text variant="bodyLarge" style={{ color: glassColors.textSecondary }}>
          Servono almeno 2 acquisti di un prodotto per calcolare le abitudini.
        </Text>
      </View>
    );
  }

  return (
    <FlatList
      data={habits}
      keyExtractor={(item) => item.product_id}
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
  const { data: items, isLoading } = useQuery({
    queryKey: ["smartList"],
    queryFn: getSmartList,
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
        <Text variant="bodyLarge" style={{ color: glassColors.textSecondary }}>
          Nessun suggerimento disponibile. Sincronizza i tuoi ordini.
        </Text>
      </View>
    );
  }

  const urgencyColor = {
    alta: "#C62828",
    media: "#EF6C00",
    bassa: "#2E7D32",
  };

  return (
    <FlatList
      data={items}
      keyExtractor={(item) => item.product_id}
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
  orderHeader: { flexDirection: "row", justifyContent: "space-between" },
  orderChain: { color: glassColors.greenDark, fontWeight: "700" },
  orderDate: { color: glassColors.textMuted, marginTop: 2 },
  orderRight: { alignItems: "flex-end" },
  orderTotal: { color: glassColors.textPrimary, fontWeight: "700" },
  orderItems: { color: glassColors.textMuted, marginTop: 2 },
  storeName: { color: glassColors.textMuted, marginTop: 6, fontSize: 12 },

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
});
