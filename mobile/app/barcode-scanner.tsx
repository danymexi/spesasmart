import { useCallback, useEffect, useRef, useState } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { ActivityIndicator, Button, IconButton, Text } from "react-native-paper";
import { router } from "expo-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  addToShoppingList,
  addToWatchlist,
  getProductByBarcode,
  type SmartSearchResult,
} from "../services/api";
import SmartCompareCard from "../components/SmartCompareCard";
import { useGlassTheme } from "../styles/useGlassTheme";
import { useAppStore } from "../stores/useAppStore";

export default function BarcodeScannerScreen() {
  const glass = useGlassTheme();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const queryClient = useQueryClient();
  const scannerRef = useRef<any>(null);
  const [scanning, setScanning] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SmartSearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const addToListMut = useMutation({
    mutationFn: (productId: string) =>
      addToShoppingList({ product_id: productId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["shoppingList"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCount"] });
    },
  });

  const addWatchlistMut = useMutation({
    mutationFn: (productId: string) => addToWatchlist(productId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlistIds"] });
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const handleScan = useCallback(async (ean: string) => {
    setScanning(false);
    setLoading(true);
    setError(null);
    try {
      const product = await getProductByBarcode(ean);
      setResult(product);
    } catch (err: any) {
      if (err.response?.status === 404) {
        setError(`Nessun prodotto trovato per il codice ${ean}`);
      } else {
        setError("Errore nella ricerca. Riprova.");
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (Platform.OS !== "web" || !scanning) return;

    let html5QrCode: any = null;

    const initScanner = async () => {
      try {
        const { Html5Qrcode } = await import("html5-qrcode");
        html5QrCode = new Html5Qrcode("barcode-reader");
        scannerRef.current = html5QrCode;

        await html5QrCode.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 280, height: 120 } },
          (decodedText: string) => {
            html5QrCode.stop().catch(() => {});
            handleScan(decodedText);
          },
          () => {} // ignore scan failures
        );
      } catch {
        setError("Impossibile accedere alla fotocamera.");
        setScanning(false);
      }
    };

    initScanner();

    return () => {
      html5QrCode?.stop?.().catch(() => {});
    };
  }, [scanning, handleScan]);

  const resetScanner = () => {
    setResult(null);
    setError(null);
    setScanning(true);
  };

  return (
    <View style={[styles.container, { backgroundColor: glass.colors.surface }]}>
      <View style={styles.header}>
        <IconButton icon="close" size={28} onPress={() => router.back()} />
        <Text variant="titleMedium" style={{ color: glass.colors.textPrimary }}>
          Scansiona Barcode
        </Text>
        <View style={{ width: 48 }} />
      </View>

      {scanning && Platform.OS === "web" && (
        <View style={styles.scannerContainer}>
          <div id="barcode-reader" style={{ width: "100%" }} />
        </View>
      )}

      {scanning && Platform.OS !== "web" && (
        <View style={styles.unsupported}>
          <Text style={{ color: glass.colors.textSecondary }}>
            Il barcode scanner e' disponibile solo su web browser.
          </Text>
        </View>
      )}

      {loading && (
        <View style={styles.center}>
          <ActivityIndicator size="large" />
          <Text style={{ color: glass.colors.textSecondary, marginTop: 12 }}>
            Cercando il prodotto...
          </Text>
        </View>
      )}

      {error && (
        <View style={styles.center}>
          <Text style={{ color: glass.colors.error, textAlign: "center", marginBottom: 16 }}>
            {error}
          </Text>
          <Button mode="contained" onPress={resetScanner}>
            Riprova
          </Button>
        </View>
      )}

      {result && (
        <View style={styles.resultContainer}>
          <SmartCompareCard result={result} />
          {isLoggedIn && (
            <View style={styles.actions}>
              <Button
                mode="contained"
                icon="cart-plus"
                onPress={() => addToListMut.mutate(result.product.id)}
                loading={addToListMut.isPending}
                style={styles.actionBtn}
              >
                Aggiungi alla spesa
              </Button>
              <Button
                mode="outlined"
                icon="heart-plus-outline"
                onPress={() => addWatchlistMut.mutate(result.product.id)}
                loading={addWatchlistMut.isPending}
                style={styles.actionBtn}
              >
                Aggiungi alla watchlist
              </Button>
            </View>
          )}
          <Button mode="text" onPress={resetScanner} style={{ marginTop: 8 }}>
            Scansiona un altro
          </Button>
        </View>
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
  scannerContainer: {
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    overflow: "hidden",
  },
  unsupported: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 40,
  },
  center: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  resultContainer: {
    flex: 1,
    padding: 16,
  },
  actions: {
    marginTop: 16,
    gap: 8,
  },
  actionBtn: {
    borderRadius: 12,
  },
});
