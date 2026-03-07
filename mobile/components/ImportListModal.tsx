import { useState } from "react";
import { StyleSheet, View } from "react-native";
import { Button, Modal, Portal, Text, TextInput } from "react-native-paper";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { importTextToList, type ImportedItem } from "../services/api";
import { glassColors } from "../styles/glassStyles";

interface ImportListModalProps {
  visible: boolean;
  onDismiss: () => void;
  listId: string;
}

export default function ImportListModal({ visible, onDismiss, listId }: ImportListModalProps) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [results, setResults] = useState<ImportedItem[] | null>(null);

  const importMutation = useMutation({
    mutationFn: () => importTextToList(listId, text),
    onSuccess: (data) => {
      setResults(data.items);
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingLists"] });
    },
  });

  const handleClose = () => {
    setText("");
    setResults(null);
    onDismiss();
  };

  return (
    <Portal>
      <Modal visible={visible} onDismiss={handleClose} contentContainerStyle={styles.modal}>
        <Text variant="titleMedium" style={styles.title}>
          Importa lista da testo
        </Text>
        <Text variant="bodySmall" style={styles.hint}>
          Scrivi o incolla una lista, ad esempio:{"\n"}
          "latte, pane, 2 yogurt, pasta, pomodori"
        </Text>

        {!results ? (
          <>
            <TextInput
              mode="outlined"
              multiline
              numberOfLines={5}
              placeholder={"latte\npane\n2 yogurt\npasta integrale\npomodori pelati"}
              value={text}
              onChangeText={setText}
              style={styles.textInput}
            />
            <View style={styles.actions}>
              <Button mode="outlined" onPress={handleClose}>
                Annulla
              </Button>
              <Button
                mode="contained"
                onPress={() => importMutation.mutate()}
                loading={importMutation.isPending}
                disabled={!text.trim() || importMutation.isPending}
                style={styles.importBtn}
              >
                Importa
              </Button>
            </View>
          </>
        ) : (
          <>
            <Text variant="bodyMedium" style={styles.resultSummary}>
              {results.length} articoli importati
            </Text>
            <View style={styles.resultList}>
              {results.map((item, i) => (
                <View key={i} style={styles.resultItem}>
                  <View style={styles.resultItemInfo}>
                    <Text variant="bodyMedium" style={styles.resultItemName}>
                      {item.name}{item.quantity > 1 ? ` x${item.quantity}` : ""}
                    </Text>
                    {item.matched_product_name && (
                      <Text variant="labelSmall" style={styles.matchBadge}>
                        Trovato: {item.matched_product_name}
                      </Text>
                    )}
                  </View>
                  <Text style={item.matched_product_id ? styles.matchDot : styles.noMatchDot}>
                    {item.matched_product_id ? "\u2713" : "\u2022"}
                  </Text>
                </View>
              ))}
            </View>
            <Button mode="contained" onPress={handleClose} style={styles.doneBtn}>
              Fatto
            </Button>
          </>
        )}
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  modal: {
    backgroundColor: "#fff",
    marginHorizontal: 20,
    borderRadius: 16,
    padding: 20,
    maxHeight: "80%",
  },
  title: {
    fontWeight: "700",
    color: glassColors.greenDark,
    marginBottom: 4,
  },
  hint: {
    color: "#888",
    marginBottom: 12,
    lineHeight: 18,
  },
  textInput: {
    minHeight: 120,
    textAlignVertical: "top",
    marginBottom: 12,
  },
  actions: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 10,
  },
  importBtn: {
    backgroundColor: glassColors.greenDark,
  },
  resultSummary: {
    fontWeight: "600",
    color: glassColors.greenDark,
    marginBottom: 12,
  },
  resultList: {
    gap: 2,
    marginBottom: 16,
  },
  resultItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    paddingHorizontal: 4,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#eee",
  },
  resultItemInfo: {
    flex: 1,
  },
  resultItemName: {
    fontWeight: "600",
    color: "#1a1a1a",
  },
  matchBadge: {
    color: glassColors.greenDark,
    marginTop: 2,
  },
  matchDot: {
    color: glassColors.greenDark,
    fontWeight: "bold",
    fontSize: 16,
  },
  noMatchDot: {
    color: "#ccc",
    fontSize: 16,
  },
  doneBtn: {
    backgroundColor: glassColors.greenDark,
  },
});
