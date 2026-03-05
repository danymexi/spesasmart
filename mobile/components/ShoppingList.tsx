import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from "react-native";
import {
  ActivityIndicator,
  Button,
  Checkbox,
  IconButton,
  Modal,
  Portal,
  Text,
  TextInput,
  useTheme,
} from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import {
  getShoppingList,
  getShoppingListCompare,
  getShoppingListSuggestions,
  addToShoppingList,
  toggleShoppingItem,
  removeShoppingItem,
  clearCheckedItems,
  updateLinkedProducts,
  smartSearch,
  type ShoppingListItem,
  type CompareItemInfo,
  type ChainPriceInfo,
  type SmartSearchResult,
  type LinkedProductDetail,
} from "../services/api";
import { glassCard, glassColors } from "../styles/glassStyles";
import { useAppStore } from "../stores/useAppStore";
import ChainTotalsSummary from "./ChainTotalsSummary";
import SuggestionsSection from "./SuggestionsSection";
import TripOptimizer from "./TripOptimizer";

const INVALIDATE_KEYS = [
  "shoppingList",
  "shoppingListCount",
  "shoppingListCompare",
  "shoppingListSuggestions",
];

export default function ShoppingList() {
  const theme = useTheme();
  const queryClient = useQueryClient();
  const nearbyChains = useAppStore((s) => s.nearbyChains);
  const [customInput, setCustomInput] = useState("");
  const [showOptimizer, setShowOptimizer] = useState(false);
  const [suggestions, setSuggestions] = useState<SmartSearchResult[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [inputFocused, setInputFocused] = useState(false);
  const [selectedSuggestions, setSelectedSuggestions] = useState<Map<string, SmartSearchResult>>(new Map());
  const [editingItem, setEditingItem] = useState<ShoppingListItem | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced autocomplete search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const query = customInput.trim();
    if (query.length < 2 || !inputFocused) {
      setSuggestions([]);
      setShowSuggestions(false);
      setLoadingSuggestions(false);
      return;
    }
    setLoadingSuggestions(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const results = await smartSearch(query, 15);
        setSuggestions(results);
        setShowSuggestions(true);
      } catch {
        setSuggestions([]);
      } finally {
        setLoadingSuggestions(false);
      }
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [customInput, inputFocused]);

  // ── Queries ──────────────────────────────────────────────────────────────

  const {
    data: items,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["shoppingList"],
    queryFn: getShoppingList,
  });

  const hasUnchecked = (items || []).some((i) => !i.checked);

  const {
    data: compareData,
    isLoading: loadingCompare,
  } = useQuery({
    queryKey: ["shoppingListCompare", nearbyChains.join(",")],
    queryFn: () =>
      getShoppingListCompare(
        nearbyChains.length > 0 ? nearbyChains.join(",") : undefined
      ),
    enabled: hasUnchecked,
  });

  const { data: suggestionsData } = useQuery({
    queryKey: ["shoppingListSuggestions"],
    queryFn: () => getShoppingListSuggestions(),
    enabled: (items || []).length > 0,
  });

  // ── Mutations ────────────────────────────────────────────────────────────

  const invalidateAll = () => {
    INVALIDATE_KEYS.forEach((key) =>
      queryClient.invalidateQueries({ queryKey: [key] })
    );
  };

  const addMutation = useMutation({
    mutationFn: addToShoppingList,
    onSuccess: () => {
      invalidateAll();
      setCustomInput("");
      setSuggestions([]);
      setShowSuggestions(false);
      setSelectedSuggestions(new Map());
    },
  });

  const toggleMutation = useMutation({
    mutationFn: toggleShoppingItem,
    onSuccess: invalidateAll,
  });

  const removeMutation = useMutation({
    mutationFn: removeShoppingItem,
    onSuccess: invalidateAll,
  });

  const clearMutation = useMutation({
    mutationFn: clearCheckedItems,
    onSuccess: invalidateAll,
  });

  const updateLinksMutation = useMutation({
    mutationFn: ({ itemId, productIds }: { itemId: string; productIds: string[] }) =>
      updateLinkedProducts(itemId, productIds),
    onSuccess: () => {
      invalidateAll();
      setEditingItem(null);
    },
  });

  // ── Derived data ─────────────────────────────────────────────────────────

  const compareMap = useMemo(() => {
    const map = new Map<string, CompareItemInfo>();
    if (!compareData) return map;
    for (const ci of compareData.items) {
      map.set(ci.item_id, ci);
    }
    return map;
  }, [compareData]);

  const uncheckedItems = useMemo(
    () => (items || []).filter((i) => !i.checked),
    [items]
  );

  const checkedItems = useMemo(
    () => (items || []).filter((i) => i.checked),
    [items]
  );

  // ── Handlers ─────────────────────────────────────────────────────────────

  const handleAddCustom = () => {
    const name = customInput.trim();
    if (!name) return;
    addMutation.mutate({ custom_name: name });
  };

  const handleAddSuggestion = (productId: string) => {
    addMutation.mutate({ product_id: productId });
  };

  const toggleSuggestionSelection = useCallback((result: SmartSearchResult) => {
    setSelectedSuggestions((prev) => {
      const next = new Map(prev);
      if (next.has(result.product.id)) {
        next.delete(result.product.id);
      } else {
        next.set(result.product.id, result);
      }
      return next;
    });
  }, []);

  const handleAddSelected = () => {
    if (selectedSuggestions.size === 0) return;
    const ids = Array.from(selectedSuggestions.keys());
    addMutation.mutate({
      product_ids: ids,
      custom_name: customInput.trim() || undefined,
    });
  };

  const handleRemoveLinkedProduct = (productId: string) => {
    if (!editingItem) return;
    const remaining = editingItem.linked_products_details.filter((p) => p.id !== productId);
    if (remaining.length === 0) {
      // If removing all products, delete the entire item
      removeMutation.mutate(editingItem.id);
      setEditingItem(null);
      return;
    }
    updateLinksMutation.mutate({
      itemId: editingItem.id,
      productIds: remaining.map((p) => p.id),
    });
    // Optimistically update local state for instant feedback
    setEditingItem({
      ...editingItem,
      linked_products_details: remaining,
      linked_product_ids: remaining.map((p) => p.id),
      linked_product_count: remaining.length,
    });
  };

  const handleInputBlur = useCallback(() => {
    // Delay to allow tap on suggestion before closing
    setTimeout(() => {
      if (selectedSuggestions.size > 0) return; // keep open while selecting
      setInputFocused(false);
      setShowSuggestions(false);
    }, 200);
  }, [selectedSuggestions.size]);

  // ── Render helpers ───────────────────────────────────────────────────────

  const renderPricePills = (itemId: string) => {
    if (loadingCompare) {
      return (
        <Text variant="labelSmall" style={styles.loadingPrices}>
          Cercando prezzi...
        </Text>
      );
    }

    const compareInfo = compareMap.get(itemId);
    if (!compareInfo || compareInfo.chain_prices.length === 0) {
      return (
        <Text variant="labelSmall" style={styles.noPrices}>
          Nessuna offerta trovata
        </Text>
      );
    }

    return (
      <View style={styles.pillsRow}>
        {compareInfo.chain_prices.map((cp: ChainPriceInfo) => (
          <View
            key={cp.chain_slug}
            style={[styles.pill, cp.is_best && styles.pillBest]}
          >
            <Text
              style={[styles.pillText, cp.is_best && styles.pillTextBest]}
              numberOfLines={1}
            >
              {cp.chain_name} {"\u20AC"}
              {Number(cp.offer_price).toFixed(2)}
              {cp.is_best ? " \u2605" : ""}
            </Text>
          </View>
        ))}
      </View>
    );
  };

  const renderItem = (item: ShoppingListItem, isChecked: boolean) => {
    const displayName = item.product_name || item.custom_name || "\u2014";
    const hasLinked = item.linked_product_count > 0;

    return (
      <Pressable
        key={item.id}
        style={[styles.itemCard, isChecked && styles.itemChecked]}
        onPress={() => {
          if (hasLinked && !isChecked) {
            setEditingItem(item);
          } else if (item.product_id) {
            router.push(`/product/${item.product_id}`);
          }
        }}
      >
        <Checkbox
          status={isChecked ? "checked" : "unchecked"}
          onPress={() => toggleMutation.mutate(item.id)}
          color={theme.colors.primary}
        />
        <View style={styles.itemContent}>
          <Text
            variant="bodyMedium"
            style={[styles.itemName, isChecked && styles.itemNameChecked]}
            numberOfLines={2}
          >
            {displayName}
            {item.quantity > 1 ? `  x${item.quantity}` : ""}
          </Text>
          {hasLinked && !isChecked && (
            <Text variant="labelSmall" style={styles.linkedBadge}>
              {item.linked_product_count} prodotti collegati
            </Text>
          )}
          {!isChecked && renderPricePills(item.id)}
          {item.notes && (
            <Text variant="labelSmall" style={styles.noteText}>
              {item.notes}
            </Text>
          )}
        </View>
        <IconButton
          icon="close"
          size={18}
          onPress={() => removeMutation.mutate(item.id)}
        />
      </Pressable>
    );
  };

  // ── Main render ──────────────────────────────────────────────────────────

  return (
    <View style={styles.container}>
      {/* Input row + autocomplete dropdown */}
      <View style={styles.inputWrapper}>
        <View style={styles.inputRow}>
          <TextInput
            label="Aggiungi articolo"
            value={customInput}
            onChangeText={setCustomInput}
            mode="outlined"
            style={styles.input}
            dense
            onSubmitEditing={handleAddCustom}
            onFocus={() => setInputFocused(true)}
            onBlur={handleInputBlur}
          />
          <IconButton
            icon="plus"
            mode="contained"
            onPress={handleAddCustom}
            disabled={!customInput.trim()}
            style={styles.addButton}
          />
        </View>

        {/* Autocomplete dropdown */}
        {inputFocused && customInput.trim().length >= 2 && (showSuggestions || loadingSuggestions || selectedSuggestions.size > 0) && (
          <View style={styles.autocompleteDropdown}>
            <ScrollView
              keyboardShouldPersistTaps="handled"
              nestedScrollEnabled
              style={styles.autocompleteScroll}
            >
              {loadingSuggestions && suggestions.length === 0 && (
                <View style={styles.autocompleteLoading}>
                  <ActivityIndicator size={16} />
                  <Text variant="bodySmall" style={styles.autocompleteLoadingText}>
                    Cercando...
                  </Text>
                </View>
              )}
              {suggestions.map((result) => {
                const bestOffer = result.offers.length > 0
                  ? result.offers.reduce((a, b) => (a.offer_price < b.offer_price ? a : b))
                  : null;
                const isSelected = selectedSuggestions.has(result.product.id);
                return (
                  <Pressable
                    key={result.product.id}
                    style={[styles.autocompleteItem, isSelected && styles.autocompleteItemSelected]}
                    onPress={() => toggleSuggestionSelection(result)}
                  >
                    <MaterialCommunityIcons
                      name={isSelected ? "checkbox-marked" : "checkbox-blank-outline"}
                      size={20}
                      color={isSelected ? glassColors.greenDark : "#999"}
                      style={styles.autocompleteCheckbox}
                    />
                    <View style={styles.autocompleteTextWrap}>
                      <Text variant="bodyMedium" style={styles.autocompleteName} numberOfLines={1}>
                        {result.product.name}
                      </Text>
                      <Text variant="labelSmall" style={styles.autocompleteMeta} numberOfLines={1}>
                        {result.product.brand || ""}
                        {bestOffer
                          ? `${result.product.brand ? " \u00B7 " : ""}\u20AC${Number(bestOffer.offer_price).toFixed(2)} — ${bestOffer.chain_name}`
                          : ""}
                      </Text>
                    </View>
                  </Pressable>
                );
              })}
            </ScrollView>
            {/* Action buttons at bottom */}
            {selectedSuggestions.size > 0 ? (
              <View style={styles.autocompleteActions}>
                <Pressable style={styles.autocompleteAddBtn} onPress={handleAddSelected}>
                  <MaterialCommunityIcons name="cart-plus" size={16} color="#fff" />
                  <Text style={styles.autocompleteAddBtnText}>
                    Aggiungi {selectedSuggestions.size} alla lista
                  </Text>
                </Pressable>
                <Pressable
                  style={styles.autocompleteCancelBtn}
                  onPress={() => setSelectedSuggestions(new Map())}
                >
                  <Text style={styles.autocompleteCancelText}>Annulla</Text>
                </Pressable>
              </View>
            ) : (
              <Pressable style={styles.autocompleteCustom} onPress={handleAddCustom}>
                <MaterialCommunityIcons name="magnify" size={16} color="#666" />
                <Text variant="bodySmall" style={styles.autocompleteCustomText} numberOfLines={1}>
                  Aggiungi "{customInput.trim()}" (auto-match)
                </Text>
              </Pressable>
            )}
          </View>
        )}
      </View>

      <ScrollView
        refreshControl={
          <RefreshControl refreshing={isLoading} onRefresh={refetch} />
        }
        contentContainerStyle={styles.scrollContent}
      >
        {/* Empty state */}
        {!isLoading && (items || []).length === 0 && (
          <View style={styles.emptyContainer}>
            <Text variant="titleMedium" style={styles.emptyTitle}>
              Lista della spesa vuota
            </Text>
            <Text variant="bodyMedium" style={styles.emptyText}>
              Aggiungi prodotti dal catalogo o scrivi un articolo qui sopra.
            </Text>
          </View>
        )}

        {/* Chain totals summary */}
        {hasUnchecked &&
          compareData &&
          compareData.chain_totals.length > 0 && (
            <ChainTotalsSummary
              chainTotals={compareData.chain_totals}
              itemsTotal={compareData.items_total}
              multiStoreTotal={compareData.multi_store_total}
              potentialSavings={compareData.potential_savings}
              onOpenOptimizer={() => setShowOptimizer(true)}
            />
          )}

        {hasUnchecked && loadingCompare && (
          <ActivityIndicator style={{ marginVertical: 12 }} />
        )}

        {/* Unchecked items */}
        {uncheckedItems.map((item) => renderItem(item, false))}

        {/* Action buttons */}
        {(items || []).length > 0 && (
          <View style={styles.actionRow}>
            <Button
              mode="contained"
              icon="map-marker-path"
              onPress={() => setShowOptimizer(true)}
              style={styles.optimizeButton}
              labelStyle={styles.actionLabel}
              compact
            >
              Ottimizza Spesa
            </Button>
            {checkedItems.length > 0 && (
              <Button
                mode="outlined"
                icon="delete-sweep"
                onPress={() => clearMutation.mutate()}
                loading={clearMutation.isPending}
                compact
              >
                Svuota completati ({checkedItems.length})
              </Button>
            )}
          </View>
        )}

        {/* Checked items */}
        {checkedItems.length > 0 && (
          <>
            <View style={styles.checkedHeader}>
              <Text variant="labelMedium" style={styles.checkedHeaderText}>
                Completati ({checkedItems.length})
              </Text>
            </View>
            {checkedItems.map((item) => renderItem(item, true))}
          </>
        )}

        {/* Suggestions */}
        {suggestionsData && (
          <SuggestionsSection
            alternatives={suggestionsData.alternatives}
            complementary={suggestionsData.complementary}
            onAddToList={handleAddSuggestion}
          />
        )}

        <View style={styles.bottomPadding} />
      </ScrollView>

      <TripOptimizer
        visible={showOptimizer}
        onDismiss={() => setShowOptimizer(false)}
      />

      {/* Linked products detail modal */}
      <Portal>
        <Modal
          visible={!!editingItem}
          onDismiss={() => setEditingItem(null)}
          contentContainerStyle={styles.modalContainer}
        >
          {editingItem && (
            <View>
              <Text variant="titleMedium" style={styles.modalTitle}>
                Prodotti collegati
              </Text>
              <Text variant="bodySmall" style={styles.modalSubtitle}>
                {editingItem.custom_name || editingItem.product_name}
              </Text>
              <View style={styles.modalList}>
                {editingItem.linked_products_details.map((p) => (
                  <View key={p.id} style={styles.modalItem}>
                    <View style={styles.modalItemInfo}>
                      <Text variant="bodyMedium" style={styles.modalItemName} numberOfLines={2}>
                        {p.name}
                      </Text>
                      {p.brand && (
                        <Text variant="labelSmall" style={styles.modalItemBrand}>
                          {p.brand}
                        </Text>
                      )}
                    </View>
                    <IconButton
                      icon="close-circle-outline"
                      size={20}
                      iconColor="#C62828"
                      onPress={() => handleRemoveLinkedProduct(p.id)}
                      style={styles.modalRemoveBtn}
                    />
                  </View>
                ))}
              </View>
              <Button
                mode="outlined"
                onPress={() => setEditingItem(null)}
                style={styles.modalCloseBtn}
              >
                Chiudi
              </Button>
            </View>
          )}
        </Modal>
      </Portal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  inputWrapper: {
    zIndex: 10,
  },
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
  scrollContent: { paddingBottom: 24 },

  // Autocomplete dropdown
  autocompleteDropdown: {
    position: "absolute",
    top: "100%",
    left: 12,
    right: 12,
    backgroundColor: "#fff",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e0e0e0",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.12,
    shadowRadius: 6,
    elevation: 4,
    zIndex: 20,
    maxHeight: 320,
  },
  autocompleteScroll: {
    maxHeight: 260,
  },
  autocompleteLoading: {
    flexDirection: "row",
    alignItems: "center",
    padding: 12,
    gap: 8,
  },
  autocompleteLoadingText: {
    color: "#999",
  },
  autocompleteItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#eee",
  },
  autocompleteItemSelected: {
    backgroundColor: "rgba(46,125,50,0.06)",
  },
  autocompleteCheckbox: {
    marginRight: 10,
  },
  autocompleteTextWrap: {
    flex: 1,
  },
  autocompleteName: {
    fontWeight: "600",
    color: "#1a1a1a",
  },
  autocompleteMeta: {
    color: "#888",
    marginTop: 2,
  },
  autocompleteActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: "#e0e0e0",
    backgroundColor: "#fafafa",
  },
  autocompleteAddBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    backgroundColor: glassColors.greenDark,
    borderRadius: 8,
    paddingVertical: 8,
  },
  autocompleteAddBtnText: {
    color: "#fff",
    fontWeight: "700",
    fontSize: 13,
  },
  autocompleteCancelBtn: {
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  autocompleteCancelText: {
    color: "#666",
    fontSize: 13,
  },
  autocompleteCustom: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: "#e0e0e0",
    backgroundColor: "#fafafa",
  },
  autocompleteCustomText: {
    color: "#666",
    flex: 1,
  },

  // Items
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
    opacity: 0.55,
  },
  itemContent: { flex: 1, paddingVertical: 4 },
  itemName: { fontWeight: "600", color: "#1a1a1a" },
  itemNameChecked: {
    textDecorationLine: "line-through",
    color: "#999",
  },
  noteText: { color: "#666", marginTop: 2, fontStyle: "italic" },

  // Price pills
  pillsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    marginTop: 6,
  },
  pill: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
    backgroundColor: "rgba(0,0,0,0.05)",
  },
  pillBest: {
    backgroundColor: "rgba(46,125,50,0.14)",
  },
  pillText: {
    fontSize: 11,
    fontWeight: "600",
    color: "#555",
  },
  pillTextBest: {
    color: glassColors.greenDark,
    fontWeight: "bold",
  },
  loadingPrices: {
    color: "#999",
    marginTop: 4,
    fontStyle: "italic",
  },
  noPrices: {
    color: "#aaa",
    marginTop: 4,
    fontStyle: "italic",
  },

  // Action row
  actionRow: {
    flexDirection: "row",
    justifyContent: "center",
    flexWrap: "wrap",
    gap: 10,
    paddingVertical: 14,
    paddingHorizontal: 12,
  },
  optimizeButton: {
    backgroundColor: glassColors.greenDark,
  },
  actionLabel: { fontSize: 13 },

  // Checked header
  checkedHeader: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 4,
  },
  checkedHeaderText: {
    color: "#999",
    textTransform: "uppercase",
    letterSpacing: 1,
    fontSize: 11,
  },

  // Empty
  emptyContainer: { alignItems: "center", padding: 40 },
  emptyTitle: { marginBottom: 8, color: "#1a1a1a" },
  emptyText: { color: "#555", textAlign: "center" },

  bottomPadding: { height: 60 },

  // Linked badge
  linkedBadge: {
    color: glassColors.greenDark,
    fontSize: 11,
    fontWeight: "600",
    marginTop: 2,
  },

  // Modal
  modalContainer: {
    backgroundColor: "#fff",
    marginHorizontal: 24,
    borderRadius: 16,
    padding: 20,
    maxHeight: "70%",
  },
  modalTitle: {
    fontWeight: "700",
    color: "#1a1a1a",
    marginBottom: 2,
  },
  modalSubtitle: {
    color: "#666",
    marginBottom: 16,
  },
  modalList: {
    gap: 2,
  },
  modalItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    paddingHorizontal: 4,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#eee",
  },
  modalItemInfo: {
    flex: 1,
  },
  modalItemName: {
    fontWeight: "600",
    color: "#1a1a1a",
  },
  modalItemBrand: {
    color: "#888",
    marginTop: 1,
  },
  modalRemoveBtn: {
    margin: 0,
  },
  modalCloseBtn: {
    marginTop: 16,
  },
});
