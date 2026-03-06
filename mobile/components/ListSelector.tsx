import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import {
  Button,
  Dialog,
  IconButton,
  Menu,
  Portal,
  Text,
  TextInput,
} from "react-native-paper";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import {
  getShoppingLists,
  createShoppingList,
  updateShoppingList,
  deleteShoppingList,
  duplicateShoppingList,
  type ShoppingListInfo,
} from "../services/api";
import { glassColors } from "../styles/glassStyles";

interface Props {
  selectedListId: string | undefined;
  onSelectList: (listId: string | undefined) => void;
}

const EMOJI_OPTIONS = ["🛒", "🥦", "🎂", "🏠", "🎉", "💼", "🍝", "🧹"];

export default function ListSelector({ selectedListId, onSelectList }: Props) {
  const queryClient = useQueryClient();
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showRenameDialog, setShowRenameDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [menuListId, setMenuListId] = useState<string | null>(null);
  const [newListName, setNewListName] = useState("");
  const [newListEmoji, setNewListEmoji] = useState("🛒");
  const [renamingList, setRenamingList] = useState<ShoppingListInfo | null>(null);

  const { data: lists } = useQuery({
    queryKey: ["shoppingLists"],
    queryFn: () => getShoppingLists(),
  });

  const createMutation = useMutation({
    mutationFn: createShoppingList,
    onSuccess: (newList) => {
      queryClient.invalidateQueries({ queryKey: ["shoppingLists"] });
      onSelectList(newList.id);
      setShowCreateDialog(false);
      setNewListName("");
      setNewListEmoji("🛒");
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, name, emoji }: { id: string; name: string; emoji: string }) =>
      updateShoppingList(id, { name, emoji }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingLists"] });
      setShowRenameDialog(false);
      setRenamingList(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteShoppingList,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingLists"] });
      if (selectedListId === menuListId) {
        // Select first remaining list
        const remaining = (lists || []).filter((l) => l.id !== menuListId);
        onSelectList(remaining.length > 0 ? remaining[0].id : undefined);
      }
      setShowDeleteDialog(false);
      setMenuListId(null);
    },
  });

  const duplicateMutation = useMutation({
    mutationFn: ({ id }: { id: string }) => duplicateShoppingList(id),
    onSuccess: (newList) => {
      queryClient.invalidateQueries({ queryKey: ["shoppingLists"] });
      onSelectList(newList.id);
      setMenuListId(null);
    },
  });

  const handleOpenRename = (list: ShoppingListInfo) => {
    setRenamingList(list);
    setNewListName(list.name);
    setNewListEmoji(list.emoji);
    setShowRenameDialog(true);
    setMenuListId(null);
  };

  const handleOpenDelete = (listId: string) => {
    setMenuListId(listId);
    setShowDeleteDialog(true);
  };

  if (!lists || lists.length === 0) {
    return (
      <View style={styles.container}>
        <Pressable
          style={styles.createPill}
          onPress={() => setShowCreateDialog(true)}
        >
          <MaterialCommunityIcons name="plus" size={16} color={glassColors.greenDark} />
          <Text style={styles.createPillText}>Crea lista</Text>
        </Pressable>

        {/* Create dialog */}
        <Portal>
          <Dialog visible={showCreateDialog} onDismiss={() => setShowCreateDialog(false)}>
            <Dialog.Title>Nuova lista</Dialog.Title>
            <Dialog.Content>
              <TextInput
                label="Nome"
                value={newListName}
                onChangeText={setNewListName}
                mode="outlined"
                dense
              />
              <View style={styles.emojiRow}>
                {EMOJI_OPTIONS.map((e) => (
                  <Pressable
                    key={e}
                    style={[styles.emojiOption, newListEmoji === e && styles.emojiSelected]}
                    onPress={() => setNewListEmoji(e)}
                  >
                    <Text style={styles.emojiText}>{e}</Text>
                  </Pressable>
                ))}
              </View>
            </Dialog.Content>
            <Dialog.Actions>
              <Button onPress={() => setShowCreateDialog(false)}>Annulla</Button>
              <Button
                onPress={() => createMutation.mutate({ name: newListName || "La mia lista", emoji: newListEmoji })}
                loading={createMutation.isPending}
              >
                Crea
              </Button>
            </Dialog.Actions>
          </Dialog>
        </Portal>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {lists.map((list) => {
          const isSelected = list.id === selectedListId;
          return (
            <View key={list.id} style={styles.pillWrapper}>
              <Pressable
                style={[styles.listPill, isSelected && styles.listPillSelected]}
                onPress={() => onSelectList(list.id)}
                onLongPress={() => setMenuListId(list.id)}
              >
                <Text style={styles.pillEmoji}>{list.emoji}</Text>
                <Text
                  style={[styles.pillName, isSelected && styles.pillNameSelected]}
                  numberOfLines={1}
                >
                  {list.name}
                </Text>
                {list.unchecked_count > 0 && (
                  <View style={[styles.badge, isSelected && styles.badgeSelected]}>
                    <Text style={[styles.badgeText, isSelected && styles.badgeTextSelected]}>
                      {list.unchecked_count}
                    </Text>
                  </View>
                )}
              </Pressable>

              {menuListId === list.id && (
                <View style={styles.contextMenu}>
                  <Pressable style={styles.menuItem} onPress={() => handleOpenRename(list)}>
                    <MaterialCommunityIcons name="pencil" size={16} color="#333" />
                    <Text style={styles.menuItemText}>Rinomina</Text>
                  </Pressable>
                  <Pressable
                    style={styles.menuItem}
                    onPress={() => duplicateMutation.mutate({ id: list.id })}
                  >
                    <MaterialCommunityIcons name="content-copy" size={16} color="#333" />
                    <Text style={styles.menuItemText}>Duplica</Text>
                  </Pressable>
                  {lists.length > 1 && (
                    <Pressable
                      style={styles.menuItem}
                      onPress={() => handleOpenDelete(list.id)}
                    >
                      <MaterialCommunityIcons name="delete-outline" size={16} color="#C62828" />
                      <Text style={[styles.menuItemText, { color: "#C62828" }]}>Elimina</Text>
                    </Pressable>
                  )}
                  <Pressable
                    style={styles.menuItem}
                    onPress={() => setMenuListId(null)}
                  >
                    <Text style={[styles.menuItemText, { color: "#999" }]}>Chiudi</Text>
                  </Pressable>
                </View>
              )}
            </View>
          );
        })}

        <Pressable
          style={styles.createPill}
          onPress={() => setShowCreateDialog(true)}
        >
          <MaterialCommunityIcons name="plus" size={16} color={glassColors.greenDark} />
        </Pressable>
      </ScrollView>

      {/* Create dialog */}
      <Portal>
        <Dialog visible={showCreateDialog} onDismiss={() => setShowCreateDialog(false)}>
          <Dialog.Title>Nuova lista</Dialog.Title>
          <Dialog.Content>
            <TextInput
              label="Nome"
              value={newListName}
              onChangeText={setNewListName}
              mode="outlined"
              dense
            />
            <View style={styles.emojiRow}>
              {EMOJI_OPTIONS.map((e) => (
                <Pressable
                  key={e}
                  style={[styles.emojiOption, newListEmoji === e && styles.emojiSelected]}
                  onPress={() => setNewListEmoji(e)}
                >
                  <Text style={styles.emojiText}>{e}</Text>
                </Pressable>
              ))}
            </View>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowCreateDialog(false)}>Annulla</Button>
            <Button
              onPress={() => createMutation.mutate({ name: newListName || "La mia lista", emoji: newListEmoji })}
              loading={createMutation.isPending}
            >
              Crea
            </Button>
          </Dialog.Actions>
        </Dialog>

        {/* Rename dialog */}
        <Dialog visible={showRenameDialog} onDismiss={() => setShowRenameDialog(false)}>
          <Dialog.Title>Rinomina lista</Dialog.Title>
          <Dialog.Content>
            <TextInput
              label="Nome"
              value={newListName}
              onChangeText={setNewListName}
              mode="outlined"
              dense
            />
            <View style={styles.emojiRow}>
              {EMOJI_OPTIONS.map((e) => (
                <Pressable
                  key={e}
                  style={[styles.emojiOption, newListEmoji === e && styles.emojiSelected]}
                  onPress={() => setNewListEmoji(e)}
                >
                  <Text style={styles.emojiText}>{e}</Text>
                </Pressable>
              ))}
            </View>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowRenameDialog(false)}>Annulla</Button>
            <Button
              onPress={() =>
                renamingList &&
                renameMutation.mutate({
                  id: renamingList.id,
                  name: newListName,
                  emoji: newListEmoji,
                })
              }
              loading={renameMutation.isPending}
            >
              Salva
            </Button>
          </Dialog.Actions>
        </Dialog>

        {/* Delete confirmation */}
        <Dialog visible={showDeleteDialog} onDismiss={() => setShowDeleteDialog(false)}>
          <Dialog.Title>Elimina lista</Dialog.Title>
          <Dialog.Content>
            <Text>Sei sicuro di voler eliminare questa lista e tutti i suoi articoli?</Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowDeleteDialog(false)}>Annulla</Button>
            <Button
              textColor="#C62828"
              onPress={() => menuListId && deleteMutation.mutate(menuListId)}
              loading={deleteMutation.isPending}
            >
              Elimina
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  scrollContent: {
    gap: 8,
    alignItems: "center",
    paddingRight: 8,
  },
  pillWrapper: {
    position: "relative",
  },
  listPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: "rgba(0,0,0,0.05)",
    borderWidth: 1.5,
    borderColor: "transparent",
  },
  listPillSelected: {
    backgroundColor: "rgba(46,125,50,0.12)",
    borderColor: glassColors.greenDark,
  },
  pillEmoji: {
    fontSize: 16,
  },
  pillName: {
    fontSize: 13,
    fontWeight: "600",
    color: "#555",
    maxWidth: 120,
  },
  pillNameSelected: {
    color: glassColors.greenDark,
  },
  badge: {
    backgroundColor: "rgba(0,0,0,0.1)",
    borderRadius: 10,
    minWidth: 20,
    height: 20,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 6,
  },
  badgeSelected: {
    backgroundColor: glassColors.greenDark,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: "bold",
    color: "#555",
  },
  badgeTextSelected: {
    color: "#fff",
  },
  createPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 1.5,
    borderColor: glassColors.greenDark,
    borderStyle: "dashed",
  },
  createPillText: {
    fontSize: 13,
    fontWeight: "600",
    color: glassColors.greenDark,
  },
  contextMenu: {
    position: "absolute",
    top: "100%",
    left: 0,
    marginTop: 4,
    backgroundColor: "#fff",
    borderRadius: 10,
    paddingVertical: 4,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 6,
    elevation: 5,
    zIndex: 30,
    minWidth: 140,
  },
  menuItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  menuItemText: {
    fontSize: 13,
    color: "#333",
  },
  emojiRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 16,
  },
  emojiOption: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.05)",
  },
  emojiSelected: {
    backgroundColor: "rgba(46,125,50,0.15)",
    borderWidth: 2,
    borderColor: glassColors.greenDark,
  },
  emojiText: {
    fontSize: 20,
  },
});
