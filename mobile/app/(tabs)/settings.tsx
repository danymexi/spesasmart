import { useState, useEffect, useRef, useCallback } from "react";
import { ActivityIndicator, Image, ScrollView, StyleSheet, View, Alert, Platform, Pressable } from "react-native";
import { Button, Chip, IconButton, List, Portal, Snackbar, Switch, Text, TextInput, useTheme } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";

function showAlert(title: string, message: string) {
  if (Platform.OS === "web") {
    window.alert(`${title}\n\n${message}`);
  } else {
    Alert.alert(title, message);
  }
}
import { useAppStore } from "../../stores/useAppStore";
import { registerUser, loginUser, claimGuestAccount, googleAuth, getUserBrands, addUserBrand, removeUserBrand, getBrands, updateUserProfile, getMe, getPreferredChains, updatePreferredChains, getNearbyStores, updateUserLocation, getSupermarketAccounts, removeSupermarketAccount, triggerPurchaseSync, startRemoteLogin, sendRemoteAction, getRemoteStatus, cancelRemoteLogin, fetchRemoteScreenshot, uploadReceipt } from "../../services/api";
import type { NearbyChainInfo, SupermarketAccount, ReceiptItem, ReceiptUploadResponse } from "../../services/api";
import { registerForPushNotifications } from "../../services/notifications";
import { glassPanel, glassColors, glassCard } from "../../styles/glassStyles";

