import { FlatList, StyleSheet, TouchableOpacity, View } from "react-native";
import { Chip, Text } from "react-native-paper";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useQuery } from "@tanstack/react-query";
import { getCategoriesTree, type CategoryTreeNode } from "../services/api";
import { glassCard, glassColors } from "../styles/glassStyles";
import { useGlassTheme } from "../styles/useGlassTheme";

interface Props {
  selectedCategory: string | null;
  onSelectCategory: (name: string | null) => void;
}

export default function CategoryPicker({ selectedCategory, onSelectCategory }: Props) {
  const { colors } = useGlassTheme();
  const { data: tree } = useQuery({
    queryKey: ["categoriesTree"],
    queryFn: getCategoriesTree,
  });

  if (!tree || tree.length === 0) return null;

  // Find the selected parent node (if any)
  const selectedParent = tree.find((p) => p.name === selectedCategory);

  // When no category is selected, show tile grid
  if (!selectedCategory) {
    return (
      <FlatList
        data={tree}
        keyExtractor={(item) => item.id}
        numColumns={3}
        renderItem={({ item }) => (
          <CategoryTile category={item} onPress={() => onSelectCategory(item.name)} />
        )}
        contentContainerStyle={styles.tileGrid}
        ListHeaderComponent={
          <Text style={[styles.gridTitle, { color: colors.primary }]}>Categorie</Text>
        }
      />
    );
  }

  // When a parent is selected, show parent chips + children row
  return (
    <View>
      {/* Parent chips (horizontal) */}
      <FlatList
        horizontal
        showsHorizontalScrollIndicator={false}
        data={tree}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <Chip
            selected={selectedCategory === item.name}
            onPress={() =>
              onSelectCategory(selectedCategory === item.name ? null : item.name)
            }
            style={[
              styles.chip,
              { backgroundColor: colors.subtleBg },
              selectedCategory === item.name && { backgroundColor: colors.primarySubtle },
            ]}
            compact
          >
            {item.name} ({item.count})
          </Chip>
        )}
        contentContainerStyle={styles.chipRow}
        style={{ flexGrow: 0 }}
      />

      {/* Children sub-row (if parent has children) */}
      {selectedParent && selectedParent.children.length > 0 && (
        <FlatList
          horizontal
          showsHorizontalScrollIndicator={false}
          data={selectedParent.children}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <Chip
              style={[styles.subChip, { backgroundColor: colors.subtleBg }]}
              compact
              onPress={() => {
                // For now sub-categories are informational; pressing clears
                // In the future this could filter further
              }}
            >
              {item.name}
            </Chip>
          )}
          contentContainerStyle={styles.subChipRow}
          style={{ flexGrow: 0 }}
        />
      )}
    </View>
  );
}

function CategoryTile({ category, onPress }: { category: CategoryTreeNode; onPress: () => void }) {
  const glass = useGlassTheme();
  const { colors } = glass;
  const iconName = category.icon || "tag-outline";
  return (
    <TouchableOpacity style={[styles.tile, glass.card]} onPress={onPress} activeOpacity={0.7}>
      <MaterialCommunityIcons
        name={iconName as any}
        size={28}
        color={colors.primary}
      />
      <Text style={[styles.tileName, { color: colors.textPrimary }]} numberOfLines={1}>
        {category.name}
      </Text>
      <Text style={[styles.tileCount, { color: colors.textMuted }]}>{category.count}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  tileGrid: { paddingHorizontal: 12, paddingTop: 8, paddingBottom: 96 },
  gridTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: glassColors.greenDark,
    marginBottom: 12,
    paddingHorizontal: 4,
  },
  tile: {
    flex: 1,
    margin: 4,
    padding: 14,
    alignItems: "center",
    gap: 6,
    ...glassCard,
    minHeight: 90,
    justifyContent: "center",
  } as any,
  tileName: {
    fontSize: 12,
    fontWeight: "600",
    color: glassColors.textPrimary,
    textAlign: "center",
  },
  tileCount: {
    fontSize: 10,
    color: glassColors.textMuted,
  },
  chipRow: { paddingHorizontal: 12, paddingVertical: 4, gap: 6 },
  chip: { backgroundColor: "rgba(0,0,0,0.04)" },
  chipSelected: { backgroundColor: glassColors.greenAccent },
  subChipRow: { paddingHorizontal: 16, paddingVertical: 2, gap: 4 },
  subChip: { backgroundColor: "rgba(0,0,0,0.03)" },
});
