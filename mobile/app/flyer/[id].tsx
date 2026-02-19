import { useState } from "react";
import { Dimensions, FlatList, Image, StyleSheet, View } from "react-native";
import { Card, Text, useTheme, ActivityIndicator, SegmentedButtons } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, router } from "expo-router";
import { getFlyer, getFlyerPages, getFlyerProducts } from "../../services/api";

const SCREEN_WIDTH = Dimensions.get("window").width;

export default function FlyerDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme();
  const [viewMode, setViewMode] = useState("pages");

  const { data: flyer, isLoading: loadingFlyer } = useQuery({
    queryKey: ["flyer", id],
    queryFn: () => getFlyer(id!),
    enabled: !!id,
  });

  const { data: pages } = useQuery({
    queryKey: ["flyerPages", id],
    queryFn: () => getFlyerPages(id!),
    enabled: !!id,
  });

  const { data: products } = useQuery({
    queryKey: ["flyerProducts", id],
    queryFn: () => getFlyerProducts(id!),
    enabled: !!id,
  });

  if (loadingFlyer) {
    return <ActivityIndicator style={styles.loader} />;
  }

  return (
    <View style={styles.container}>
      {/* Flyer info header */}
      {flyer && (
        <View style={styles.header}>
          <Text variant="titleMedium" style={styles.title}>
            {flyer.title ?? "Volantino"}
          </Text>
          <Text variant="bodySmall" style={styles.dates}>
            {flyer.chain_name} &middot;{" "}
            {new Date(flyer.valid_from).toLocaleDateString("it-IT")} -{" "}
            {new Date(flyer.valid_to).toLocaleDateString("it-IT")}
          </Text>
        </View>
      )}

      {/* View mode toggle */}
      <SegmentedButtons
        value={viewMode}
        onValueChange={setViewMode}
        buttons={[
          { value: "pages", label: "Pagine", icon: "image" },
          { value: "products", label: "Prodotti", icon: "format-list-bulleted" },
        ]}
        style={styles.segmented}
      />

      {/* Pages view */}
      {viewMode === "pages" && (
        <FlatList
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          data={pages}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <View style={styles.pageContainer}>
              {item.image_url ? (
                <Image
                  source={{ uri: item.image_url }}
                  style={styles.pageImage}
                  resizeMode="contain"
                />
              ) : (
                <View style={styles.placeholderPage}>
                  <Text variant="bodyMedium" style={styles.placeholderText}>
                    Pagina {item.page_number}
                  </Text>
                </View>
              )}
              <Text variant="labelSmall" style={styles.pageNumber}>
                Pagina {item.page_number} di {pages?.length ?? "?"}
              </Text>
            </View>
          )}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Text style={styles.emptyText}>Nessuna pagina disponibile</Text>
            </View>
          }
        />
      )}

      {/* Products view */}
      {viewMode === "products" && (
        <FlatList
          data={products}
          keyExtractor={(item, idx) => `${item.product_id}-${idx}`}
          renderItem={({ item }) => (
            <Card
              style={styles.productCard}
              onPress={() => router.push(`/product/${item.product_id}`)}
            >
              <Card.Content style={styles.productContent}>
                <View style={styles.productInfo}>
                  <Text variant="titleSmall" numberOfLines={2}>
                    {item.product_name}
                  </Text>
                  {item.brand && (
                    <Text variant="bodySmall" style={styles.brand}>
                      {item.brand}
                    </Text>
                  )}
                  {item.category && (
                    <Text variant="labelSmall" style={styles.category}>
                      {item.category}
                    </Text>
                  )}
                  {item.quantity && (
                    <Text variant="labelSmall" style={styles.quantity}>
                      {item.quantity}
                    </Text>
                  )}
                </View>
                <View style={styles.productPrice}>
                  <Text
                    variant="titleLarge"
                    style={{ color: theme.colors.primary, fontWeight: "bold" }}
                  >
                    {"\u20AC"}{Number(item.offer_price).toFixed(2)}
                  </Text>
                  {item.original_price && (
                    <Text variant="bodySmall" style={styles.originalPrice}>
                      {"\u20AC"}{Number(item.original_price).toFixed(2)}
                    </Text>
                  )}
                  {item.discount_pct && (
                    <Text variant="labelSmall" style={styles.discountBadge}>
                      -{Number(item.discount_pct).toFixed(0)}%
                    </Text>
                  )}
                </View>
              </Card.Content>
            </Card>
          )}
          ListEmptyComponent={
            <Text style={styles.emptyText}>Nessun prodotto estratto</Text>
          }
          contentContainerStyle={styles.productList}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  loader: { marginTop: 60 },
  header: { padding: 16, backgroundColor: "#fff" },
  title: { fontWeight: "bold" },
  dates: { color: "#666", marginTop: 4 },
  segmented: { marginHorizontal: 12, marginVertical: 8 },
  pageContainer: { width: SCREEN_WIDTH, alignItems: "center", padding: 8 },
  pageImage: { width: SCREEN_WIDTH - 32, height: SCREEN_WIDTH * 1.3, borderRadius: 8 },
  placeholderPage: {
    width: SCREEN_WIDTH - 32,
    height: SCREEN_WIDTH * 1.3,
    backgroundColor: "#e0e0e0",
    borderRadius: 8,
    justifyContent: "center",
    alignItems: "center",
  },
  placeholderText: { color: "#999" },
  pageNumber: { marginTop: 8, color: "#888" },
  emptyContainer: { width: SCREEN_WIDTH, alignItems: "center", paddingTop: 40 },
  emptyText: { textAlign: "center", color: "#888", padding: 20 },
  productCard: { marginHorizontal: 12, marginBottom: 8 },
  productContent: { flexDirection: "row", justifyContent: "space-between" },
  productInfo: { flex: 1, marginRight: 12 },
  brand: { color: "#666", marginTop: 2 },
  category: { color: "#999", marginTop: 2 },
  quantity: { color: "#888", marginTop: 2 },
  productPrice: { alignItems: "flex-end" },
  originalPrice: { textDecorationLine: "line-through", color: "#999" },
  discountBadge: { color: "#E65100", fontWeight: "bold", marginTop: 2 },
  productList: { paddingTop: 4, paddingBottom: 20 },
});