export default function SettingsScreen() {
  const theme = useTheme();
  const router = useRouter();
  const { isLoggedIn, isGuest, userEmail, setAuth, logout, themeMode, setThemeMode } = useAppStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [brandInput, setBrandInput] = useState("");
  const [snackMessage, setSnackMessage] = useState("");
  const [snackVisible, setSnackVisible] = useState(false);

  const queryClient = useQueryClient();

  // Initialize Google Sign-In on web
  useEffect(() => {
    if (Platform.OS !== "web" || typeof window === "undefined") return;
    const handleGoogleCredential = async (response: any) => {
      try {
        const res = await googleAuth(response.credential);
        setAuth(res.access_token, res.user.id, res.user.email ?? "");
        showAlert("Accesso con Google", "Hai effettuato l'accesso con Google.");
      } catch {
        setError("Errore durante l'accesso con Google.");
      }
    };
    // If GSI script is loaded, initialize
    if ((window as any).google?.accounts) {
      (window as any).google.accounts.id.initialize({
        client_id: process.env.EXPO_PUBLIC_GOOGLE_CLIENT_ID || "",
        callback: handleGoogleCredential,
      });
    }
  }, [setAuth]);

  // Fetch user profile for notification_mode
  const { data: userProfile } = useQuery({
    queryKey: ["userProfile"],
    queryFn: getMe,
    enabled: isLoggedIn,
  });

  const notificationModeMutation = useMutation({
    mutationFn: (mode: string) => updateUserProfile({ notification_mode: mode }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userProfile"] });
      setSnackMessage(
        userProfile?.notification_mode === "instant"
          ? "Riepilogo settimanale attivato"
          : "Notifiche immediate attivate"
      );
      setSnackVisible(true);
    },
  });

  // Brand queries
  const { data: userBrands } = useQuery({
    queryKey: ["userBrands"],
    queryFn: getUserBrands,
    enabled: isLoggedIn,
  });

  const { data: brandSuggestions } = useQuery({
    queryKey: ["brandSuggestions", brandInput],
    queryFn: () => getBrands(brandInput, 10),
    enabled: isLoggedIn && brandInput.length >= 2,
  });

  const addBrandMutation = useMutation({
    mutationFn: (brandName: string) => addUserBrand(brandName),
    onSuccess: (_data, brandName) => {
      queryClient.invalidateQueries({ queryKey: ["userBrands"] });
      queryClient.invalidateQueries({ queryKey: ["brandDeals"] });
      setBrandInput("");
      setSnackMessage(`"${brandName}" aggiunta alle marche preferite`);
      setSnackVisible(true);
    },
    onError: (err: any) => {
      if (err.response?.status === 409) {
        setSnackMessage("Marca gia' salvata");
      } else {
        setSnackMessage("Errore nell'aggiunta della marca");
      }
      setSnackVisible(true);
    },
  });

  const removeBrandMutation = useMutation({
    mutationFn: (brandId: string) => removeUserBrand(brandId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userBrands"] });
      queryClient.invalidateQueries({ queryKey: ["brandDeals"] });
      setSnackMessage("Marca rimossa");
      setSnackVisible(true);
    },
  });

  const handleAddBrand = (name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    addBrandMutation.mutate(trimmed);
  };

  const handleRegister = async () => {
    setError(null);
    setLoading(true);
    try {
      // If guest, claim the existing account; otherwise create new
      const res = isGuest
        ? await claimGuestAccount(email, password)
        : await registerUser(email, password);
      setAuth(res.access_token, res.user.id, res.user.email!);
      setEmail("");
      setPassword("");
      showAlert(
        isGuest ? "Account creato" : "Registrazione completata",
        isGuest
          ? "I tuoi dati sono stati salvati. Ora puoi accedere da qualsiasi dispositivo."
          : "Il tuo account è stato creato.",
      );
    } catch (err: any) {
      if (err.response?.status === 409) {
        setError("Email già registrata. Prova ad accedere.");
      } else if (err.response?.status === 400) {
        setError(err.response.data?.detail || "Dati non validi.");
      } else {
        setError("Errore di rete. Riprova.");
      }
    }
    setLoading(false);
  };

  const handleLogin = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await loginUser(email, password);
      setAuth(res.access_token, res.user.id, res.user.email!);
      setEmail("");
      setPassword("");
    } catch (err: any) {
      if (err.response?.status === 401) {
        setError("Email o password errati.");
      } else {
        setError("Errore di rete. Riprova.");
      }
    }
    setLoading(false);
  };

  const handleLogout = () => {
    logout();
    showAlert("Disconnesso", "Hai effettuato il logout.");
  };

  const handleEnablePush = async () => {
    if (!isLoggedIn) return;
    const token = await registerForPushNotifications(useAppStore.getState().userId);
    if (token) {
      setPushEnabled(true);
      showAlert("Notifiche attivate", "Riceverai notifiche per le offerte.");
    } else {
      showAlert("Errore", "Impossibile attivare le notifiche push.");
    }
  };

  return (
    <ScrollView style={styles.container}>
      {/* Profile section */}
      <View style={styles.section}>
        <List.Section>
          <List.Subheader style={styles.listSubheader}>Profilo</List.Subheader>
          {isLoggedIn && !isGuest ? (
            <View style={styles.loggedInSection}>
              <List.Item
                title="Email"
                description={userEmail}
                titleStyle={styles.listTitle}
                descriptionStyle={styles.listDescription}
                left={(props) => <List.Icon {...props} icon="account" />}
              />
              <Button
                mode="outlined"
                onPress={handleLogout}
                style={styles.logoutButton}
                icon="logout"
              >
                Esci
              </Button>
            </View>
          ) : (
            <View style={styles.createSection}>
              {isGuest && (
                <View style={styles.guestBanner}>
                  <Text variant="titleSmall" style={styles.guestBannerTitle}>
                    Stai usando un account ospite
                  </Text>
                  <Text variant="bodySmall" style={styles.guestBannerText}>
                    Registrati per salvare i tuoi dati e accedere da altri dispositivi.
                  </Text>
                </View>
              )}
              <Text variant="bodyMedium" style={styles.createText}>
                {isGuest
                  ? "Crea il tuo account per non perdere le tue liste e preferenze."
                  : "Accedi o registrati per salvare la tua lista e ricevere notifiche."}
              </Text>
              {error && (
                <Text variant="bodySmall" style={styles.errorText}>
                  {error}
                </Text>
              )}
              <Button
                mode="outlined"
                icon="google"
                onPress={async () => {
                  setError(null);
                  setLoading(true);
                  try {
                    // Web-based Google Sign-In via popup
                    if (Platform.OS === "web" && typeof window !== "undefined" && (window as any).google?.accounts) {
                      // GSI library loaded — prompt
                      (window as any).google.accounts.id.prompt();
                    } else {
                      setError("Google Sign-In non disponibile. Configura il Google Client ID.");
                    }
                  } catch {
                    setError("Errore con Google Sign-In.");
                  }
                  setLoading(false);
                }}
                loading={loading}
                style={styles.googleButton}
              >
                Accedi con Google
              </Button>
              <Text variant="labelSmall" style={styles.orDivider}>oppure</Text>
              <TextInput
                label="Email"
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                mode="outlined"
                style={styles.input}
              />
              <TextInput
                label="Password"
                value={password}
                onChangeText={setPassword}
                secureTextEntry
                mode="outlined"
                style={styles.input}
              />
              <View style={styles.buttonRow}>
                {!isGuest && (
                  <Button
                    mode="contained"
                    onPress={handleLogin}
                    loading={loading}
                    disabled={!email || !password || loading}
                    style={styles.authButton}
                  >
                    Accedi
                  </Button>
                )}
                <Button
                  mode={isGuest ? "contained" : "outlined"}
                  onPress={handleRegister}
                  loading={loading}
                  disabled={!email || !password || loading}
                  style={styles.authButton}
                >
                  {isGuest ? "Crea Account" : "Registrati"}
                </Button>
              </View>
            </View>
          )}
        </List.Section>
      </View>

      {/* Theme */}
      <View style={styles.section}>
        <List.Section>
          <List.Subheader style={styles.listSubheader}>Aspetto</List.Subheader>
          <View style={{ flexDirection: "row", gap: 8, paddingHorizontal: 16, paddingBottom: 12 }}>
            {(["system", "light", "dark"] as const).map((mode) => {
              const labels = { system: "Sistema", light: "Chiaro", dark: "Scuro" };
              const icons = { system: "cellphone", light: "white-balance-sunny", dark: "weather-night" };
              return (
                <Chip
                  key={mode}
                  icon={icons[mode]}
                  selected={themeMode === mode}
                  onPress={() => setThemeMode(mode)}
                  style={{ flex: 1 }}
                >
                  {labels[mode]}
                </Chip>
              );
            })}
          </View>
        </List.Section>
      </View>

      {/* Notifications */}
      <View style={styles.section}>
        <List.Section>
          <List.Subheader style={styles.listSubheader}>Notifiche</List.Subheader>
          <List.Item
            title="Notifiche Push"
            description="Ricevi avvisi quando i tuoi prodotti sono in offerta"
            titleStyle={styles.listTitle}
            descriptionStyle={styles.listDescription}
            left={(props) => <List.Icon {...props} icon="bell" />}
            right={() => (
              <Switch
                value={pushEnabled}
                onValueChange={handleEnablePush}
                disabled={!isLoggedIn}
              />
            )}
          />
          <List.Item
            title="Telegram Bot"
            description="Cerca @SpesaSmartBot su Telegram"
            titleStyle={styles.listTitle}
            descriptionStyle={styles.listDescription}
            left={(props) => <List.Icon {...props} icon="send" />}
          />
          <List.Item
            title="Riepilogo settimanale"
            description={
              userProfile?.notification_mode === "digest"
                ? "Attivo: ricevi un riepilogo ogni lunedi'"
                : "Disattivo: ricevi notifiche immediate"
            }
            titleStyle={styles.listTitle}
            descriptionStyle={styles.listDescription}
            left={(props) => <List.Icon {...props} icon="calendar-week" />}
            right={() => (
              <Switch
                value={userProfile?.notification_mode === "digest"}
                onValueChange={(v) =>
                  notificationModeMutation.mutate(v ? "digest" : "instant")
                }
                disabled={!isLoggedIn || notificationModeMutation.isPending}
              />
            )}
          />
        </List.Section>
      </View>

      {/* Marche Preferite */}
      {isLoggedIn && (
        <View style={styles.section}>
          <List.Section>
            <List.Subheader style={styles.listSubheader}>Marche Preferite</List.Subheader>
            <View style={styles.brandInputRow}>
              <TextInput
                label="Aggiungi marca"
                value={brandInput}
                onChangeText={setBrandInput}
                mode="outlined"
                style={styles.brandInput}
                dense
              />
              <Button
                mode="contained"
                onPress={() => handleAddBrand(brandInput)}
                disabled={!brandInput.trim() || addBrandMutation.isPending}
                compact
                style={styles.brandAddButton}
              >
                Aggiungi
              </Button>
            </View>

            {/* Autocomplete suggestions */}
            {brandInput.length >= 2 && brandSuggestions && brandSuggestions.length > 0 && (
              <View style={styles.suggestionsRow}>
                {brandSuggestions.map((b) => (
                  <Chip
                    key={b.name}
                    onPress={() => handleAddBrand(b.name)}
                    style={styles.suggestionChip}
                    compact
                  >
                    {b.name} ({b.count})
                  </Chip>
                ))}
              </View>
            )}

            {/* Saved brands list */}
            {userBrands && userBrands.length > 0 ? (
              userBrands.map((ub) => (
                <List.Item
                  key={ub.id}
                  title={ub.brand_name}
                  description={ub.category || undefined}
                  titleStyle={styles.listTitle}
                  descriptionStyle={styles.listDescription}
                  left={(props) => <List.Icon {...props} icon="tag-heart" />}
                  right={() => (
                    <Button
                      mode="text"
                      compact
                      onPress={() => removeBrandMutation.mutate(ub.id)}
                      textColor="#D32F2F"
                      icon="close"
                    >
                      {""}
                    </Button>
                  )}
                />
              ))
            ) : (
              <Text variant="bodySmall" style={styles.brandEmptyText}>
                Nessuna marca salvata. Aggiungi le tue marche preferite per ricevere notifiche.
              </Text>
            )}
          </List.Section>
        </View>
      )}

      {/* Account Supermercato (Purchase History) */}
      {isLoggedIn && (
        <View style={styles.section}>
          <List.Section>
            <List.Subheader style={styles.listSubheader}>Account Supermercato</List.Subheader>
            <Text variant="bodySmall" style={styles.brandEmptyText}>
              Collega il tuo account per scaricare lo storico ordini e ricevere suggerimenti personalizzati.
            </Text>
            <SupermarketAccountsSection />
            <Button
              mode="outlined"
              icon="history"
              onPress={() => router.push("/purchases")}
              style={{ marginHorizontal: 16, marginTop: 8, marginBottom: 12 }}
            >
              Storico Acquisti
            </Button>
          </List.Section>
        </View>
      )}

      {/* Supermercati (Geolocation + Chains) */}
      <View style={styles.section}>
        <List.Section>
          <List.Subheader style={styles.listSubheader}>I Tuoi Supermercati</List.Subheader>
          <NearbyStoresSelector isLoggedIn={isLoggedIn} />
          {isLoggedIn && <ReceiptUploadSection />}
          {isLoggedIn && Platform.OS === "web" && <EsselungaBookmarkletSection />}
        </List.Section>
      </View>

      {/* App info */}
      <View style={styles.section}>
        <List.Section>
          <List.Subheader style={styles.listSubheader}>Info</List.Subheader>
          <List.Item
            title="Versione"
            description="1.0.0"
            titleStyle={styles.listTitle}
            descriptionStyle={styles.listDescription}
            left={(props) => <List.Icon {...props} icon="information" />}
          />
          <List.Item
            title="SpesaSmart"
            description="Confronto prezzi supermercati"
            titleStyle={styles.listTitle}
            descriptionStyle={styles.listDescription}
            left={(props) => <List.Icon {...props} icon="cart" />}
          />
        </List.Section>
        {Platform.OS === "web" && (
          <Button
            mode="outlined"
            icon="refresh"
            onPress={async () => {
              if ("serviceWorker" in navigator) {
                const regs = await navigator.serviceWorker.getRegistrations();
                for (const reg of regs) await reg.unregister();
              }
              const keys = await caches.keys();
              for (const key of keys) await caches.delete(key);
              window.location.reload();
            }}
            style={styles.reloadButton}
          >
            Ricarica App
          </Button>
        )}
      </View>

      {/* Admin link (only for admin users) */}
      {userProfile?.is_admin && (
        <View style={styles.section}>
          <List.Section>
            <List.Subheader style={styles.listSubheader}>Amministrazione</List.Subheader>
            <List.Item
              title="Admin Panel"
              description="Scraping, statistiche, prodotti"
              titleStyle={styles.listTitle}
              descriptionStyle={styles.listDescription}
              left={(props) => <List.Icon {...props} icon="shield-crown" />}
              onPress={() => router.push("/admin")}
            />
          </List.Section>
        </View>
      )}

      <View style={styles.bottomPadding} />

      <Snackbar
        visible={snackVisible}
        onDismiss={() => setSnackVisible(false)}
        duration={2500}
      >
        {snackMessage}
      </Snackbar>
    </ScrollView>
  );
}

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
  { slug: "pam", label: "PAM Panorama" },
];

