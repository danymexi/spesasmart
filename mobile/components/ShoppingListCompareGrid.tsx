import { Image, StyleSheet, TouchableOpacity, View } from "react-native";
import { Text } from "react-native-paper";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { glassCard, glassColors, productImage, imagePlaceholder } from "../styles/glassStyles";
import { useGlassTheme } from "../styles/useGlassTheme";
import type { CompareItemInfo } from "../services/api";

interface Props {
  items: CompareItemInfo[];
}

export default function ShoppingListCompareGrid({ items }: Props) {
  const glass = useGlassTheme();
  const { colors } = glass;

  if (items.length === 0) return null;

  return (
    <View style={styles.container}>
      <View style={styles.sectionHeader}>
        <MaterialCommunityIcons
          name="format-list-checks"
          size={20}
          color={colors.primary}
        />
        <Text style={[styles.sectionTitle, { color: colors.primary }]}>I Tuoi Prodotti</Text>
      </View>

      {items.map((item) => (
        <TouchableOpacity
          key={item.item_id}
          style={[styles.card, glass.card]}
          activeOpacity={0.7}
          onPress={() => {
            if (item.product_id) {
              router.push(`/product/${item.product_id}`);
            }
          }}
        >
          <View style={styles.header}>
            {item.image_url ? (
              <Image
                source={{ uri: item.image_url }}
                style={styles.image}
                resizeMode="contain"
              />
            ) : (
              <View style={[styles.image, styles.imagePlaceholder]}>
                <MaterialCommunityIcons
                  name="food-variant"
                  size={18}
                  color={colors.textMuted}
                />
              </View>
            )}
            <View style={styles.nameSection}>
              {item.search_term && (
                <Text style={[styles.searchTerm, { color: colors.textMuted }]}>
                  Cercato: "{item.search_term}"
                </Text>
              )}
              <Text style={[styles.itemName, { color: colors.textPrimary }]} numberOfLines={2}>
                {item.display_name}
              </Text>
              {item.quantity > 1 && (
                <Text style={[styles.qty, { color: colors.textMuted }]}>x{item.quantity}</Text>
              )}
            </View>
          </View>

          {item.chain_prices.length > 0 ? (
            <View style={styles.chainsRow}>
              {item.chain_prices.map((cp) => (
                <View
                  key={cp.chain_slug}
                  style={[
                    styles.chainCell,
                    { backgroundColor: colors.subtleBg },
                    cp.is_best && { backgroundColor: colors.primarySubtle },
                  ]}
                >
                  <Text
                    style={[
                      styles.chainName,
                      { color: colors.textSecondary },
                      cp.is_best && { color: colors.primary, fontWeight: "600" },
                    ]}
                    numberOfLines={1}
                  >
                    {cp.chain_name}
                  </Text>
                  <Text
                    style={[
                      styles.chainPrice,
                      { color: colors.textPrimary },
                      cp.is_best && { color: colors.primary },
                    ]}
                  >
                    {"\u20AC"}{Number(cp.offer_price).toFixed(2)}
                  </Text>
                  {cp.is_best && (
                    <MaterialCommunityIcons
                      name="star"
                      size={12}
                      color={colors.primary}
                    />
                  )}
                  {cp.discount_pct && (
                    <Text
                      style={[
                        styles.discount,
                        { color: colors.accent },
                        cp.is_best && { color: colors.primary },
                      ]}
                    >
                      -{Number(cp.discount_pct).toFixed(0)}%
                    </Text>
                  )}
                </View>
              ))}
            </View>
          ) : (
            <Text style={[styles.noPrices, { color: colors.textMuted }]}>
              Nessuna offerta trovata
            </Text>
          )}
        </TouchableOpacity>
      ))}
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
    paddingBottom: 10,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: glassColors.greenDark,
  },
  card: {
    marginHorizontal: 12,
    marginBottom: 8,
    padding: 12,
    ...glassCard,
  } as any,
  header: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: 8,
  },
  image: {
    ...productImage.compact,
    marginRight: 10,
  },
  imagePlaceholder: {
    ...imagePlaceholder,
  },
  nameSection: {
    flex: 1,
  },
  searchTerm: {
    fontSize: 10,
    color: glassColors.textMuted,
    fontStyle: "italic",
    marginBottom: 2,
  },
  itemName: {
    fontSize: 14,
    fontWeight: "600",
    color: glassColors.textPrimary,
  },
  qty: {
    fontSize: 12,
    color: glassColors.textMuted,
    marginTop: 2,
  },
  chainsRow: {
    flexDirection: "row",
    gap: 6,
  },
  chainCell: {
    flex: 1,
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.03)",
    borderRadius: 10,
    paddingVertical: 6,
    paddingHorizontal: 4,
  },
  chainCellBest: {
    backgroundColor: "rgba(27,94,32,0.08)",
  },
  chainName: {
    fontSize: 10,
    color: "#555",
    marginBottom: 2,
  },
  chainNameBest: {
    color: glassColors.greenDark,
    fontWeight: "600",
  },
  chainPrice: {
    fontSize: 14,
    fontWeight: "bold",
    color: "#333",
  },
  chainPriceBest: {
    color: glassColors.greenDark,
  },
  discount: {
    fontSize: 10,
    color: "#E65100",
    fontWeight: "bold",
    marginTop: 1,
  },
  discountBest: {
    color: glassColors.greenDark,
  },
  noPrices: {
    fontSize: 12,
    color: glassColors.textMuted,
    fontStyle: "italic",
  },
});
