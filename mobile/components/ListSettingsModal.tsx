import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { Button, Modal, Portal, Text, TextInput } from "react-native-paper";
import { glassColors } from "../styles/glassStyles";
import { useGlassTheme } from "../styles/useGlassTheme";

const EMOJI_OPTIONS = [
  null, "\uD83D\uDED2", "\uD83C\uDF4E", "\uD83C\uDF3F", "\uD83C\uDF7D\uFE0F",
  "\uD83C\uDFE0", "\uD83C\uDF89", "\uD83D\uDC76", "\uD83D\uDC36", "\uD83C\uDFCB\uFE0F",
  "\u2764\uFE0F", "\u2B50", "\uD83D\uDCA1",
];

const COLOR_OPTIONS = [
  null, "#E6007E", "#3CB4E6", "#FFD200", "#49B170",
  "#6B2D8B", "#FF6F00", "#03234B",
];

interface Props {
  visible: boolean;
  onDismiss: () => void;
  onSave: (data: { name: string; emoji: string | null; color: string | null }) => void;
  initial?: { name: string; emoji: string | null; color: string | null };
  title?: string;
}

export default function ListSettingsModal({
  visible,
  onDismiss,
  onSave,
  initial,
  title = "Nuova lista",
}: Props) {
  const { colors } = useGlassTheme();
  const [name, setName] = useState(initial?.name ?? "");
  const [emoji, setEmoji] = useState<string | null>(initial?.emoji ?? null);
  const [color, setColor] = useState<string | null>(initial?.color ?? null);

  const handleSave = () => {
    if (!name.trim()) return;
    onSave({ name: name.trim(), emoji, color });
    setName("");
    setEmoji(null);
    setColor(null);
  };

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={onDismiss}
        contentContainerStyle={[styles.container, { backgroundColor: colors.surface }]}
      >
        <Text variant="titleLarge" style={[styles.title, { color: colors.textPrimary }]}>
          {title}
        </Text>

        <TextInput
          label="Nome lista"
          value={name}
          onChangeText={setName}
          mode="outlined"
          style={styles.input}
          autoFocus
        />

        <Text variant="labelLarge" style={[styles.sectionLabel, { color: colors.textSecondary }]}>
          Icona
        </Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={styles.optionRow}>
            {EMOJI_OPTIONS.map((e, i) => (
              <Pressable
                key={i}
                style={[
                  styles.emojiBtn,
                  { backgroundColor: colors.subtleBg },
                  emoji === e && [styles.optionSelected, { borderColor: colors.primaryMuted }],
                ]}
                onPress={() => setEmoji(e)}
              >
                <Text style={styles.emojiText}>{e ?? "–"}</Text>
              </Pressable>
            ))}
          </View>
        </ScrollView>

        <Text variant="labelLarge" style={[styles.sectionLabel, { color: colors.textSecondary }]}>
          Colore
        </Text>
        <View style={styles.optionRow}>
          {COLOR_OPTIONS.map((c, i) => (
            <Pressable
              key={i}
              style={[
                styles.colorBtn,
                { backgroundColor: c ?? "#ddd" },
                color === c && [styles.optionSelected, { borderColor: colors.primaryMuted }],
              ]}
              onPress={() => setColor(c)}
            />
          ))}
        </View>

        <View style={styles.actions}>
          <Button onPress={onDismiss}>Annulla</Button>
          <Button
            mode="contained"
            onPress={handleSave}
            disabled={!name.trim()}
          >
            Salva
          </Button>
        </View>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#fff",
    margin: 20,
    padding: 24,
    borderRadius: 20,
  },
  title: {
    marginBottom: 16,
    color: glassColors.textPrimary,
  },
  input: {
    marginBottom: 16,
  },
  sectionLabel: {
    marginBottom: 8,
    color: glassColors.textSecondary,
  },
  optionRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 16,
    flexWrap: "wrap",
  },
  emojiBtn: {
    width: 40,
    height: 40,
    borderRadius: 12,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.04)",
  },
  emojiText: {
    fontSize: 20,
  },
  colorBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
  },
  optionSelected: {
    borderWidth: 2,
    borderColor: glassColors.greenMedium,
  },
  actions: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 8,
    marginTop: 8,
  },
});