interface SelectedFile {
  uri: string;
  isPdf: boolean;
  name: string;
}

interface UploadResult {
  items: ReceiptItem[];
  store_name: string | null;
  date: string | null;
  total: string | null;
}

function ReceiptUploadSection() {
  const queryClient = useQueryClient();
  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([]);
  const [chainSlug, setChainSlug] = useState(RECEIPT_CHAINS[0].slug);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");
  const [results, setResults] = useState<UploadResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  const pickFiles = async () => {
    setError(null);
    setResults([]);

    if (Platform.OS === "web") {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "image/*,application/pdf";
      input.multiple = true;
      input.onchange = (e: any) => {
        const files = e.target?.files;
        if (files && files.length > 0) {
          const newFiles: SelectedFile[] = [];
          for (let i = 0; i < files.length; i++) {
            const f = files[i];
            newFiles.push({
              uri: URL.createObjectURL(f),
              isPdf: f.type === "application/pdf" || f.name?.toLowerCase().endsWith(".pdf"),
              name: f.name || `file_${i + 1}`,
            });
          }
          setSelectedFiles((prev) => [...prev, ...newFiles]);
        }
      };
      input.click();
      return;
    }

    const ImagePicker = await import("expo-image-picker");
    const permResult = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permResult.granted) {
      showAlert("Permesso negato", "Serve accesso alla galleria per caricare scontrini.");
      return;
    }

    const pickerResult = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsMultipleSelection: true,
      quality: 0.8,
    });

    if (!pickerResult.canceled && pickerResult.assets.length > 0) {
      const newFiles = pickerResult.assets.map((a, i) => ({
        uri: a.uri,
        isPdf: false,
        name: a.fileName || `foto_${i + 1}`,
      }));
      setSelectedFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const takePhoto = async () => {
    setError(null);

    if (Platform.OS === "web") {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "image/*";
      input.setAttribute("capture", "environment");
      input.onchange = (e: any) => {
        const file = e.target?.files?.[0];
        if (file) {
          setSelectedFiles((prev) => [...prev, {
            uri: URL.createObjectURL(file),
            isPdf: false,
            name: file.name || "foto",
          }]);
        }
      };
      input.click();
      return;
    }

    const ImagePicker = await import("expo-image-picker");
    const permResult = await ImagePicker.requestCameraPermissionsAsync();
    if (!permResult.granted) {
      showAlert("Permesso negato", "Serve accesso alla fotocamera per scattare foto.");
      return;
    }

    const pickerResult = await ImagePicker.launchCameraAsync({
      quality: 0.8,
    });

    if (!pickerResult.canceled && pickerResult.assets[0]) {
      setSelectedFiles((prev) => [...prev, {
        uri: pickerResult.assets[0].uri,
        isPdf: false,
        name: pickerResult.assets[0].fileName || "foto",
      }]);
    }
  };

  const removeFile = (idx: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setError(null);
    setResults([]);

    const allResults: UploadResult[] = [];
    let hasError = false;

    for (let i = 0; i < selectedFiles.length; i++) {
      setUploadProgress(`Analisi ${i + 1}/${selectedFiles.length}...`);
      try {
        const res = await uploadReceipt(selectedFiles[i].uri, chainSlug);
        allResults.push({
          items: res.items,
          store_name: res.store_name,
          date: res.date,
          total: res.total,
        });
      } catch (e: any) {
        const msg = e?.response?.data?.detail || e?.message || "Errore";
        setError(`Errore file ${i + 1} (${selectedFiles[i].name}): ${msg}`);
        hasError = true;
        break;
      }
    }

    if (allResults.length > 0) {
      setResults(allResults);
      queryClient.invalidateQueries({ queryKey: ["purchases"] });
    }

    setUploading(false);
    setUploadProgress("");
  };

  const reset = () => {
    setSelectedFiles([]);
    setResults([]);
    setError(null);
    setUploadProgress("");
  };

  const totalItems = results.reduce((sum, r) => sum + r.items.length, 0);

  return (
    <View style={receiptStyles.container}>
      <View style={receiptStyles.header}>
        <Text style={receiptStyles.title}>Carica scontrini</Text>
        <Text style={receiptStyles.subtitle}>
          Foto, immagini o PDF (anche multipli)
        </Text>
      </View>

      {results.length === 0 && (
        <>
          <View style={receiptStyles.buttonRow}>
            <Button
              mode="outlined"
              icon="camera"
              onPress={takePhoto}
              compact
              disabled={uploading}
              style={receiptStyles.pickButton}
            >
              Fotocamera
            </Button>
            <Button
              mode="outlined"
              icon="file-multiple"
              onPress={pickFiles}
              compact
              disabled={uploading}
              style={receiptStyles.pickButton}
            >
              File / Galleria
            </Button>
          </View>

          {selectedFiles.length > 0 && (
            <View style={{ marginTop: 10 }}>
              {selectedFiles.map((f, idx) => (
                <View key={idx} style={receiptStyles.fileRow}>
                  <Text style={receiptStyles.fileName} numberOfLines={1}>
                    {f.isPdf ? "PDF" : "IMG"} — {f.name}
                  </Text>
                  <IconButton
                    icon="close"
                    size={16}
                    onPress={() => removeFile(idx)}
                    disabled={uploading}
                  />
                </View>
              ))}

              <View style={receiptStyles.chainSelector}>
                <Text style={receiptStyles.chainLabel}>Catena:</Text>
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
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
              </View>

              <View style={receiptStyles.buttonRow}>
                <Button
                  mode="contained"
                  icon="upload"
                  onPress={handleUpload}
                  loading={uploading}
                  disabled={uploading}
                  style={{ flex: 1 }}
                >
                  {uploading ? uploadProgress : `Carica ${selectedFiles.length} scontrin${selectedFiles.length === 1 ? "o" : "i"}`}
                </Button>
                <Button
                  mode="text"
                  onPress={reset}
                  disabled={uploading}
                >
                  Annulla
                </Button>
              </View>
            </View>
          )}
        </>
      )}

      {error && (
        <View style={receiptStyles.errorBox}>
          <Text style={receiptStyles.errorText}>{error}</Text>
          <Button mode="text" compact onPress={reset}>Riprova</Button>
        </View>
      )}

      {results.length > 0 && (
        <View style={receiptStyles.resultBox}>
          {results.map((result, rIdx) => (
            <View key={rIdx} style={rIdx > 0 ? { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: "rgba(0,0,0,0.08)" } : undefined}>
              <View style={receiptStyles.resultHeader}>
                <Text style={receiptStyles.resultTitle}>
                  {result.store_name || `Scontrino ${rIdx + 1}`}
                </Text>
                {result.date && (
                  <Text style={receiptStyles.resultDate}>{result.date}</Text>
                )}
              </View>

              {result.items.map((item, idx) => (
                <View key={idx} style={receiptStyles.itemRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={receiptStyles.itemName}>{item.name}</Text>
                    {item.category && (
                      <Text style={receiptStyles.itemCategory}>{item.category}</Text>
                    )}
                  </View>
                  <Text style={receiptStyles.itemPrice}>{item.total_price}</Text>
                </View>
              ))}

              {result.total && (
                <View style={receiptStyles.totalRow}>
                  <Text style={receiptStyles.totalLabel}>Totale</Text>
                  <Text style={receiptStyles.totalValue}>{result.total}</Text>
                </View>
              )}
            </View>
          ))}

          <Text style={receiptStyles.savedHint}>
            Salvati nello storico acquisti ({totalItems} prodotti da {results.length} scontrin{results.length === 1 ? "o" : "i"})
          </Text>

          <Button mode="text" compact onPress={reset} style={{ marginTop: 8 }}>
            Carica altri scontrini
          </Button>
        </View>
      )}
    </View>
  );
}

const receiptStyles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 12,
  },
  header: { marginBottom: 8 },
  title: { fontWeight: "600", fontSize: 14, color: "#1a1a1a" },
  subtitle: { fontSize: 12, color: "#666", marginTop: 2 },
  buttonRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 8,
  },
  pickButton: { flex: 1 },
  preview: {
    width: "100%",
    height: 200,
    borderRadius: 8,
    marginTop: 8,
    backgroundColor: "#f0f0f0",
  },
  chainSelector: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 10,
    flexWrap: "wrap",
  },
  chainLabel: { fontSize: 13, fontWeight: "600", color: "#333" },
  errorBox: {
    marginTop: 8,
    padding: 10,
    backgroundColor: "#FFEBEE",
    borderRadius: 8,
  },
  errorText: { color: "#C62828", fontSize: 13 },
  resultBox: {
    marginTop: 8,
    padding: 12,
    backgroundColor: "rgba(0,0,0,0.03)",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(0,0,0,0.06)",
  },
  resultHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(0,0,0,0.08)",
  },
  resultTitle: { fontWeight: "700", fontSize: 15, color: "#1a1a1a" },
  resultDate: { fontSize: 12, color: "#666" },
  itemRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 4,
  },
  itemName: { fontSize: 13, color: "#333" },
  itemCategory: { fontSize: 11, color: "#999" },
  itemPrice: { fontSize: 13, fontWeight: "600", color: "#1a1a1a", marginLeft: 8 },
  totalRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "rgba(0,0,0,0.1)",
  },
  totalLabel: { fontWeight: "700", fontSize: 14, color: "#1a1a1a" },
  totalValue: { fontWeight: "700", fontSize: 14, color: "#2E7D32" },
  savedHint: { fontSize: 11, color: "#2E7D32", marginTop: 8, fontStyle: "italic" },
  fileRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 2,
    paddingLeft: 4,
  },
  fileName: { fontSize: 13, color: "#333", flex: 1 },
});

