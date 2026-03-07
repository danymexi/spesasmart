import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { Button, Text } from "react-native-paper";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import WebView from "react-native-webview";
import CookieManager from "@react-native-cookies/cookies";
import { uploadSession } from "../../services/api";
import { getChainConfig } from "../../services/chainConfig";
import { glassColors } from "../../styles/glassStyles";

type LoginPhase = "browsing" | "detected" | "extracting" | "uploading" | "done" | "error";

export default function SupermarketLoginScreen() {
  const { chain } = useLocalSearchParams<{ chain: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const config = chain ? getChainConfig(chain) : undefined;

  const webViewRef = useRef<WebView>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [phase, setPhase] = useState<LoginPhase>("browsing");
  const [pageLoaded, setPageLoaded] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [localStorageEntries, setLocalStorageEntries] = useState<Array<{ name: string; value: string }>>([]);

  // Unsupported chain fallback
  if (!config) {
    return (
      <View style={styles.fallback}>
        <Text variant="titleMedium" style={styles.fallbackTitle}>
          Catena non supportata
        </Text>
        <Text variant="bodyMedium" style={styles.fallbackText}>
          La catena "{chain}" non e' ancora supportata per il login in-app.
        </Text>
        <Button mode="outlined" onPress={() => router.back()} style={{ marginTop: 16 }}>
          Torna indietro
        </Button>
      </View>
    );
  }

  // ── Auth polling ───────────────────────────────────────────────────────────
  const startPolling = useCallback(() => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(() => {
      if (webViewRef.current && phase === "browsing") {
        webViewRef.current.injectJavaScript(config.authCheckScript + "; true;");
      }
    }, 3000);
  }, [config, phase]);

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  // ── Cookie extraction ──────────────────────────────────────────────────────
  const extractAndUpload = useCallback(async () => {
    setPhase("extracting");

    // Small delay to let the native cookie jar sync with the WebView
    await new Promise((r) => setTimeout(r, 800));

    try {
      // 1. Extract cookies from all relevant domains (including httpOnly)
      const allCookies: any[] = [];
      for (const domain of config.cookieDomains) {
        const url = `https://${domain.replace(/^\./, "")}`;
        const domainCookies = await CookieManager.get(url, true);
        if (domainCookies) {
          for (const [name, cookie] of Object.entries(domainCookies) as [string, any][]) {
            allCookies.push({
              name,
              value: cookie.value ?? "",
              domain: cookie.domain ?? domain,
              path: cookie.path ?? "/",
              expires: cookie.expires
                ? Math.floor(new Date(cookie.expires).getTime() / 1000)
                : -1,
              httpOnly: cookie.httpOnly ?? false,
              secure: cookie.secure ?? true,
              sameSite: "None",
            });
          }
        }
      }

      // 2. Request localStorage from WebView
      webViewRef.current?.injectJavaScript(config.localStorageScript + "; true;");

      // Wait a moment for the message to come back
      await new Promise((r) => setTimeout(r, 500));

      // 3. Assemble Playwright-compatible storageState
      const origin = config.loginUrl;
      const storageState = {
        cookies: allCookies,
        origins: [
          {
            origin,
            localStorage: localStorageEntries,
          },
        ],
      };

      // 4. Upload to backend
      setPhase("uploading");
      await uploadSession(config.slug, storageState);

      // 5. Invalidate and navigate back
      setPhase("done");
      queryClient.invalidateQueries({ queryKey: ["supermarketAccounts"] });

      // Brief success feedback before going back
      setTimeout(() => {
        router.back();
      }, 1200);
    } catch (err: any) {
      console.error("Session upload failed:", err);
      setErrorMsg(err?.message || "Errore durante il salvataggio della sessione.");
      setPhase("error");
    }
  }, [config, localStorageEntries, queryClient, router]);

  // ── WebView message handler ────────────────────────────────────────────────
  const onMessage = useCallback(
    (event: any) => {
      try {
        const data = JSON.parse(event.nativeEvent.data);

        if (data.type === "AUTH_CHECK" && data.authenticated && phase === "browsing") {
          // Auth detected — stop polling, start extraction
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          setPhase("detected");
          // Trigger localStorage extraction, then cookies
          webViewRef.current?.injectJavaScript(config.localStorageScript + "; true;");
          // Give localStorage a moment, then extract cookies & upload
          setTimeout(() => extractAndUpload(), 600);
        }

        if (data.type === "LOCAL_STORAGE") {
          setLocalStorageEntries(data.entries || []);
        }
      } catch {
        // ignore non-JSON messages from the website
      }
    },
    [phase, config, extractAndUpload]
  );

  // ── Overlay text ───────────────────────────────────────────────────────────
  const overlayText = (() => {
    switch (phase) {
      case "detected":
      case "extracting":
        return "Login rilevato — estrazione sessione...";
      case "uploading":
        return "Salvataggio sessione...";
      case "done":
        return "Connesso!";
      case "error":
        return errorMsg || "Errore";
      default:
        return null;
    }
  })();

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text variant="titleMedium" style={styles.headerTitle}>
          Login {config.label}
        </Text>
        <Button
          mode="text"
          compact
          onPress={() => router.back()}
          icon="close"
          textColor={glassColors.textSecondary}
        >
          {""}
        </Button>
      </View>

      {/* WebView */}
      <View style={styles.webViewContainer}>
        {!pageLoaded && (
          <View style={styles.loadingOverlay}>
            <ActivityIndicator size="large" color={glassColors.greenMedium} />
            <Text style={styles.loadingText}>Caricamento...</Text>
          </View>
        )}

        <WebView
          ref={webViewRef}
          source={{ uri: config.loginUrl }}
          style={styles.webView}
          sharedCookiesEnabled
          thirdPartyCookiesEnabled
          javaScriptEnabled
          domStorageEnabled
          onLoadEnd={() => {
            setPageLoaded(true);
            startPolling();
          }}
          onMessage={onMessage}
          userAgent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        />
      </View>

      {/* Phase overlay */}
      {overlayText && (
        <View style={styles.phaseOverlay}>
          {phase !== "error" && phase !== "done" && (
            <ActivityIndicator size="small" color="#fff" style={{ marginRight: 10 }} />
          )}
          <Text style={[styles.phaseText, phase === "done" && styles.phaseTextDone]}>
            {overlayText}
          </Text>
          {phase === "error" && (
            <Button mode="text" textColor="#fff" onPress={() => router.back()}>
              Chiudi
            </Button>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(0,0,0,0.08)",
    backgroundColor: "#fafafa",
  },
  headerTitle: { fontWeight: "700", color: glassColors.greenDark },
  webViewContainer: { flex: 1 },
  webView: { flex: 1 },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "#fff",
    zIndex: 10,
  },
  loadingText: { marginTop: 12, color: "#666" },
  phaseOverlay: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 14,
    paddingHorizontal: 20,
    backgroundColor: "rgba(0,0,0,0.82)",
  },
  phaseText: { color: "#fff", fontSize: 14, fontWeight: "600" },
  phaseTextDone: { color: "#66BB6A" },
  fallback: { flex: 1, justifyContent: "center", alignItems: "center", padding: 32 },
  fallbackTitle: { fontWeight: "700", color: glassColors.greenDark, marginBottom: 12, textAlign: "center" },
  fallbackText: { color: "#555", textAlign: "center", lineHeight: 22 },
});
