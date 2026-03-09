import { ScrollView, StyleSheet, TouchableOpacity, View } from "react-native";
import { ActivityIndicator, Chip, Text } from "react-native-paper";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useQuery } from "@tanstack/react-query";
import { getCatalogHome, type CatalogHomeCategory } from "../services/api";
import OfferCard from "./OfferCard";
import { glassCard, glassChip, glassColors } from "../styles/glassStyles";
import { useGlassTheme } from "../styles/useGlassTheme";

interface Props {
  onSelectCategory: (name: string) => void;
}

export default function CatalogHome({ onSelectCategory }: Props) {
  const glass = useGlassTheme();
  const { colors } = glass;

  const { data, isLoading } = useQuery({
    queryKey: ["catalogHome"],
    queryFn: getCatalogHome,
    staleTime: 300_000,
  });

  if (isLoading) {
    return <ActivityIndicator style={styles.loader} />;
  }

  if (!data) return null;

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      showsVerticalScrollIndicator={false}
    >
      {/* Featured offers */}
      {data.featured.length > 0 && (
        <>
          <Text variant="titleMedium" style={[styles.sectionTitle, { color: colors.primary }]}>
            Offerte imperdibili
          </Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.horizontalList}
          >
            {data.featured.map((offer) => (
              <View key={offer.id} style={styles.offerCardWrap}>
                <OfferCard offer={offer} compact />
              </View>
            ))}
          </ScrollView>
        </>
      )}

      {/* Category chips */}
      {data.categories.length > 0 && (
        <>
          <Text variant="titleMedium" style={[styles.sectionTitle, { color: colors.primary }]}>
            Categorie
          </Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chipList}
          >
            {data.categories.map((cat) => (
              <Chip
                key={cat.slug}
                icon={() => (
                  <MaterialCommunityIcons
                    name={cat.icon as any}
                    size={16}
                    color={colors.primary}
                  />
                )}
                onPress={() => onSelectCategory(cat.name)}
                style={[styles.catChip, glass.chip]}
                compact
              >
                {cat.name}
              </Chip>
            ))}
          </ScrollView>
        </>
      )}

      {/* Per-category sections */}
      {data.categories.map((cat) => (
        <CategorySection
          key={cat.slug}
          category={cat}
          onViewAll={() => onSelectCategory(cat.name)}
        />
      ))}

      <View style={styles.bottomPad} />
    </ScrollView>
  );
}

function CategorySection({
  category,
  onViewAll,
}: {
  category: CatalogHomeCategory;
  onViewAll: () => void;
}) {
  const glass = useGlassTheme();
  const { colors } = glass;

  if (category.offers.length === 0) return null;

  return (
    <View style={styles.section}>
      <TouchableOpacity
        style={styles.sectionHeader}
        onPress={onViewAll}
        activeOpacity={0.7}
      >
        <View style={styles.sectionHeaderLeft}>
          <MaterialCommunityIcons
            name={category.icon as any}
            size={20}
            color={colors.primary}
          />
          <Text variant="titleSmall" style={[styles.sectionName, { color: colors.textPrimary }]}>
            {category.name}
          </Text>
          <Text variant="labelSmall" style={{ color: colors.textMuted }}>
            ({category.count})
          </Text>
        </View>
        <View style={styles.viewAllBtn}>
          <Text variant="labelSmall" style={{ color: colors.primary }}>
            Vedi tutti
          </Text>
          <MaterialCommunityIcons name="chevron-right" size={16} color={colors.primary} />
        </View>
      </TouchableOpacity>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.horizontalList}
      >
        {category.offers.map((offer) => (
          <View key={offer.id} style={styles.offerCardWrap}>
            <OfferCard offer={offer} compact />
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingTop: 4,
  },
  loader: {
    marginTop: 40,
  },
  sectionTitle: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
    fontWeight: "700",
  },
  horizontalList: {
    paddingHorizontal: 12,
  },
  offerCardWrap: {
    width: 260,
    marginRight: 12,
  },
  chipList: {
    paddingHorizontal: 12,
    gap: 6,
    paddingBottom: 4,
  },
  catChip: {
    ...glassChip,
  } as any,
  section: {
    marginTop: 12,
  },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  sectionHeaderLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  sectionName: {
    fontWeight: "600",
  },
  viewAllBtn: {
    flexDirection: "row",
    alignItems: "center",
  },
  bottomPad: {
    height: 96,
  },
});