function useBookmarkletCode() {
  const { accessToken } = useAppStore();

  const apiBase = typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? window.location.origin + "/api/v1"
    : "http://localhost:8000/api/v1";

  // Build bookmarklet — only single quotes inside to avoid HTML attribute issues
  return `javascript:void(function(){` +
    `var T='${accessToken || ""}';` +
    `var API='${apiBase}';` +
    `var el=document.querySelector('[ng-controller]');` +
    `if(!el){alert('Apri la pagina I tuoi scontrini su esselunga.it');return}` +
    `var sc=angular.element(el).scope();` +
    `if(!sc||!sc.ctrl){alert('Scope AngularJS non trovato.');return}` +
    `var mv=sc.ctrl.shoppingMovements;` +
    `var cc=sc.ctrl.codCarta;` +
    `if(!mv||!mv.length){alert('Nessuno scontrino trovato.');return}` +
    `var ov=document.createElement('div');` +
    `ov.id='ss-overlay';` +
    `ov.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:99999;display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:system-ui,sans-serif;color:#fff';` +
    `var tx=document.createElement('div');` +
    `tx.style.cssText='font-size:18px;margin-bottom:16px';` +
    `tx.textContent='SpesaSmart - Importazione scontrini';` +
    `ov.appendChild(tx);` +
    `var st=document.createElement('div');` +
    `st.id='ss-status';` +
    `st.style.cssText='font-size:14px;margin-bottom:8px';` +
    `st.textContent='Avvio...';` +
    `ov.appendChild(st);` +
    `var pg=document.createElement('div');` +
    `pg.style.cssText='width:300px;height:6px;background:#333;border-radius:3px;overflow:hidden';` +
    `var pb=document.createElement('div');` +
    `pb.id='ss-bar';` +
    `pb.style.cssText='height:100%;width:0%;background:#2E7D32;transition:width 0.3s';` +
    `pg.appendChild(pb);ov.appendChild(pg);` +
    `var lg=document.createElement('div');` +
    `lg.id='ss-log';` +
    `lg.style.cssText='margin-top:16px;font-size:12px;max-height:200px;overflow-y:auto;width:340px;text-align:left';` +
    `ov.appendChild(lg);` +
    `document.body.appendChild(ov);` +
    `var imported=0,skipped=0,errors=0,i=0;` +
    `function addLog(m,c){var d=document.createElement('div');d.style.color=c||'#aaa';d.textContent=m;lg.appendChild(d);lg.scrollTop=lg.scrollHeight}` +
    `function done(){` +
      `st.textContent='Completato! '+imported+' importati, '+skipped+' gia presenti'+(errors?', '+errors+' errori':'');` +
      `st.style.color='#2E7D32';` +
      `pb.style.width='100%';` +
      `var btn=document.createElement('button');` +
      `btn.textContent='Chiudi';` +
      `btn.style.cssText='margin-top:16px;padding:8px 24px;background:#2E7D32;color:#fff;border:none;border-radius:4px;font-size:14px;cursor:pointer';` +
      `btn.onclick=function(){document.body.removeChild(ov)};` +
      `ov.appendChild(btn)` +
    `}` +
    `function next(){` +
      `if(i>=mv.length){done();return}` +
      `var m=mv[i];` +
      `var pct=Math.round((i/mv.length)*100);` +
      `pb.style.width=pct+'%';` +
      `st.textContent='Scontrino '+(i+1)+'/'+mv.length+': download...';` +
      `var x1=new XMLHttpRequest();` +
      `x1.open('GET','shoppingMovementsAjax?pdfId='+m.id+'&codCarta='+cc,true);` +
      `x1.responseType='blob';` +
      `x1.onload=function(){` +
        `if(x1.status!==200){addLog('Errore download #'+m.id,'#e57373');errors++;i++;next();return}` +
        `st.textContent='Scontrino '+(i+1)+'/'+mv.length+': upload...';` +
        `var fd=new FormData();` +
        `fd.append('file',x1.response,'scontrino_'+m.id+'.pdf');` +
        `fd.append('chain_slug','esselunga');` +
        `fd.append('external_receipt_id',String(m.id));` +
        `var x2=new XMLHttpRequest();` +
        `x2.open('POST',API+'/users/me/purchases/upload-receipt',true);` +
        `x2.setRequestHeader('Authorization','Bearer '+T);` +
        `x2.onload=function(){` +
          `if(x2.status===200){` +
            `var r=JSON.parse(x2.responseText);` +
            `if(r.skipped){skipped++;addLog('#'+m.id+' - gia presente','#FFD200')}` +
            `else{imported++;addLog('#'+m.id+' - importato ('+r.items_count+' prodotti)','#81C784')}` +
          `}else{errors++;addLog('#'+m.id+' - errore upload','#e57373')}` +
          `i++;next()` +
        `};` +
        `x2.onerror=function(){errors++;addLog('#'+m.id+' - errore rete','#e57373');i++;next()};` +
        `x2.send(fd)` +
      `};` +
      `x1.onerror=function(){errors++;addLog('#'+m.id+' - errore download','#e57373');i++;next()};` +
      `x1.send()` +
    `}` +
    `next()` +
  `}())`;
}

