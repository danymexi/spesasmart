import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { SegmentedButtons, Text } from "react-native-paper";
import { useAppStore } from "../stores/useAppStore";
import { glassColors } from "../styles/glassStyles";
import PurchaseOrders from "../components/PurchaseOrders";
import PurchaseProducts from "../components/PurchaseProducts";

type Tab = "orders" | "products";

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
            { value: "products", label: "I miei prodotti", icon: "basket" },
          ]}
          style={styles.segmented}
        />
      </View>

      {tab === "orders" && <PurchaseOrders />}
      {tab === "products" && <PurchaseProducts />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  tabBar: { paddingHorizontal: 12, paddingTop: 12, paddingBottom: 4 },
  segmented: { borderRadius: 16 },
});
