import { useState } from "react";
import { ScrollView, StyleSheet, View, Alert, Platform } from "react-native";
import { Button, Chip, List, Snackbar, Switch, Text, TextInput, useTheme } from "react-native-paper";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

function showAlert(title: string, message: string) {
  if (Platform.OS === "web") {
    window.alert(`${title}\n\n${message}`);
  } else {
    Alert.alert(title, message);
  }
}
import { useAppStore } from "../../stores/useAppStore";
import { registerUser, loginUser, getUserBrands, addUserBrand, removeUserBrand, getBrands, updateUserProfile, getMe, getPreferredChains, updatePreferredChains } from "../../services/api";
import { registerForPushNotifications } from "../../services/notifications";
import { glassPanel, glassColors } from "../../styles/glassStyles";

export default function SettingsScreen() {
  const theme = useTheme();
  const { isLoggedIn, userEmail, setAuth, logout } = useAppStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [brandInput, setBrandInput] = useState("");
  const [snackMessage, setSnackMessage] = useState("");
  const [snackVisible, setSnackVisible] = useState(false);

  const queryClient = useQueryClient();

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
      const res = await registerUser(email, password);
      setAuth(res.access_token, res.user.id, res.user.email!);
      setEmail("");
      setPassword("");
      showAlert("Registrazione completata", "Il tuo account è stato creato.");
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
          <List.Subheader>Profilo</List.Subheader>
          {isLoggedIn ? (
            <View style={styles.loggedInSection}>
              <List.Item
                title="Email"
                description={userEmail}
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
              <Text variant="bodyMedium" style={styles.createText}>
                Accedi o registrati per salvare la tua lista e ricevere notifiche.
              </Text>
              {error && (
                <Text variant="bodySmall" style={styles.errorText}>
                  {error}
                </Text>
              )}
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
                <Button
                  mode="contained"
                  onPress={handleLogin}
                  loading={loading}
                  disabled={!email || !password || loading}
                  style={styles.authButton}
                >
                  Accedi
                </Button>
                <Button
                  mode="outlined"
                  onPress={handleRegister}
                  loading={loading}
                  disabled={!email || !password || loading}
                  style={styles.authButton}
                >
                  Registrati
                </Button>
              </View>
            </View>
          )}
        </List.Section>
      </View>

      {/* Notifications */}
      <View style={styles.section}>
        <List.Section>
          <List.Subheader>Notifiche</List.Subheader>
          <List.Item
            title="Notifiche Push"
            description="Ricevi avvisi quando i tuoi prodotti sono in offerta"
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
            left={(props) => <List.Icon {...props} icon="send" />}
          />
          <List.Item
            title="Riepilogo settimanale"
            description={
              userProfile?.notification_mode === "digest"
                ? "Attivo: ricevi un riepilogo ogni lunedi'"
                : "Disattivo: ricevi notifiche immediate"
            }
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
            <List.Subheader>Marche Preferite</List.Subheader>
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

      {/* Zone */}
      <View style={styles.section}>
        <List.Section>
          <List.Subheader>Zona</List.Subheader>
          <List.Item
            title="Monza e Brianza"
            description="Zona monitorata per le offerte"
            left={(props) => <List.Icon {...props} icon="map-marker" />}
          />
        </List.Section>
      </View>

      {/* Preferred Chains */}
      <View style={styles.section}>
        <List.Section>
          <List.Subheader>Catene Preferite</List.Subheader>
          <Text variant="bodySmall" style={styles.chainHint}>
            Seleziona le catene da mostrare in home. Se nessuna selezionata, le mostra tutte.
          </Text>
          <PreferredChainsSelector isLoggedIn={isLoggedIn} />
        </List.Section>
      </View>

      {/* App info */}
      <View style={styles.section}>
        <List.Section>
          <List.Subheader>Info</List.Subheader>
          <List.Item
            title="Versione"
            description="1.0.0"
            left={(props) => <List.Icon {...props} icon="information" />}
          />
          <List.Item
            title="SpesaSmart"
            description="Confronto prezzi supermercati - Monza e Brianza"
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

const CHAIN_OPTIONS = [
  { slug: "esselunga", label: "Esselunga" },
  { slug: "lidl", label: "Lidl" },
  { slug: "coop", label: "Coop" },
  { slug: "iperal", label: "Iperal" },
];

function PreferredChainsSelector({ isLoggedIn }: { isLoggedIn: boolean }) {
  const queryClient = useQueryClient();

  const { data: preferredChains } = useQuery({
    queryKey: ["preferredChains"],
    queryFn: getPreferredChains,
    enabled: isLoggedIn,
  });

  const mutation = useMutation({
    mutationFn: (chains: string[]) => updatePreferredChains(chains),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["preferredChains"] });
    },
  });

  const selectedSet = new Set(preferredChains || []);

  const toggle = (slug: string) => {
    const next = new Set(selectedSet);
    if (next.has(slug)) {
      next.delete(slug);
    } else {
      next.add(slug);
    }
    mutation.mutate(Array.from(next));
  };

  return (
    <View>
      {CHAIN_OPTIONS.map((chain) => (
        <List.Item
          key={chain.slug}
          title={chain.label}
          left={(props) => <List.Icon {...props} icon="store" />}
          right={() => (
            <Switch
              value={selectedSet.has(chain.slug)}
              onValueChange={() => toggle(chain.slug)}
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
  createSection: { paddingHorizontal: 16, paddingBottom: 16 },
  createText: { color: "#666", marginBottom: 12 },
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
  brandEmptyText: { color: "#888", paddingHorizontal: 16, paddingBottom: 12 },
  chainHint: { color: "#888", paddingHorizontal: 16, paddingBottom: 4 },
  bottomPadding: { height: 96 },
});