function EsselungaBookmarkletSection() {
  const [copied, setCopied] = useState(false);
  const { accessToken } = useAppStore();
  const linkRef = useRef<HTMLSpanElement>(null);
  const bookmarkletCode = useBookmarkletCode();

  // Create the <a> element via DOM to avoid HTML escaping issues with javascript: href
  useEffect(() => {
    const container = linkRef.current;
    if (!container || !accessToken) return;
    container.innerHTML = "";
    const a = document.createElement("a");
    a.href = bookmarkletCode;
    a.textContent = "Importa Scontrini Esselunga";
    a.title = "Trascina nella barra dei segnalibri";
    a.style.cssText = "display:inline-block;padding:8px 16px;background:#2E7D32;color:#fff;border-radius:4px;text-decoration:none;font-weight:600;font-size:13px;cursor:grab;font-family:system-ui,sans-serif;user-select:none";
    container.appendChild(a);
  }, [bookmarkletCode, accessToken]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(bookmarkletCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = bookmarkletCode;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!accessToken) return null;

  return (
    <View style={bookmarkletStyles.container}>
      <View style={bookmarkletStyles.header}>
        <Text style={bookmarkletStyles.title}>Importa scontrini Esselunga</Text>
        <Text style={bookmarkletStyles.subtitle}>
          Importa automaticamente tutti gli scontrini dal tuo account Esselunga
        </Text>
      </View>

      <View style={bookmarkletStyles.steps}>
        <Text style={bookmarkletStyles.step}>
          1. Trascina il link verde nella barra dei segnalibri (oppure copialo)
        </Text>
        <Text style={bookmarkletStyles.step}>
          2. Vai su esselunga.it/area-utenti e apri "I tuoi scontrini"
        </Text>
        <Text style={bookmarkletStyles.step}>
          3. Clicca il segnalibro: gli scontrini vengono scaricati e importati in SpesaSmart
        </Text>
      </View>

      <View style={bookmarkletStyles.linkRow}>
        <span ref={linkRef as any} />
        <Button
          mode="outlined"
          icon={copied ? "check" : "content-copy"}
          onPress={handleCopy}
          compact
          style={{ marginLeft: 8 }}
        >
          {copied ? "Copiato!" : "Copia link"}
        </Button>
      </View>

      <Text style={bookmarkletStyles.warning}>
        Il link contiene il tuo token di accesso. Non condividerlo con nessuno.
      </Text>
    </View>
  );
}

const bookmarkletStyles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 12,
  },
  header: { marginBottom: 8 },
  title: { fontWeight: "600", fontSize: 14, color: "#1a1a1a" },
  subtitle: { fontSize: 12, color: "#666", marginTop: 2 },
  steps: { marginBottom: 12 },
  step: { fontSize: 13, color: "#333", marginBottom: 4, paddingLeft: 4 },
  linkRow: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 8,
  },
  warning: {
    fontSize: 11,
    color: "#C62828",
    fontStyle: "italic",
    marginTop: 4,
  },
});

const SUPERMARKET_CHAINS = [
  { slug: "esselunga", label: "Esselunga" },
  { slug: "iperal", label: "Iperal" },
];

