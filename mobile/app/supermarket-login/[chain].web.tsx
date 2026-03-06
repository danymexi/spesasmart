import { StyleSheet, View } from "react-native";
import { Button, Text } from "react-native-paper";
import { useLocalSearchParams, useRouter } from "expo-router";
import { glassColors } from "../../styles/glassStyles";

/**
 * Web fallback — WebView login is only available on native (iOS/Android).
 * On web, users should use the CLI session helper from their Mac.
 */
export default function SupermarketLoginScreenWeb() {
  const { chain } = useLocalSearchParams<{ chain: string }>();
  const router = useRouter();

  return (
    <View style={styles.fallback}>
      <Text variant="titleMedium" style={styles.fallbackTitle}>
        Login non disponibile su web
      </Text>
      <Text variant="bodyMedium" style={styles.fallbackText}>
        Per collegare il tuo account {chain ? chain.charAt(0).toUpperCase() + chain.slice(1) : "supermercato"},
        usa l'app nativa su iOS o Android oppure lo script CLI dal tuo Mac.
      </Text>
      <Button mode="outlined" onPress={() => router.back()} style={{ marginTop: 16 }}>
        Torna indietro
      </Button>
    </View>
  );
}

const styles = StyleSheet.create({
  fallback: { flex: 1, justifyContent: "center", alignItems: "center", padding: 32 },
  fallbackTitle: { fontWeight: "700", color: glassColors.greenDark, marginBottom: 12, textAlign: "center" },
  fallbackText: { color: "#555", textAlign: "center", lineHeight: 22 },
});
