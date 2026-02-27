import { useState } from "react";
import { ScrollView, StyleSheet, View, Alert, Platform } from "react-native";
import { Button, Divider, List, Switch, Text, TextInput, useTheme } from "react-native-paper";

function showAlert(title: string, message: string) {
  if (Platform.OS === "web") {
    window.alert(`${title}\n\n${message}`);
  } else {
    Alert.alert(title, message);
  }
}
import { useAppStore } from "../../stores/useAppStore";
import { createUser } from "../../services/api";
import { registerForPushNotifications } from "../../services/notifications";

export default function SettingsScreen() {
  const theme = useTheme();
  const { userId, setUserId } = useAppStore();
  const [telegramId, setTelegramId] = useState("");
  const [pushEnabled, setPushEnabled] = useState(false);
  const [creating, setCreating] = useState(false);

  const handleCreateProfile = async () => {
    setCreating(true);
    try {
      const user = await createUser({
        telegram_chat_id: telegramId ? parseInt(telegramId, 10) : undefined,
      });
      setUserId(user.id);
      showAlert("Profilo creato", "Il tuo profilo è stato creato con successo.");
    } catch {
      showAlert("Errore", "Impossibile creare il profilo. Riprova.");
    }
    setCreating(false);
  };

  const handleEnablePush = async () => {
    if (!userId) return;
    const token = await registerForPushNotifications(userId);
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
      <List.Section>
        <List.Subheader>Profilo</List.Subheader>
        {userId ? (
          <List.Item
            title="ID Utente"
            description={userId}
            left={(props) => <List.Icon {...props} icon="account" />}
          />
        ) : (
          <View style={styles.createSection}>
            <Text variant="bodyMedium" style={styles.createText}>
              Crea un profilo per salvare la tua lista e ricevere notifiche.
            </Text>
            <TextInput
              label="Telegram Chat ID (opzionale)"
              value={telegramId}
              onChangeText={setTelegramId}
              keyboardType="numeric"
              mode="outlined"
              style={styles.input}
            />
            <Button
              mode="contained"
              onPress={handleCreateProfile}
              loading={creating}
              style={styles.createButton}
            >
              Crea Profilo
            </Button>
          </View>
        )}
      </List.Section>

      <Divider />

      {/* Notifications */}
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
              disabled={!userId}
            />
          )}
        />
        <List.Item
          title="Telegram Bot"
          description="Cerca @SpesaSmartBot su Telegram"
          left={(props) => <List.Icon {...props} icon="send" />}
        />
      </List.Section>

      <Divider />

      {/* Zone */}
      <List.Section>
        <List.Subheader>Zona</List.Subheader>
        <List.Item
          title="Monza e Brianza"
          description="Zona monitorata per le offerte"
          left={(props) => <List.Icon {...props} icon="map-marker" />}
        />
      </List.Section>

      <Divider />

      {/* Supermarkets */}
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

      <Divider />

      {/* App info */}
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

      <View style={styles.bottomPadding} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  createSection: { paddingHorizontal: 16, paddingBottom: 16 },
  createText: { color: "#666", marginBottom: 12 },
  input: { marginBottom: 12 },
  createButton: { alignSelf: "flex-start" },
  bottomPadding: { height: 40 },
});