function RemoteBrowserLogin({
  chainSlug,
  onClose,
  onSuccess,
}: {
  chainSlug: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [starting, setStarting] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  const [browserWidth, setBrowserWidth] = useState(1280);
  const [browserHeight, setBrowserHeight] = useState(720);
  const statusPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const screenshotPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevBlobRef = useRef<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const inputRef = useRef<any>(null);
  const lastInputLen = useRef(0);

  const isMobileWeb = Platform.OS === "web" && typeof window !== "undefined" && ("ontouchstart" in window || navigator.maxTouchPoints > 0);

  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

  // Start session — pass device viewport on mobile for responsive rendering
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let vw: number | undefined;
        let vh: number | undefined;
        if (isMobileWeb && typeof window !== "undefined") {
          // Use device screen size for mobile viewport
          vw = Math.round(window.screen.width * (window.devicePixelRatio || 1));
          vh = Math.round(window.screen.height * (window.devicePixelRatio || 1));
          // Cap at reasonable mobile dimensions (CSS pixels, not physical)
          vw = Math.min(window.screen.width, 430);
          vh = Math.min(window.screen.height, 932);
        }
        const res = await startRemoteLogin(chainSlug, vw, vh);
        if (!cancelled) {
          setSessionId(res.session_id);
          setBrowserWidth(res.viewport_width);
          setBrowserHeight(res.viewport_height);
          setStarting(false);
        }
      } catch (err: any) {
        if (!cancelled) { setError(err.response?.data?.detail || "Impossibile avviare la sessione."); setStarting(false); }
      }
    })();
    return () => { cancelled = true; };
  }, [chainSlug]);

  // Poll screenshot
  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    const fetchScreenshot = async () => {
      try {
        const blob = await fetchRemoteScreenshot(sessionId);
        if (!active) return;
        const url = URL.createObjectURL(blob);
        setScreenshotUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
        prevBlobRef.current = url;
      } catch {}
    };
    fetchScreenshot();
    screenshotPollRef.current = setInterval(fetchScreenshot, 800);
    return () => { active = false; if (screenshotPollRef.current) clearInterval(screenshotPollRef.current); if (prevBlobRef.current) URL.revokeObjectURL(prevBlobRef.current); };
  }, [sessionId]);

  // Poll status
  useEffect(() => {
    if (!sessionId) return;
    statusPollRef.current = setInterval(async () => {
      try {
        const res = await getRemoteStatus(sessionId);
        if (res.status === "success") {
          if (statusPollRef.current) clearInterval(statusPollRef.current);
          if (screenshotPollRef.current) clearInterval(screenshotPollRef.current);
          onSuccess();
        } else if (res.status === "error") {
          if (statusPollRef.current) clearInterval(statusPollRef.current);
          if (screenshotPollRef.current) clearInterval(screenshotPollRef.current);
          setError(res.error || "Errore durante il login.");
        }
      } catch {}
    }, 2000);
    return () => { if (statusPollRef.current) clearInterval(statusPollRef.current); };
  }, [sessionId]);

  // Desktop: capture keyboard directly (not from input)
  useEffect(() => {
    if (Platform.OS !== "web" || !sessionId) return;
    const isTouchDevice = "ontouchstart" in window || navigator.maxTouchPoints > 0;
    if (isTouchDevice) return; // Mobile uses the input field instead

    const KEY_MAP: Record<string, string> = {
      Backspace: "Backspace", Tab: "Tab", Enter: "Enter",
      ArrowLeft: "ArrowLeft", ArrowRight: "ArrowRight", ArrowUp: "ArrowUp", ArrowDown: "ArrowDown",
      Delete: "Delete", Home: "Home", End: "End",
    };
    const handleKeyDown = async (e: KeyboardEvent) => {
      const sid = sessionIdRef.current;
      if (!sid) return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "Escape") { e.preventDefault(); handleClose(); return; }
      e.preventDefault();
      e.stopPropagation();
      try {
        if (KEY_MAP[e.key]) await sendRemoteAction(sid, { type: "press", key: KEY_MAP[e.key] });
        else if (e.key.length === 1) await sendRemoteAction(sid, { type: "type", text: e.key });
      } catch {}
    };
    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [sessionId]);

  // Cleanup
  useEffect(() => {
    return () => { if (sessionIdRef.current) cancelRemoteLogin(sessionIdRef.current).catch(() => {}); };
  }, []);

  // Handle text input changes (mobile): detect new chars or deletions
  const handleInputChange = useCallback(async (text: string) => {
    const sid = sessionIdRef.current;
    if (!sid) { setInputText(text); return; }
    const prev = lastInputLen.current;
    if (text.length > prev) {
      // New characters typed
      const newChars = text.slice(prev);
      try { await sendRemoteAction(sid, { type: "type", text: newChars }); } catch {}
    } else if (text.length < prev) {
      // Characters deleted (backspace)
      const deleted = prev - text.length;
      for (let i = 0; i < deleted; i++) {
        try { await sendRemoteAction(sid, { type: "press", key: "Backspace" }); } catch {}
      }
    }
    lastInputLen.current = text.length;
    setInputText(text);
  }, []);

  // Desktop: simple click handler
  const handleImageClick = useCallback(async (e: any) => {
    if (isMobileWeb) return; // Mobile uses touch handlers
    const sid = sessionIdRef.current;
    if (!sid) return;
    const rect = e.target.getBoundingClientRect();
    const clickX = (e.clientX - rect.left) * (browserWidth / rect.width);
    const clickY = (e.clientY - rect.top) * (browserHeight / rect.height);
    try { await sendRemoteAction(sid, { type: "click", x: clickX, y: clickY }); } catch {}
  }, [browserWidth, browserHeight, isMobileWeb]);

  // Mobile: touch handlers for tap (click) + swipe (scroll)
  const touchRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  const onTouchStart = useCallback((e: any) => {
    const t = e.touches[0];
    touchRef.current = { x: t.clientX, y: t.clientY, moved: false };
  }, []);

  const onTouchMove = useCallback(async (e: any) => {
    if (!touchRef.current) return;
    const sid = sessionIdRef.current;
    if (!sid) return;
    const t = e.touches[0];
    const dy = touchRef.current.y - t.clientY;
    if (Math.abs(dy) > 8) {
      touchRef.current.moved = true;
      try { await sendRemoteAction(sid, { type: "scroll", y: dy * 3 }); } catch {}
      touchRef.current.x = t.clientX;
      touchRef.current.y = t.clientY;
    }
    e.preventDefault();
  }, []);

  const onTouchEnd = useCallback(async (e: any) => {
    if (!touchRef.current) { return; }
    if (touchRef.current.moved) { touchRef.current = null; return; }
    // Small movement = tap = click
    const sid = sessionIdRef.current;
    if (!sid) { touchRef.current = null; return; }
    const t = e.changedTouches[0];
    const rect = (e.target as HTMLElement).getBoundingClientRect();
    const clickX = (t.clientX - rect.left) * (browserWidth / rect.width);
    const clickY = (t.clientY - rect.top) * (browserHeight / rect.height);
    try { await sendRemoteAction(sid, { type: "click", x: clickX, y: clickY }); } catch {}
    touchRef.current = null;
  }, [browserWidth, browserHeight]);

  const handleClose = useCallback(async () => {
    if (statusPollRef.current) clearInterval(statusPollRef.current);
    if (screenshotPollRef.current) clearInterval(screenshotPollRef.current);
    const sid = sessionIdRef.current;
    if (sid) { try { await cancelRemoteLogin(sid); } catch {} }
    onClose();
  }, [onClose]);

  const pressKey = useCallback(async (key: string) => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    try { await sendRemoteAction(sid, { type: "press", key }); } catch {}
  }, []);

  const chainLabel = chainSlug.charAt(0).toUpperCase() + chainSlug.slice(1);

  return (
    <Portal>
      <View style={smStyles.modalOverlay}>
        {/* Header */}
        <View style={smStyles.modalHeader}>
          <Text style={{ color: "#fff", fontSize: 16, fontWeight: "700" }}>
            Login {chainLabel}
          </Text>
          <View style={{ flex: 1 }} />
          <Pressable onPress={handleClose} style={smStyles.modalCloseBtn}>
            <Text style={{ color: "#fff", fontSize: 20, fontWeight: "700" }}>✕</Text>
          </Pressable>
        </View>

        {/* Screenshot */}
        <View style={{ flex: 1, justifyContent: "center", alignItems: "center", padding: 4 }}>
          {starting ? (
            <View style={{ alignItems: "center" }}>
              <ActivityIndicator size="large" color="#fff" />
              <Text style={{ color: "#aaa", marginTop: 16, fontSize: 14 }}>Avvio browser remoto...</Text>
            </View>
          ) : error ? (
            <View style={{ alignItems: "center", padding: 32 }}>
              <Text style={{ color: "#ff6b6b", fontSize: 15, textAlign: "center", marginBottom: 16 }}>{error}</Text>
              <Button mode="contained" onPress={handleClose} buttonColor="#fff" textColor="#333">Chiudi</Button>
            </View>
          ) : screenshotUrl ? (
            Platform.OS === "web" ? (
              <img
                src={screenshotUrl}
                onClick={handleImageClick}
                onTouchStart={isMobileWeb ? onTouchStart : undefined}
                onTouchMove={isMobileWeb ? onTouchMove : undefined}
                onTouchEnd={isMobileWeb ? onTouchEnd : undefined}
                style={{
                  width: "100%",
                  maxHeight: isMobileWeb ? "calc(100vh - 120px)" : "calc(100vh - 70px)",
                  cursor: isMobileWeb ? "default" : "pointer",
                  display: "block",
                  borderRadius: 6,
                  objectFit: "contain",
                  touchAction: "none",
                }}
                alt="Browser remoto"
                draggable={false}
              />
            ) : (
              <Image source={{ uri: screenshotUrl }} style={{ width: "100%", aspectRatio: browserWidth / browserHeight }} resizeMode="contain" />
            )
          ) : (
            <ActivityIndicator size="large" color="#fff" />
          )}
        </View>

        {/* Bottom input bar (always visible on mobile, hidden on desktop) */}
        {(isMobileWeb || Platform.OS !== "web") && !starting && !error && (
          <View style={smStyles.modalInputBar}>
            <TextInput
              ref={inputRef}
              value={inputText}
              onChangeText={handleInputChange}
              placeholder="Tocca qui per digitare..."
              placeholderTextColor="#999"
              mode="flat"
              dense
              style={smStyles.modalInput}
              autoCapitalize="none"
              autoCorrect={false}
              // @ts-ignore
              spellCheck={false}
              underlineColor="transparent"
              activeUnderlineColor="#4FC3F7"
              textColor="#fff"
              onSubmitEditing={() => { pressKey("Enter"); setInputText(""); lastInputLen.current = 0; }}
            />
            <IconButton icon="keyboard-tab" iconColor="#fff" size={22} onPress={() => { pressKey("Tab"); setInputText(""); lastInputLen.current = 0; }} />
            <IconButton icon="keyboard-return" iconColor="#fff" size={22} onPress={() => { pressKey("Enter"); setInputText(""); lastInputLen.current = 0; }} />
          </View>
        )}

        {/* Desktop hint */}
        {!isMobileWeb && Platform.OS === "web" && !starting && !error && (
          <Text style={{ color: "rgba(255,255,255,0.4)", fontSize: 12, textAlign: "center", paddingBottom: 8 }}>
            Clicca sui campi e digita — Esc per chiudere
          </Text>
        )}
      </View>
    </Portal>
  );
}

