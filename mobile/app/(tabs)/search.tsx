import { useState } from "react";
import { FlatList, Image, StyleSheet, View } from "react-native";
import { Searchbar, Chip, Text, useTheme, ActivityIndicator } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { router, useLocalSearchParams } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { searchProducts } from "../../services/api";
import {
  glassCard,
  glassChip,
  glassColors,
  glassSearchbar,
  productImage,
  imagePlaceholder,
} from "../../styles/glassStyles";

const CATEGORIES = ["Latticini", "Frutta", "Verdura", "Bevande", "Carne", "Pesce", "Pane", "Surgelati"];
const CHAINS = ["esselunga", "lidl", "coop", "iperal"];

export default function SearchScreen() {
  const theme = useTheme();
  const params = useLocalSearchParams<{ chain?: string }>();
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedChain, setSelectedChain] = useState<string | null>(params.chain ?? null);

  const { data: results, isLoading } = useQuery({
    queryKey: ["search", query, selectedCategory],
    queryFn: () => searchProducts(query, selectedCategory ?? undefined),
    enabled: query.length >= 2,
  });

  return (
    <View style={styles.container}>
      <Searchbar
        placeholder="Cerca prodotti... (es. latte, pasta)"
        onChangeText={setQuery}
        value={query}
        style={styles.searchbar}
      />

      {/* Chain filters */}
      <View style={styles.filterRow}>
        {CHAINS.map((c) => (
          <Chip
            key={c}
            selected={selectedChain === c}
            onPress={() => setSelectedChain(selectedChain === c ? null : c)}
            style={styles.filterChip}
            compact
          >
            {c.charAt(0).toUpperCase() + c.slice(1)}
          </Chip>
        ))}
      </View>

      {/* Category filters */}
      <FlatList
        horizontal
        showsHorizontalScrollIndicator={false}
        data={CATEGORIES}
        keyExtractor={(item) => item}
        renderItem={({ item }) => (
          <Chip
            selected={selectedCategory === item}
            onPress={() => setSelectedCategory(selectedCategory === item ? null : item)}
            style={styles.filterChip}
            compact
          >
            {item}
          </Chip>
        )}
        contentContainerStyle={styles.categoryRow}
        style={{ flexGrow: 0 }}
      />

      {/* Results */}
      {isLoading ? (
        <ActivityIndicator style={styles.loader} />
      ) : (
        <FlatList
          data={results}
          keyExtractor={(item) => item.product.id}
          renderItem={({ item }) => (
            <View
              style={styles.resultCard}
            >
              <View
                style={styles.resultCardInner}
              >
                {/* Product image */}
                {item.product.image_url ? (
                  <Image
                    source={{ uri: item.product.image_url }}
                    style={styles.resultImage}
                    resizeMode="contain"
                  />
                ) : (
                  <View style={[styles.resultImage, styles.resultImagePlaceholder]}>
                    <MaterialCommunityIcons name="food-variant" size={24} color="#ccc" />
                  </View>
                )}

                <View style={styles.resultRow}>
                  <View
                    style={styles.resultInfo}
                  >
                    <Text
                      variant="titleMedium"
                      numberOfLines={2}
                      onPress={() => router.push(`/product/${item.product.id}`)}
                    >
                      {item.product.name}
                    </Text>
                    {item.product.brand && (
                      <Text variant="bodySmall" style={styles.brandText}>
                        {item.product.brand}
                      </Text>
                    )}
                    {item.product.category && (
                      <Chip compact style={styles.categoryChip}>
                        {item.product.category}
                      </Chip>
                    )}
                  </View>
                  <View style={styles.resultPrice}>
                    {item.best_current_price ? (
                      <>
                        <Text
                          variant="headlineSmall"
                          style={{ color: theme.colors.primary, fontWeight: "bold" }}
                        >
                          {"\u20AC"}{Number(item.best_current_price).toFixed(2)}
                        </Text>
                        {item.chain_name && (
                          <Text variant="bodySmall" style={styles.chainLabel}>
                            {item.chain_name}
                          </Text>
                        )}
                        <Text variant="labelSmall" style={styles.offersCount}>
                          {item.offers_count} offert{item.offers_count === 1 ? "a" : "e"}
                        </Text>
                      </>
                    ) : (
                      <Text variant="bodySmall" style={{ color: "#999" }}>
                        Nessuna offerta
                      </Text>
                    )}
                  </View>
                </View>
              </View>
            </View>
          )}
          ListEmptyComponent={
            query.length >= 2 ? (
              <Text style={styles.emptyText}>Nessun risultato per "{query}"</Text>
            ) : (
              <Text style={styles.emptyText}>
                Cerca un prodotto per confrontare i prezzi
              </Text>
            )
          }
          contentContainerStyle={styles.listContent}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  searchbar: {
    margin: 12,
    ...glassSearchbar,
  } as any,
  filterRow: { flexDirection: "row", paddingHorizontal: 12, gap: 6, flexWrap: "wrap" },
  filterChip: {
    marginBottom: 6,
    ...glassChip,
  } as any,
  categoryRow: { paddingHorizontal: 12, paddingVertical: 8, gap: 6 },
  loader: { marginTop: 40 },
  resultCard: {
    marginHorizontal: 12,
    marginBottom: 8,
    padding: 12,
    ...glassCard,
  } as any,
  resultCardInner: {
    flexDirection: "row",
    alignItems: "flex-start",
  },
  resultImage: {
    ...productImage.search,
    marginRight: 12,
  },
  resultImagePlaceholder: {
    ...imagePlaceholder,
  },
  resultRow: { flex: 1, flexDirection: "row", justifyContent: "space-between" },
  resultInfo: { flex: 1, marginRight: 12 },
  brandText: { color: "#666", marginTop: 2 },
  categoryChip: { marginTop: 6, alignSelf: "flex-start" },
  resultPrice: { alignItems: "flex-end", justifyContent: "center" },
  chainLabel: { color: "#666", marginTop: 2 },
  offersCount: { color: "#999", marginTop: 2 },
  emptyText: { textAlign: "center", marginTop: 40, color: "#888", paddingHorizontal: 20 },
  listContent: { paddingBottom: 96 },
});
