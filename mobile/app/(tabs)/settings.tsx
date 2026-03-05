import { useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, View, Alert, Platform } from "react-native";
import { Button, Chip, List, Snackbar, Switch, Text, TextInput, useTheme } from "react-native-paper";
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
import { registerUser, loginUser, getUserBrands, addUserBrand, removeUserBrand, getBrands, updateUserProfile, getMe, getPreferredChains, updatePreferredChains, getNearbyStores, updateUserLocation, getSupermarketAccounts, addSupermarketAccount, removeSupermarketAccount, triggerPurchaseSync } from "../../services/api";
import type { NearbyChainInfo, SupermarketAccount } from "../../services/api";
import { registerForPushNotifications } from "../../services/notifications";
import { glassPanel, glassColors, glassCard } from "../../styles/glassStyles";

export default function SettingsScreen() {
  const theme = useTheme();
  const router = useRouter();
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
          <List.Subheader style={styles.listSubheader}>Profilo</List.Subheader>
          {isLoggedIn ? (
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
            description="Confronto prezzi supermercati - Monza e Brianza"
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

const SUPERMARKET_CHAINS = [
  { slug: "esselunga", label: "Esselunga" },
  { slug: "iperal", label: "Iperal" },
];

function SupermarketAccountsSection() {
  const queryClient = useQueryClient();
  const [selectedChain, setSelectedChain] = useState<string | null>(null);
  const [smEmail, setSmEmail] = useState("");
  const [smPassword, setSmPassword] = useState("");

  const { data: accounts } = useQuery({
    queryKey: ["supermarketAccounts"],
    queryFn: getSupermarketAccounts,
  });

  const addMutation = useMutation({
    mutationFn: () => addSupermarketAccount(selectedChain!, smEmail, smPassword),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["supermarketAccounts"] });
      setSelectedChain(null);
      setSmEmail("");
      setSmPassword("");
    },
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

  return (
    <View style={{ paddingHorizontal: 16, paddingBottom: 8 }}>
      {/* Connected accounts */}
      {accounts && accounts.length > 0 && accounts.map((acc) => (
        <View key={acc.chain_slug} style={smStyles.accountRow}>
          <View style={{ flex: 1 }}>
            <Text style={smStyles.accountChain}>
              {acc.chain_slug.charAt(0).toUpperCase() + acc.chain_slug.slice(1)}
            </Text>
            <Text style={smStyles.accountEmail}>{acc.masked_email}</Text>
            {acc.last_error && (
              <Text style={smStyles.accountError}>{acc.last_error}</Text>
            )}
            {acc.last_synced_at && (
              <Text style={smStyles.accountSync}>
                Ultimo sync: {new Date(acc.last_synced_at).toLocaleDateString("it-IT")}
              </Text>
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

      {/* Add new account */}
      {!selectedChain ? (
        <View style={{ flexDirection: "row", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          {SUPERMARKET_CHAINS.filter((c) => !connectedSlugs.has(c.slug)).map((c) => (
            <Chip
              key={c.slug}
              onPress={() => setSelectedChain(c.slug)}
              icon="plus"
              compact
            >
              {c.label}
            </Chip>
          ))}
        </View>
      ) : (
        <View style={{ marginTop: 8 }}>
          <Text variant="bodyMedium" style={{ fontWeight: "600", marginBottom: 8, color: "#1a1a1a" }}>
            Collega {selectedChain.charAt(0).toUpperCase() + selectedChain.slice(1)}
          </Text>
          <TextInput
            label="Email"
            value={smEmail}
            onChangeText={setSmEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            mode="outlined"
            dense
            style={{ marginBottom: 8 }}
          />
          <TextInput
            label="Password"
            value={smPassword}
            onChangeText={setSmPassword}
            secureTextEntry
            mode="outlined"
            dense
            style={{ marginBottom: 8 }}
          />
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Button
              mode="contained"
              onPress={() => addMutation.mutate()}
              loading={addMutation.isPending}
              disabled={!smEmail || !smPassword || addMutation.isPending}
              compact
              style={{ flex: 1 }}
            >
              Collega
            </Button>
            <Button
              mode="outlined"
              onPress={() => { setSelectedChain(null); setSmEmail(""); setSmPassword(""); }}
              compact
            >
              Annulla
            </Button>
          </View>
          {addMutation.isError && (
            <Text style={smStyles.accountError}>
              Errore nel collegamento. Verifica le credenziali.
            </Text>
          )}
        </View>
      )}
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
  accountEmail: { color: "#666", fontSize: 12, marginTop: 2 },
  accountError: { color: "#C62828", fontSize: 11, marginTop: 2 },
  accountSync: { color: "#666", fontSize: 11, marginTop: 2 },
});

const CHAIN_OPTIONS = [
  { slug: "esselunga", label: "Esselunga" },
  { slug: "lidl", label: "Lidl" },
  { slug: "coop", label: "Coop" },
  { slug: "iperal", label: "Iperal" },
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
