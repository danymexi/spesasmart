import { useState } from "react";
import { Platform, Share, StyleSheet, View } from "react-native";
import { Button, IconButton, Modal, Portal, Snackbar, Text } from "react-native-paper";
import { shareShoppingList, type ShoppingListMeta } from "../services/api";
import { glassColors } from "../styles/glassStyles";

interface Props {
  visible: boolean;
  onDismiss: () => void;
  list: ShoppingListMeta | null;
}

export default function ShareListModal({ visible, onDismiss, list }: Props) {
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleShare = async () => {
    if (!list) return;
    setLoading(true);
    try {
      const result = await shareShoppingList(list.id);
      const origin =
        Platform.OS === "web" && typeof window !== "undefined"
          ? window.location.origin
          : "https://spesasmart.spazioitech.it";
      const fullUrl = `${origin}${result.share_url}`;
      setShareUrl(fullUrl);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!shareUrl) return;
    if (Platform.OS === "web" && typeof navigator !== "undefined" && navigator.clipboard) {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
    } else {
      await Share.share({ message: shareUrl });
    }
  };

  const handleDismiss = () => {
    setShareUrl(null);
    setCopied(false);
    onDismiss();
  };

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={handleDismiss}
        contentContainerStyle={styles.container}
      >
        <Text variant="titleLarge" style={styles.title}>
          Condividi lista
        </Text>
        <Text variant="bodyMedium" style={styles.subtitle}>
          {list?.emoji} {list?.name}
        </Text>

        {!shareUrl ? (
          <Button
            mode="contained"
            onPress={handleShare}
            loading={loading}
            icon="share-variant"
            style={styles.btn}
          >
            Genera link (24h)
          </Button>
        ) : (
          <View style={styles.linkRow}>
            <Text
              variant="bodySmall"
              style={styles.link}
              numberOfLines={2}
              selectable
            >
              {shareUrl}
            </Text>
            <IconButton icon="content-copy" size={20} onPress={handleCopy} />
          </View>
        )}

        <Button onPress={handleDismiss} style={styles.closeBtn}>
          Chiudi
        </Button>
      </Modal>
      <Snackbar
        visible={copied}
        onDismiss={() => setCopied(false)}
        duration={2000}
      >
        Link copiato!
      </Snackbar>
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
    marginBottom: 4,
    color: glassColors.textPrimary,
  },
  subtitle: {
    marginBottom: 20,
    color: glassColors.textSecondary,
  },
  btn: {
    marginBottom: 12,
  },
  linkRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.04)",
    borderRadius: 12,
    paddingLeft: 12,
    marginBottom: 12,
  },
  link: {
    flex: 1,
    color: glassColors.greenMedium,
    fontFamily: Platform.OS === "web" ? "monospace" : undefined,
  },
  closeBtn: {
    alignSelf: "flex-end",
  },
});
