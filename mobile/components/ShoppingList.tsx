import { useState } from "react";
import { FlatList, RefreshControl, StyleSheet, View } from "react-native";
import { Button, Checkbox, IconButton, Text, TextInput, useTheme } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import {
  getShoppingList,
  addToShoppingList,
  toggleShoppingItem,
  removeShoppingItem,
  clearCheckedItems,
  ShoppingListItem,
} from "../services/api";
import { glassCard, glassColors } from "../styles/glassStyles";
import TripOptimizer from "./TripOptimizer";

export default function ShoppingList() {
  const theme = useTheme();
  const queryClient = useQueryClient();
  const [customInput, setCustomInput] = useState("");
  const [showOptimizer, setShowOptimizer] = useState(false);

  const { data: items, isLoading, refetch } = useQuery({
    queryKey: ["shoppingList"],
    queryFn: getShoppingList,
  });

  const addMutation = useMutation({
    mutationFn: addToShoppingList,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
      setCustomInput("");
    },
  });

  const toggleMutation = useMutation({
    mutationFn: toggleShoppingItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: removeShoppingItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
    },
  });

  const clearMutation = useMutation({
    mutationFn: clearCheckedItems,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
    },
  });

  const handleAddCustom = () => {
    const name = customInput.trim();
    if (!name) return;
    addMutation.mutate({ custom_name: name });
  };

  // Group items by chain (null chain = "Altro")
  const grouped = (items || []).reduce<Record<string, ShoppingListItem[]>>((acc, item) => {
    const key = item.chain_name || "Altro";
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});

  const sections = Object.entries(grouped).sort(([a], [b]) => {
    if (a === "Altro") return 1;
    if (b === "Altro") return -1;
    return a.localeCompare(b);
  });

  const checkedCount = (items || []).filter((i) => i.checked).length;

  const flatData = sections.flatMap(([chain, chainItems]) => [
    { type: "header" as const, chain },
    ...chainItems.map((item) => ({ type: "item" as const, ...item })),
  ]);

  return (
    <View style={styles.container}>
      {/* Manual input */}
      <View style={styles.inputRow}>
        <TextInput
          label="Aggiungi articolo"
          value={customInput}
          onChangeText={setCustomInput}
          mode="outlined"
          style={styles.input}
          dense
          onSubmitEditing={handleAddCustom}
        />
        <IconButton
          icon="plus"
          mode="contained"
          onPress={handleAddCustom}
          disabled={!customInput.trim()}
          style={styles.addButton}
        />
      </View>

      <FlatList
        data={flatData}
        keyExtractor={(item, idx) =>
          item.type === "header" ? `h-${item.chain}` : `i-${(item as any).id}`
        }
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refetch} />}
        renderItem={({ item }) => {
          if (item.type === "header") {
            return (
              <View style={styles.sectionHeader}>
                <Text variant="titleSmall" style={styles.sectionTitle}>
                  {item.chain}
                </Text>
              </View>
            );
          }

          const shopItem = item as ShoppingListItem & { type: "item" };
          const displayName = shopItem.product_name || shopItem.custom_name || "—";

          return (
            <View style={[styles.itemCard, shopItem.checked && styles.itemChecked]}>
              <Checkbox
                status={shopItem.checked ? "checked" : "unchecked"}
                onPress={() => toggleMutation.mutate(shopItem.id)}
                color={theme.colors.primary}
              />
              <View style={styles.itemContent}>
                <Text
                  variant="bodyMedium"
                  style={[
                    styles.itemName,
                    shopItem.checked && styles.itemNameChecked,
                  ]}
                  onPress={() =>
                    shopItem.product_id
                      ? router.push(`/product/${shopItem.product_id}`)
                      : undefined
                  }
                  numberOfLines={2}
                >
                  {displayName}
                  {shopItem.quantity > 1 ? ` x${shopItem.quantity}` : ""}
                </Text>
                {shopItem.offer_price != null && (
                  <Text variant="labelSmall" style={styles.priceText}>
                    {"\u20AC"}{Number(shopItem.offer_price).toFixed(2)}
                    {shopItem.chain_name ? ` @ ${shopItem.chain_name}` : ""}
                  </Text>
                )}
                {shopItem.notes && (
                  <Text variant="labelSmall" style={styles.noteText}>
                    {shopItem.notes}
                  </Text>
                )}
              </View>
              <IconButton
                icon="close"
                size={18}
                onPress={() => removeMutation.mutate(shopItem.id)}
              />
            </View>
          );
        }}
        ListEmptyComponent={
          !isLoading ? (
            <View style={styles.emptyContainer}>
              <Text variant="titleMedium" style={styles.emptyTitle}>
                Lista della spesa vuota
              </Text>
              <Text variant="bodyMedium" style={styles.emptyText}>
                Aggiungi prodotti dal catalogo o scrivi un articolo qui sopra.
              </Text>
            </View>
          ) : null
        }
        contentContainerStyle={styles.listContent}
      />

      {/* Action buttons */}
      <View style={styles.clearRow}>
        {(items?.length ?? 0) > 0 && (
          <Button
            mode="contained"
            icon="map-marker-path"
            onPress={() => setShowOptimizer(true)}
            style={styles.optimizeButton}
          >
            Ottimizza Spesa
          </Button>
        )}
        {checkedCount > 0 && (
          <Button
            mode="outlined"
            icon="delete-sweep"
            onPress={() => clearMutation.mutate()}
            loading={clearMutation.isPending}
          >
            Svuota completati ({checkedCount})
          </Button>
        )}
      </View>

      <TripOptimizer
        visible={showOptimizer}
        onDismiss={() => setShowOptimizer(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingTop: 12,
    paddingBottom: 4,
    gap: 4,
  },
  input: { flex: 1 },
  addButton: { marginTop: 6 },
  listContent: { paddingBottom: 96 },
  sectionHeader: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 4,
  },
  sectionTitle: {
    fontWeight: "bold",
    color: glassColors.greenDark,
    textTransform: "uppercase",
    fontSize: 12,
    letterSpacing: 1,
  },
  itemCard: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: 12,
    marginBottom: 4,
    paddingVertical: 4,
    paddingRight: 4,
    ...glassCard,
  } as any,
  itemChecked: {
    opacity: 0.6,
  },
  itemContent: { flex: 1, paddingVertical: 4 },
  itemName: { fontWeight: "500" },
  itemNameChecked: {
    textDecorationLine: "line-through",
    color: "#999",
  },
  priceText: { color: glassColors.greenMedium, marginTop: 2 },
  noteText: { color: "#888", marginTop: 2, fontStyle: "italic" },
  emptyContainer: { alignItems: "center", padding: 40 },
  emptyTitle: { marginBottom: 8 },
  emptyText: { color: "#888", textAlign: "center" },
  clearRow: {
    position: "absolute",
    bottom: 80,
    left: 0,
    right: 0,
    alignItems: "center",
    paddingVertical: 8,
    gap: 8,
  },
  optimizeButton: {
    backgroundColor: glassColors.greenDark,
  },
});
