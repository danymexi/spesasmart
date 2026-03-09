import { useState } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, View } from "react-native";
import {
  ActivityIndicator,
  Button,
  Chip,
  IconButton,
  Text,
} from "react-native-paper";
import { router } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import {
  uploadReceipt,
  bulkAddToShoppingList,
  type ReceiptItem,
  type ReceiptUploadResponse,
} from "../services/api";
import { useGlassTheme } from "../styles/useGlassTheme";

const RECEIPT_CHAINS = [
  { slug: "iperal", label: "Iperal" },
  { slug: "esselunga", label: "Esselunga" },
  { slug: "coop", label: "Coop" },
  { slug: "lidl", label: "Lidl" },
  { slug: "carrefour", label: "Carrefour" },
  { slug: "conad", label: "Conad" },
  { slug: "eurospin", label: "Eurospin" },
  { slug: "aldi", label: "Aldi" },
  { slug: "md-discount", label: "MD Discount" },
  { slug: "penny", label: "Penny Market" },
];

type Phase = "capture" | "loading" | "review";

export default function ScanReceiptScreen() {
  const { colors } = useGlassTheme();
  const [phase, setPhase] = useState<Phase>("capture");
  const [chainSlug, setChainSlug] = useState(RECEIPT_CHAINS[0].slug);
  const [receiptResult, setReceiptResult] = useState<ReceiptUploadResponse | null>(null);
  const [selectedItems, setSelectedItems] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addedCount, setAddedCount] = useState<number | null>(null);

  const handlePickFile = async (useCamera: boolean) => {
    setError(null);

    let fileUri: string | null = null;

    if (Platform.OS === "web") {
      fileUri = await new Promise<string | null>((resolve) => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "image/*";
        if (useCamera) input.setAttribute("capture", "environment");
        input.onchange = (e: any) => {
          const file = e.target?.files?.[0];
          if (file) {
            resolve(URL.createObjectURL(file));
          } else {
            resolve(null);
          }
        };
        input.click();
      });
    } else {
      const ImagePicker = await import("expo-image-picker");
      if (useCamera) {
        const perm = await ImagePicker.requestCameraPermissionsAsync();
        if (!perm.granted) {
          setError("Serve accesso alla fotocamera.");
          return;
        }
        const result = await ImagePicker.launchCameraAsync({ quality: 0.8 });
        if (!result.canceled && result.assets[0]) {
          fileUri = result.assets[0].uri;
        }
      } else {
        const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!perm.granted) {
          setError("Serve accesso alla galleria.");
          return;
        }
        const result = await ImagePicker.launchImageLibraryAsync({
          mediaTypes: ["images"],
          quality: 0.8,
        });
        if (!result.canceled && result.assets[0]) {
          fileUri = result.assets[0].uri;
        }
      }
    }

    if (!fileUri) return;

    // Start OCR
    setPhase("loading");
    try {
      const res = await uploadReceipt(fileUri, chainSlug);
      setReceiptResult(res);
      // Select all items by default
      setSelectedItems(new Set(res.items.map((_, i) => i)));
      setPhase("review");
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || "Errore OCR";
      setError(msg);
      setPhase("capture");
    }
  };

  const toggleItem = (index: number) => {
    setSelectedItems((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const handleAddToList = async () => {
    if (!receiptResult) return;
    const items = receiptResult.items
      .filter((_, i) => selectedItems.has(i))
      .map((item) => ({
        product_id: item.product_id || undefined,
        custom_name: item.product_id ? undefined : item.name,
        quantity: Math.max(1, Math.round(item.quantity)),
      }));

    if (items.length === 0) return;

    setAdding(true);
    try {
      const result = await bulkAddToShoppingList(items);
      setAddedCount(result.added);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Errore");
    }
    setAdding(false);
  };

  const resetAll = () => {
    setPhase("capture");
    setReceiptResult(null);
    setSelectedItems(new Set());
    setError(null);
    setAddedCount(null);
  };

  const selectedCount = selectedItems.size;

  return (
    <View style={[styles.container, { backgroundColor: colors.surface }]}>
      {/* Header */}
      <View style={styles.header}>
        <IconButton icon="close" size={28} onPress={() => router.back()} />
        <Text variant="titleMedium" style={{ color: colors.textPrimary, fontWeight: "bold" }}>
          Scontrino
        </Text>
        <View style={{ width: 48 }} />
      </View>

      {/* Phase: Capture */}
      {phase === "capture" && (
        <ScrollView contentContainerStyle={styles.captureContent}>
          <Text variant="bodyMedium" style={[styles.label, { color: colors.textSecondary }]}>
            Seleziona la catena:
          </Text>
          <View style={styles.chainsRow}>
            {RECEIPT_CHAINS.map((c) => (
              <Chip
                key={c.slug}
                selected={chainSlug === c.slug}
                onPress={() => setChainSlug(c.slug)}
                compact
              >
                {c.label}
              </Chip>
            ))}
          </View>

          <View style={styles.buttonsRow}>
            <Button
              mode="contained"
              icon="camera"
              onPress={() => handlePickFile(true)}
              style={[styles.captureBtn, { backgroundColor: colors.primary }]}
            >
              Fotocamera
            </Button>
            <Button
              mode="outlined"
              icon="image"
              onPress={() => handlePickFile(false)}
              style={styles.captureBtn}
            >
              Galleria
            </Button>
          </View>

          {error && (
            <Text style={[styles.errorText, { color: colors.error }]}>{error}</Text>
          )}
        </ScrollView>
      )}

      {/* Phase: Loading */}
      {phase === "loading" && (
        <View style={styles.center}>
          <ActivityIndicator size="large" />
          <Text variant="bodyLarge" style={{ color: colors.textSecondary, marginTop: 16 }}>
            Analisi scontrino...
          </Text>
          <Text variant="bodySmall" style={{ color: colors.textMuted, marginTop: 4 }}>
            Potrebbe richiedere 10-30 secondi
          </Text>
        </View>
      )}

      {/* Phase: Review */}
      {phase === "review" && receiptResult && (
        <>
          <ScrollView contentContainerStyle={styles.reviewContent}>
            {/* Receipt header */}
            <View style={[styles.receiptHeader, { backgroundColor: colors.subtleBg }]}>
              {receiptResult.store_name && (
                <Text variant="titleSmall" style={{ color: colors.textPrimary, fontWeight: "700" }}>
                  {receiptResult.store_name}
                </Text>
              )}
              <View style={styles.receiptMeta}>
                {receiptResult.date && (
                  <Text variant="bodySmall" style={{ color: colors.textMuted }}>
                    {receiptResult.date}
                  </Text>
                )}
                {receiptResult.total && (
                  <Text variant="bodySmall" style={{ color: colors.textPrimary, fontWeight: "600" }}>
                    Totale: {"\u20AC"}{receiptResult.total}
                  </Text>
                )}
              </View>
            </View>

            {/* Success message */}
            {addedCount !== null && (
              <View style={[styles.successBanner, { backgroundColor: "#E8F5E9" }]}>
                <MaterialCommunityIcons name="check-circle" size={20} color="#2E7D32" />
                <Text style={{ color: "#2E7D32", fontWeight: "600", marginLeft: 8 }}>
                  {addedCount} articoli aggiunti alla lista!
                </Text>
              </View>
            )}

            {/* Items list */}
            {receiptResult.items.map((item, index) => (
              <Pressable
                key={index}
                style={[styles.itemRow, { borderBottomColor: colors.divider }]}
                onPress={() => toggleItem(index)}
              >
                <MaterialCommunityIcons
                  name={selectedItems.has(index) ? "checkbox-marked" : "checkbox-blank-outline"}
                  size={22}
                  color={selectedItems.has(index) ? colors.primary : colors.textMuted}
                />
                <View style={styles.itemInfo}>
                  <Text
                    variant="bodyMedium"
                    style={{ color: colors.textPrimary, fontWeight: "600" }}
                    numberOfLines={2}
                  >
                    {item.name}
                  </Text>
                  {item.product_name && (
                    <Text variant="labelSmall" style={{ color: colors.textMuted }}>
                      {item.product_name}
                    </Text>
                  )}
                </View>
                <Text variant="bodyMedium" style={{ color: colors.textPrimary }}>
                  {"\u20AC"}{item.total_price}
                </Text>
              </Pressable>
            ))}

            {error && (
              <Text style={[styles.errorText, { color: colors.error, marginTop: 12 }]}>{error}</Text>
            )}
          </ScrollView>

          {/* Bottom actions */}
          <View style={[styles.bottomBar, { backgroundColor: colors.surface, borderTopColor: colors.divider }]}>
            {addedCount === null ? (
              <>
                <Button
                  mode="contained"
                  icon="cart-plus"
                  onPress={handleAddToList}
                  loading={adding}
                  disabled={selectedCount === 0 || adding}
                  style={[styles.addBtn, { backgroundColor: colors.primary }]}
                >
                  Aggiungi alla spesa ({selectedCount})
                </Button>
                <Button mode="text" onPress={resetAll}>
                  Scansiona un altro
                </Button>
              </>
            ) : (
              <>
                <Button
                  mode="contained"
                  icon="cart"
                  onPress={() => router.back()}
                  style={[styles.addBtn, { backgroundColor: colors.primary }]}
                >
                  Torna alla lista
                </Button>
                <Button mode="text" onPress={resetAll}>
                  Scansiona un altro
                </Button>
              </>
            )}
          </View>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 4,
    paddingTop: Platform.OS === "web" ? 12 : 0,
  },
  captureContent: {
    padding: 20,
    gap: 20,
  },
  label: {
    marginBottom: 4,
  },
  chainsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  buttonsRow: {
    flexDirection: "row",
    gap: 12,
    marginTop: 8,
  },
  captureBtn: {
    flex: 1,
    borderRadius: 12,
  },
  center: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  reviewContent: {
    paddingBottom: 120,
  },
  receiptHeader: {
    padding: 16,
    marginHorizontal: 12,
    marginTop: 8,
    borderRadius: 12,
  },
  receiptMeta: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 4,
  },
  successBanner: {
    flexDirection: "row",
    alignItems: "center",
    padding: 12,
    marginHorizontal: 12,
    marginTop: 8,
    borderRadius: 8,
  },
  itemRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  itemInfo: {
    flex: 1,
  },
  bottomBar: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    padding: 16,
    borderTopWidth: 1,
    gap: 4,
  },
  addBtn: {
    borderRadius: 12,
  },
  errorText: {
    textAlign: "center",
    marginTop: 8,
  },
});
