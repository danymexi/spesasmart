import { FlatList, Image, StyleSheet, TouchableOpacity, View } from "react-native";
import { IconButton, Text } from "react-native-paper";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { glassCard, glassColors, productImage, imagePlaceholder } from "../styles/glassStyles";
import type { SuggestionItem } from "../services/api";

interface Props {
  alternatives: SuggestionItem[];
  complementary: SuggestionItem[];
  onAddToList: (productId: string) => void;
}

function SuggestionCard({
  item,
  onAdd,
}: {
  item: SuggestionItem;
  onAdd: () => void;
}) {
  return (
    <TouchableOpacity
      style={styles.itemCard}
      activeOpacity={0.7}
      onPress={() => router.push(`/product/${item.product_id}`)}
    >
      {item.image_url ? (
        <Image
          source={{ uri: item.image_url }}
          style={styles.image}
          resizeMode="contain"
        />
      ) : (
        <View style={[styles.image, styles.imagePlaceholder]}>
          <MaterialCommunityIcons name="food-variant" size={16} color="#ccc" />
        </View>
      )}
      <Text style={styles.itemName} numberOfLines={2}>
        {item.product_name}
      </Text>
      {item.brand && (
        <Text style={styles.brand} numberOfLines={1}>
          {item.brand}
        </Text>
      )}
      <View style={styles.priceRow}>
        <Text style={styles.price}>
          {"\u20AC"}{Number(item.offer_price).toFixed(2)}
        </Text>
        <Text style={styles.chain} numberOfLines={1}>
          {item.chain_name}
        </Text>
      </View>
      {item.discount_pct && (
        <Text style={styles.discount}>
          -{Number(item.discount_pct).toFixed(0)}%
        </Text>
      )}
      <IconButton
        icon="cart-plus"
        iconColor={glassColors.greenMedium}
        size={20}
        onPress={onAdd}
        style={styles.addBtn}
      />
    </TouchableOpacity>
  );
}

export default function SuggestionsSection({
  alternatives,
  complementary,
  onAddToList,
}: Props) {
  if (alternatives.length === 0 && complementary.length === 0) return null;

  return (
    <View style={styles.container}>
      {alternatives.length > 0 && (
        <>
          <View style={styles.sectionHeader}>
            <MaterialCommunityIcons
              name="swap-horizontal"
              size={20}
              color="#E65100"
            />
            <Text style={styles.sectionTitle}>Alternative Convenienti</Text>
          </View>
          <FlatList
            horizontal
            showsHorizontalScrollIndicator={false}
            data={alternatives}
            keyExtractor={(item, i) => `alt-${item.product_id}-${i}`}
            renderItem={({ item }) => (
              <SuggestionCard
                item={item}
                onAdd={() => onAddToList(item.product_id)}
              />
            )}
            contentContainerStyle={styles.list}
          />
        </>
      )}

      {complementary.length > 0 && (
        <>
          <View style={styles.sectionHeader}>
            <MaterialCommunityIcons
              name="lightbulb-on-outline"
              size={20}
              color="#1565C0"
            />
            <Text style={styles.sectionTitle}>Potresti aver bisogno di...</Text>
          </View>
          <FlatList
            horizontal
            showsHorizontalScrollIndicator={false}
            data={complementary}
            keyExtractor={(item, i) => `comp-${item.product_id}-${i}`}
            renderItem={({ item }) => (
              <SuggestionCard
                item={item}
                onAdd={() => onAddToList(item.product_id)}
              />
            )}
            contentContainerStyle={styles.list}
          />
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginBottom: 8,
  },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: "700",
    color: glassColors.greenDark,
  },
  list: {
    paddingHorizontal: 12,
  },
  itemCard: {
    width: 160,
    marginRight: 10,
    padding: 10,
    ...glassCard,
    position: "relative",
  } as any,
  image: {
    ...productImage.compact,
    alignSelf: "center",
    marginBottom: 6,
  },
  imagePlaceholder: {
    ...imagePlaceholder,
  },
  itemName: {
    fontSize: 12,
    fontWeight: "600",
    color: glassColors.textPrimary,
    marginBottom: 2,
  },
  brand: {
    fontSize: 10,
    color: glassColors.textMuted,
    marginBottom: 4,
  },
  priceRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 4,
  },
  price: {
    fontSize: 14,
    fontWeight: "bold",
    color: glassColors.greenDark,
  },
  chain: {
    fontSize: 10,
    color: glassColors.textMuted,
    flex: 1,
    textAlign: "right",
  },
  discount: {
    fontSize: 11,
    color: "#E65100",
    fontWeight: "bold",
    marginTop: 2,
  },
  addBtn: {
    position: "absolute",
    top: 0,
    right: 0,
    margin: 0,
  },
});