function SupermarketAccountsSection() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const isNative = Platform.OS !== "web";
  const [remoteBrowserSlug, setRemoteBrowserSlug] = useState<string | null>(null);
  const [snackMsg, setSnackMsg] = useState("");
  const [snackVisible, setSnackVisible] = useState(false);

  const { data: accounts } = useQuery({
    queryKey: ["supermarketAccounts"],
    queryFn: getSupermarketAccounts,
  });

  const removeMutation = useMutation({
    mutationFn: (slug: string) => removeSupermarketAccount(slug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["supermarketAccounts"] });
    },
  });

  const syncMutation = useMutation({
    mutationFn: (slug: string) => triggerPurchaseSync(slug),
  });

  const connectedSlugs = new Set((accounts || []).map((a) => a.chain_slug));

  const getStatusColor = (acc: SupermarketAccount) => {
    if (acc.session_status === "active" && acc.is_valid) return "#2E7D32";
    if (acc.session_status === "expired" || !acc.is_valid) return "#E65100";
    return "#9E9E9E";
  };

  const getStatusLabel = (acc: SupermarketAccount) => {
    if (acc.session_status === "active" && acc.is_valid) return "Connesso";
    if (acc.session_status === "expired" || !acc.is_valid) return "Sessione scaduta";
    return "Non connesso";
  };

  const openRemoteBrowser = (slug: string) => {
    setRemoteBrowserSlug(remoteBrowserSlug === slug ? null : slug);
  };

  const handleRemoteSuccess = () => {
    setRemoteBrowserSlug(null);
    queryClient.invalidateQueries({ queryKey: ["supermarketAccounts"] });
    setSnackMsg("Connesso! Sync acquisti in corso...");
    setSnackVisible(true);
  };

  return (
    <View style={{ paddingHorizontal: 16, paddingBottom: 8 }}>
      {/* Connected accounts */}
      {accounts && accounts.length > 0 && accounts.map((acc) => (
        <View key={acc.chain_slug} style={smStyles.accountRow}>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <Text style={smStyles.accountChain}>
                {acc.chain_slug.charAt(0).toUpperCase() + acc.chain_slug.slice(1)}
              </Text>
              <View style={[smStyles.statusBadge, { backgroundColor: getStatusColor(acc) + "20" }]}>
                <View style={[smStyles.statusDot, { backgroundColor: getStatusColor(acc) }]} />
                <Text style={[smStyles.statusText, { color: getStatusColor(acc) }]}>
                  {getStatusLabel(acc)}
                </Text>
              </View>
            </View>
            {acc.last_error && (
              <Text style={smStyles.accountError}>{acc.last_error}</Text>
            )}
            {acc.last_synced_at && (
              <Text style={smStyles.accountSync}>
                Ultimo sync: {new Date(acc.last_synced_at).toLocaleDateString("it-IT")}
              </Text>
            )}
            {(acc.session_status === "expired" || !acc.is_valid) && (
              isNative ? (
                <Button
                  mode="text"
                  compact
                  icon="refresh"
                  onPress={() => router.push(`/supermarket-login/${acc.chain_slug}` as any)}
                  style={{ alignSelf: "flex-start", marginTop: 2 }}
                  labelStyle={{ fontSize: 12 }}
                >
                  Ricollega
                </Button>
              ) : (
                <Button
                  mode="text"
                  compact
                  icon="refresh"
                  onPress={() => openRemoteBrowser(acc.chain_slug)}
                  style={{ alignSelf: "flex-start", marginTop: 2 }}
                  labelStyle={{ fontSize: 12 }}
                >
                  Ricollega
                </Button>
              )
            )}
          </View>
          <View style={{ flexDirection: "row", gap: 4 }}>
            <Button
              mode="text"
              compact
              icon="sync"
              onPress={() => syncMutation.mutate(acc.chain_slug)}
              loading={syncMutation.isPending}
            >
              {""}
            </Button>
            <Button
              mode="text"
              compact
              icon="close"
              textColor="#D32F2F"
              onPress={() => removeMutation.mutate(acc.chain_slug)}
            >
              {""}
            </Button>
          </View>
        </View>
      ))}

      {/* Unconnected chains */}
      {SUPERMARKET_CHAINS.filter((c) => !connectedSlugs.has(c.slug)).length > 0 && (
        <View style={{ marginTop: 8 }}>
          <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
            {SUPERMARKET_CHAINS.filter((c) => !connectedSlugs.has(c.slug)).map((c) => (
              <Chip
                key={c.slug}
                onPress={() => {
                  if (isNative) {
                    router.push(`/supermarket-login/${c.slug}` as any);
                  } else {
                    openRemoteBrowser(c.slug);
                  }
                }}
                icon="link-plus"
                compact
              >
                Collega {c.label}
              </Chip>
            ))}
          </View>
        </View>
      )}

      {/* Remote browser login (web) */}
      {remoteBrowserSlug && (
        <RemoteBrowserLogin
          chainSlug={remoteBrowserSlug}
          onClose={() => setRemoteBrowserSlug(null)}
          onSuccess={handleRemoteSuccess}
        />
      )}

      <Snackbar
        visible={snackVisible}
        onDismiss={() => setSnackVisible(false)}
        duration={3000}
      >
        {snackMsg}
      </Snackbar>
    </View>
  );
}

const smStyles = StyleSheet.create({
  accountRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(0,0,0,0.06)",
  },
  accountChain: { fontWeight: "600", color: "#1a1a1a", fontSize: 14 },
  accountError: { color: "#C62828", fontSize: 11, marginTop: 2 },
  accountSync: { color: "#666", fontSize: 11, marginTop: 2 },
  accountHint: { color: "#E65100", fontSize: 11, marginTop: 2, fontStyle: "italic" },
  statusBadge: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
    gap: 4,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 11, fontWeight: "600" },
  instructionsBox: {
    marginTop: 12,
    padding: 12,
    backgroundColor: "rgba(0,0,0,0.03)",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(0,0,0,0.06)",
  },
  instructionsTitle: { fontWeight: "600", color: "#1a1a1a", fontSize: 13 },
  instructionsText: { color: "#555", fontSize: 12, marginBottom: 8, lineHeight: 18 },
  commandBox: {
    backgroundColor: "#1a1a1a",
    borderRadius: 6,
    padding: 10,
    marginBottom: 8,
  },
  commandText: { color: "#4FC3F7", fontSize: 11, fontFamily: Platform.OS === "web" ? "monospace" : undefined },
  remoteBrowserBox: {
    marginTop: 12,
    backgroundColor: "rgba(0,0,0,0.03)",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(0,0,0,0.08)",
    overflow: "hidden",
  },
  remoteBrowserHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingLeft: 12,
    paddingRight: 4,
    paddingVertical: 2,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(0,0,0,0.06)",
  },
  screenshotContainer: {
    backgroundColor: "#000",
    marginHorizontal: 8,
    marginTop: 8,
    borderRadius: 4,
    overflow: "hidden",
  },
  remoteBrowserHint: {
    color: "#888",
    fontSize: 11,
    paddingHorizontal: 12,
    paddingBottom: 10,
    fontStyle: "italic",
  },
  modalOverlay: {
    ...(Platform.OS === "web" ? { position: "fixed" as any } : { position: "absolute" as any }),
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "#000000",
    zIndex: 9999,
  } as any,
  modalHeader: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.1)",
  },
  modalCloseBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "rgba(255,255,255,0.15)",
    justifyContent: "center",
    alignItems: "center",
  },
  modalInputBar: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderTopWidth: 1,
    borderTopColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.08)",
  },
  modalInput: {
    flex: 1,
    backgroundColor: "rgba(255,255,255,0.1)",
    borderRadius: 8,
    fontSize: 16,
    height: 42,
  },
});

