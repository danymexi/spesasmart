import { useCallback } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { IconButton, Text } from "react-native-paper";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getShoppingLists, type ShoppingListMeta } from "../services/api";
import { useAppStore } from "../stores/useAppStore";
import { glassColors } from "../styles/glassStyles";
import { useGlassTheme } from "../styles/useGlassTheme";

interface Props {
  onCreateList: () => void;
}

export default function ListPicker({ onCreateList }: Props) {
  const { colors } = useGlassTheme();
  const activeListId = useAppStore((s) => s.activeListId);
  const setActiveListId = useAppStore((s) => s.setActiveListId);
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);

  const { data: lists } = useQuery({
    queryKey: ["shoppingLists"],
    queryFn: () => getShoppingLists(),
    enabled: isLoggedIn,
  });

  const handleSelect = useCallback(
    (id: string) => setActiveListId(id),
    [setActiveListId]
  );

  if (!lists || lists.length <= 1) return null;

  return (
    <View style={styles.wrapper}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scroll}
      >
        {lists.map((list) => {
          const isActive = list.id === activeListId || (!activeListId && list.sort_order === 0);
          return (
            <Pressable
              key={list.id}
              style={[
                styles.chip,
                { backgroundColor: colors.subtleBg, borderColor: colors.subtleBorder },
                isActive && { backgroundColor: colors.primarySubtleStrong, borderColor: colors.primarySubtle },
              ]}
              onPress={() => handleSelect(list.id)}
            >
              {list.emoji ? (
                <Text style={styles.emoji}>{list.emoji}</Text>
              ) : null}
              <Text
                style={[
                  styles.chipText,
                  { color: colors.textSecondary },
                  isActive && { color: colors.primary, fontWeight: "700" },
                ]}
                numberOfLines={1}
              >
                {list.name}
              </Text>
              {list.unchecked_count > 0 && (
                <View style={[
                  styles.badge,
                  { backgroundColor: colors.subtleBg },
                  isActive && { backgroundColor: colors.primarySubtle },
                ]}>
                  <Text style={[
                    styles.badgeText,
                    { color: colors.textMuted },
                    isActive && { color: colors.primary },
                  ]}>
                    {list.unchecked_count}
                  </Text>
                </View>
              )}
            </Pressable>
          );
        })}
        <IconButton
          icon="plus"
          size={18}
          style={[styles.addBtn, { backgroundColor: colors.subtleBg }]}
          onPress={onCreateList}
        />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    paddingBottom: 4,
  },
  scroll: {
    paddingHorizontal: 12,
    gap: 8,
    alignItems: "center",
  },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: "rgba(255,255,255,0.5)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.4)",
    gap: 6,
  },
  chipActive: {
    backgroundColor: glassColors.greenAccentStrong,
    borderColor: "rgba(46,125,50,0.3)",
  },
  chipText: {
    fontSize: 14,
    color: glassColors.textSecondary,
    fontWeight: "500",
    maxWidth: 120,
  },
  chipTextActive: {
    color: glassColors.greenDark,
    fontWeight: "700",
  },
  emoji: {
    fontSize: 16,
  },
  badge: {
    backgroundColor: "rgba(0,0,0,0.08)",
    borderRadius: 10,
    minWidth: 20,
    height: 20,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 5,
  },
  badgeActive: {
    backgroundColor: "rgba(27,94,32,0.2)",
  },
  badgeText: {
    fontSize: 11,
    fontWeight: "700",
    color: glassColors.textMuted,
  },
  badgeTextActive: {
    color: glassColors.greenDark,
  },
  addBtn: {
    margin: 0,
    backgroundColor: "rgba(255,255,255,0.4)",
  },
});
