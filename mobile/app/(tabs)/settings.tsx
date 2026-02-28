import { useState } from "react";
import { ScrollView, StyleSheet, View, Alert, Platform } from "react-native";
import { Button, List, Switch, Text, TextInput, useTheme } from "react-native-paper";

function showAlert(title: string, message: string) {
  if (Platform.OS === "web") {
    window.alert(`${title}\n\n${message}`);
  } else {
    Alert.alert(title, message);
  }
}
import { useAppStore } from "../../stores/useAppStore";
import { registerUser, loginUser } from "../../services/api";
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
        </List.Section>
      </View>

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

      {/* Supermarkets */}
      <View style={styles.section}>
        <List.Section>
          <List.Subheader>Supermercati Monitorati</List.Subheader>
          {["Esselunga", "Lidl", "Coop", "Iperal"].map((chain) => (
            <List.Item
              key={chain}
              title={chain}
              left={(props) => <List.Icon {...props} icon="store" />}
              right={(props) => <List.Icon {...props} icon="check-circle" color={theme.colors.primary} />}
            />
          ))}
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
      </View>

      <View style={styles.bottomPadding} />
    </ScrollView>
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
  bottomPadding: { height: 96 },
});