const CHAIN_OPTIONS = [
  { slug: "esselunga", label: "Esselunga" },
  { slug: "lidl", label: "Lidl" },
  { slug: "coop", label: "Coop" },
  { slug: "iperal", label: "Iperal" },
  { slug: "carrefour", label: "Carrefour" },
  { slug: "conad", label: "Conad" },
  { slug: "eurospin", label: "Eurospin" },
  { slug: "aldi", label: "Aldi" },
  { slug: "md-discount", label: "MD Discount" },
  { slug: "penny", label: "Penny Market" },
  { slug: "pam", label: "PAM Panorama" },
];

function NearbyStoresSelector({ isLoggedIn }: { isLoggedIn: boolean }) {
  const queryClient = useQueryClient();
  const {
    userLat, userLon, nearbyChains,
    setUserLocation, setNearbyChains,
  } = useAppStore();

  const [locating, setLocating] = useState(false);
  const [nearbyData, setNearbyData] = useState<NearbyChainInfo[] | null>(null);

  // Preferred chains query (server-side)
  const { data: preferredChains } = useQuery({
    queryKey: ["preferredChains"],
    queryFn: getPreferredChains,
    enabled: isLoggedIn,
  });

  const chainMutation = useMutation({
    mutationFn: (chains: string[]) => updatePreferredChains(chains),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["preferredChains"] });
      queryClient.invalidateQueries({ queryKey: ["shoppingListCompare"] });
    },
  });

  const selectedSet = new Set(preferredChains || []);

  const toggleChain = (slug: string) => {
    const next = new Set(selectedSet);
    if (next.has(slug)) {
      next.delete(slug);
    } else {
      next.add(slug);
    }
    const arr = Array.from(next);
    chainMutation.mutate(arr);
    setNearbyChains(arr);
  };

  const handleGeolocate = async () => {
    setLocating(true);
    try {
      const position = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: false,
          timeout: 10000,
        });
      });

      const { latitude, longitude } = position.coords;
      setUserLocation(latitude, longitude);

      // Fetch nearby stores
      const result = await getNearbyStores(latitude, longitude, 20);
      setNearbyData(result.chains);

      // Auto-select all nearby chains
      const slugs = result.chain_slugs;
      setNearbyChains(slugs);
      if (isLoggedIn) {
        chainMutation.mutate(slugs);
        updateUserLocation(latitude, longitude).catch(() => {});
      }
    } catch (err: any) {
      showAlert("Posizione", "Impossibile ottenere la posizione. Controlla i permessi.");
    }
    setLocating(false);
  };

  return (
    <View>
      {/* Geolocation button */}
      <View style={styles.geoRow}>
        <Button
          mode="contained"
          icon="crosshairs-gps"
          onPress={handleGeolocate}
          loading={locating}
          disabled={locating}
          style={styles.geoButton}
          labelStyle={{ fontWeight: "600" }}
        >
          Usa la mia posizione
        </Button>
        {userLat && userLon && (
          <Text style={styles.geoCoords}>
            {Number(userLat).toFixed(4)}, {Number(userLon).toFixed(4)}
          </Text>
        )}
      </View>

      {/* Nearby chains results */}
      {nearbyData && nearbyData.length > 0 && (
        <View style={styles.nearbyInfo}>
          <Text style={styles.nearbyLabel}>
            {nearbyData.length} catene trovate entro 20km
          </Text>
          {nearbyData.map((nc) => (
            <Text key={nc.chain_slug} style={styles.nearbyDetail}>
              {nc.chain_name}: {nc.store_count} negozi (min. {nc.min_distance_km}km)
            </Text>
          ))}
        </View>
      )}

      {/* Chain toggles */}
      <Text variant="bodySmall" style={styles.chainHint}>
        Seleziona le catene. Se nessuna selezionata, le mostra tutte.
      </Text>
      {CHAIN_OPTIONS.map((chain) => (
        <List.Item
          key={chain.slug}
          title={chain.label}
          titleStyle={{ color: "#1a1a1a" }}
          left={(props) => <List.Icon {...props} icon="store" />}
          right={() => (
            <Switch
              value={selectedSet.has(chain.slug)}
              onValueChange={() => toggleChain(chain.slug)}
              disabled={!isLoggedIn}
            />
          )}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "transparent" },
  section: {
    marginHorizontal: 12,
    marginTop: 12,
    ...glassPanel,
    overflow: "hidden",
  } as any,
  listSubheader: { color: glassColors.greenDark, fontWeight: "700", fontSize: 14 },
  listTitle: { color: "#1a1a1a" },
  listDescription: { color: "#555" },
  createSection: { paddingHorizontal: 16, paddingBottom: 16 },
  guestBanner: {
    backgroundColor: "rgba(245,127,23,0.08)",
    borderRadius: 12,
    padding: 12,
    marginBottom: 12,
  },
  guestBannerTitle: { color: "#E65100", fontWeight: "600", marginBottom: 4 },
  guestBannerText: { color: "#E65100" },
  googleButton: { marginBottom: 8 },
  orDivider: { textAlign: "center", color: "#999", marginBottom: 8 },
  createText: { color: "#555", marginBottom: 12 },
  errorText: { color: "#D32F2F", marginBottom: 8 },
  input: { marginBottom: 12 },
  buttonRow: { flexDirection: "row", gap: 12 },
  authButton: { flex: 1 },
  loggedInSection: { paddingBottom: 8 },
  logoutButton: { marginHorizontal: 16, marginBottom: 8 },
  reloadButton: { marginHorizontal: 16, marginBottom: 12 },
  brandInputRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, gap: 8, marginBottom: 4 },
  brandInput: { flex: 1 },
  brandAddButton: { marginTop: 6 },
  suggestionsRow: { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: 16, gap: 6, marginBottom: 8, marginTop: 4 },
  suggestionChip: { marginBottom: 2 },
  brandEmptyText: { color: "#666", paddingHorizontal: 16, paddingBottom: 12 },
  chainHint: { color: "#666", paddingHorizontal: 16, paddingBottom: 4 },
  geoRow: { paddingHorizontal: 16, paddingBottom: 8, gap: 6 },
  geoButton: { borderRadius: 12, backgroundColor: glassColors.greenMedium },
  geoCoords: { fontSize: 11, color: glassColors.textMuted, marginTop: 4 },
  nearbyInfo: { paddingHorizontal: 16, paddingBottom: 8 },
  nearbyLabel: { fontSize: 13, fontWeight: "600", color: glassColors.greenDark, marginBottom: 4 },
  nearbyDetail: { fontSize: 12, color: glassColors.textSecondary, marginBottom: 2 },
  bottomPadding: { height: 96 },
});
