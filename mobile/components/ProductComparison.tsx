import { StyleSheet, View } from "react-native";
import { Text, useTheme, ActivityIndicator } from "react-native-paper";
import { useQuery } from "@tanstack/react-query";
import { getProductCompare } from "../services/api";
import { glassPanel, glassColors } from "../styles/glassStyles";

interface Props {
  productId: string;
}

const CHAIN_COLORS: Record<string, string> = {
  Esselunga: "#D32F2F",
  Lidl: "#0039A6",
  Coop: "#E53935",
  Iperal: "#1565C0",
  Carrefour: "#004E9A",
  Conad: "#E31E24",
  Eurospin: "#1A4D8F",
  Aldi: "#00205B",
  "MD Discount": "#E5007D",
  "Penny Market": "#CD1719",
  "PAM Panorama": "#E4002B",
};

export default function ProductComparison({ productId }: Props) {
  const theme = useTheme();

  const { data, isLoading } = useQuery({
    queryKey: ["comparison", productId],
    queryFn: () => getProductCompare(productId),
    enabled: !!productId,
  });
  const offers = data?.offers ?? [];

  if (isLoading) {
    return <ActivityIndicator style={styles.loader} />;
  }

  if (!offers || offers.length === 0) {
    return (
      <View style={styles.container}>
        <Text variant="bodyMedium" style={styles.emptyText}>
          Nessuna offerta attiva per il confronto
        </Text>
      </View>
    );
  }

  const maxPrice = Math.max(...offers.map((o: any) => Number(o.offer_price)));

  return (
    <View style={styles.container}>
      {offers.map((offer: any, index: number) => {
        const price = Number(offer.offer_price);
        const barWidth = maxPrice > 0 ? (price / maxPrice) * 100 : 0;
        const isBest = index === 0;
        const chainColor = CHAIN_COLORS[offer.chain_name] ?? "#666";

        return (
          <View key={`${offer.chain_name}-${index}`} style={styles.row}>
            <View style={styles.chainLabel}>
              <Text
                variant="bodyMedium"
                style={[styles.chainName, isBest && { fontWeight: "bold" }]}
              >
                {offer.chain_name}
              </Text>
              {offer.product_name && (
                <Text variant="labelSmall" style={styles.productName} numberOfLines={1}>
                  {offer.product_name}
                </Text>
              )}
            </View>
            <View style={styles.barContainer}>
              <View
                style={[
                  styles.bar,
                  {
                    width: `${barWidth}%`,
                    backgroundColor: isBest ? theme.colors.primary : chainColor,
                    opacity: isBest ? 1 : 0.6,
                  },
                ]}
              />
            </View>
            <View style={styles.priceLabel}>
              <Text
                variant="bodyMedium"
                style={[
                  styles.price,
                  isBest && { color: theme.colors.primary, fontWeight: "bold" },
                ]}
              >
                {"\u20AC"}{price.toFixed(2)}
              </Text>
              {isBest && (
                <Text variant="labelSmall" style={styles.bestLabel}>
                  MIGLIORE
                </Text>
              )}
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: 4,
  },
  loader: { marginVertical: 20 },
  emptyText: { color: "#666" },
  row: { flexDirection: "row", alignItems: "center", marginBottom: 10 },
  chainLabel: { width: 90 },
  chainName: { fontSize: 13, color: "#1a1a1a" },
  productName: { fontSize: 11, color: "#888", marginTop: 1 },
  barContainer: {
    flex: 1,
    height: 24,
    backgroundColor: glassColors.subtleBg,
    borderRadius: 14,
    overflow: "hidden",
  },
  bar: { height: "100%", borderRadius: 14 },
  priceLabel: { width: 80, alignItems: "flex-end", paddingLeft: 8 },
  price: { fontSize: 14 },
  bestLabel: { color: "#2E7D32", fontSize: 9, fontWeight: "bold" },
});
