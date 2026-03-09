import { useCallback, useEffect, useMemo, useState } from "react";
import { Platform, Pressable, SafeAreaView, StyleSheet, View } from "react-native";
import { Button, IconButton, Text } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { router, useLocalSearchParams } from "expo-router";
import {
  getShoppingList,
  toggleShoppingItem,
  clearCheckedItems,
  type ShoppingListItem,
} from "../services/api";


export default function ShoppingModeScreen() {
  const params = useLocalSearchParams<{ listId?: string }>();
  const listId = params.listId || undefined;
  const queryClient = useQueryClient();
  const [celebration, setCelebration] = useState(false);

  // Keep screen awake (web: via wakeLock API)
  useEffect(() => {
    if (Platform.OS !== "web") return;
    let wakeLock: any = null;
    (async () => {
      try {
        wakeLock = await (navigator as any).wakeLock?.request?.("screen");
      } catch {
        // silent — not supported in all browsers
      }
    })();
    return () => {
      wakeLock?.release?.();
    };
  }, []);

  const { data: items, refetch } = useQuery({
    queryKey: ["shoppingList", listId],
    queryFn: () => getShoppingList(listId),
    refetchInterval: 5000,
  });

  const toggleMutation = useMutation({
    mutationFn: toggleShoppingItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingLists"] });
    },
  });

  const unchecked = useMemo(() => (items || []).filter((i) => !i.checked), [items]);
  const checked = useMemo(() => (items || []).filter((i) => i.checked), [items]);
  const total = (items || []).length;
  const checkedCount = checked.length;
  const progress = total > 0 ? checkedCount / total : 0;

  // Estimated total from unchecked items with prices
  const estimatedTotal = useMemo(
    () =>
      unchecked.reduce(
        (sum, item) =>
          sum + (item.offer_price ? item.offer_price * item.quantity : 0),
        0
      ),
    [unchecked]
  );

  // Celebration when all checked
  useEffect(() => {
    if (total > 0 && checkedCount === total && !celebration) {
      setCelebration(true);
    }
  }, [total, checkedCount, celebration]);

  const handleToggle = useCallback(
    (id: string) => toggleMutation.mutate(id),
    [toggleMutation]
  );

  const displayName = (item: ShoppingListItem) =>
    item.custom_name || item.product_name || "Articolo";

  return (
    <SafeAreaView style={styles.container}>
      {/* Header bar */}
      <View style={styles.header}>
        <IconButton
          icon="close"
          size={28}
          iconColor="#fff"
          onPress={() => router.back()}
        />
        <Text style={styles.headerTitle}>Spesa in corso</Text>
        <View style={{ width: 48 }} />
      </View>

      {/* Progress bar */}
      <View style={styles.progressContainer}>
        <View style={[styles.progressBar, { width: `${progress * 100}%` }]} />
      </View>
      <Text style={styles.progressText}>
        {checkedCount} / {total} articoli
      </Text>
      {estimatedTotal > 0 && (
        <Text style={styles.estimatedTotal}>
          Totale stimato: {"\u20AC"}{estimatedTotal.toFixed(2)}
        </Text>
      )}

      {/* Celebration overlay */}
      {celebration && (
        <View style={styles.celebrationOverlay}>
          <Text style={styles.celebrationEmoji}>{"\uD83C\uDF89"}</Text>
          <Text style={styles.celebrationText}>Spesa completata!</Text>
          <Button
            mode="contained"
            onPress={() => router.back()}
            style={styles.celebrationBtn}
            buttonColor="#2563EB"
          >
            Torna alla lista
          </Button>
        </View>
      )}

      {/* Item list */}
      {!celebration && (
        <View style={styles.listContainer}>
          {unchecked.map((item) => (
            <Pressable
              key={item.id}
              style={styles.itemRow}
              onPress={() => handleToggle(item.id)}
            >
              <View style={styles.checkbox} />
              <View style={styles.itemInfo}>
                <Text style={styles.itemName} numberOfLines={2}>
                  {displayName(item)}
                </Text>
                {item.offer_price != null && (
                  <Text style={styles.itemPrice}>
                    {"\u20AC"}{item.offer_price.toFixed(2)}{item.chain_name ? ` - ${item.chain_name}` : ""}
                  </Text>
                )}
                {item.quantity > 1 && (
                  <Text style={styles.itemQty}>
                    x{item.quantity} {item.unit ?? ""}
                  </Text>
                )}
              </View>
            </Pressable>
          ))}

          {checked.length > 0 && (
            <>
              <View style={styles.divider} />
              <Text style={styles.doneLabel}>Completati</Text>
              {checked.map((item) => (
                <Pressable
                  key={item.id}
                  style={[styles.itemRow, styles.itemChecked]}
                  onPress={() => handleToggle(item.id)}
                >
                  <View style={[styles.checkbox, styles.checkboxChecked]}>
                    <Text style={styles.checkmark}>{"\u2713"}</Text>
                  </View>
                  <Text style={styles.itemNameChecked} numberOfLines={1}>
                    {displayName(item)}
                  </Text>
                </Pressable>
              ))}
            </>
          )}
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#121212",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 4,
    paddingTop: Platform.OS === "web" ? 12 : 0,
  },
  headerTitle: {
    color: "#fff",
    fontSize: 18,
    fontWeight: "700",
  },
  progressContainer: {
    height: 6,
    backgroundColor: "rgba(255,255,255,0.15)",
    borderRadius: 3,
    marginHorizontal: 20,
    marginTop: 4,
    overflow: "hidden",
  },
  progressBar: {
    height: 6,
    backgroundColor: "#60A5FA",
    borderRadius: 3,
  },
  progressText: {
    color: "rgba(255,255,255,0.6)",
    fontSize: 13,
    textAlign: "center",
    marginTop: 6,
    marginBottom: 12,
  },
  listContainer: {
    flex: 1,
    paddingHorizontal: 16,
    ...(Platform.OS === "web" ? { overflowY: "auto" } : {}) as any,
  },
  itemRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 14,
    paddingHorizontal: 12,
    borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.06)",
    marginBottom: 8,
    gap: 14,
  },
  itemChecked: {
    opacity: 0.5,
    backgroundColor: "rgba(255,255,255,0.03)",
  },
  checkbox: {
    width: 48,
    height: 48,
    borderRadius: 14,
    borderWidth: 2,
    borderColor: "rgba(255,255,255,0.35)",
    justifyContent: "center",
    alignItems: "center",
  },
  checkboxChecked: {
    backgroundColor: "#60A5FA",
    borderColor: "#60A5FA",
  },
  checkmark: {
    color: "#fff",
    fontSize: 22,
    fontWeight: "bold",
  },
  itemInfo: {
    flex: 1,
  },
  itemName: {
    color: "#E8E8E8",
    fontSize: 18,
    fontWeight: "600",
  },
  itemNameChecked: {
    color: "rgba(255,255,255,0.5)",
    fontSize: 16,
    textDecorationLine: "line-through",
    flex: 1,
  },
  itemPrice: {
    color: "rgba(255,255,255,0.45)",
    fontSize: 13,
    marginTop: 2,
  },
  itemQty: {
    color: "rgba(255,255,255,0.5)",
    fontSize: 14,
    marginTop: 2,
  },
  estimatedTotal: {
    color: "rgba(255,255,255,0.45)",
    fontSize: 13,
    textAlign: "center",
    marginBottom: 8,
  },
  divider: {
    height: 1,
    backgroundColor: "rgba(255,255,255,0.1)",
    marginVertical: 12,
  },
  doneLabel: {
    color: "rgba(255,255,255,0.4)",
    fontSize: 13,
    fontWeight: "600",
    marginBottom: 8,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  celebrationOverlay: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 40,
  },
  celebrationEmoji: {
    fontSize: 64,
    marginBottom: 16,
  },
  celebrationText: {
    color: "#fff",
    fontSize: 28,
    fontWeight: "bold",
    marginBottom: 24,
  },
  celebrationBtn: {
    borderRadius: 20,
    paddingHorizontal: 8,
  },
});
