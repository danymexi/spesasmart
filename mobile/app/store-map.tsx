import { useEffect, useMemo, useRef, useState } from "react";
import { Platform, StyleSheet, View } from "react-native";
import { ActivityIndicator, IconButton, Text } from "react-native-paper";
import { router } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { getStores, type Store } from "../services/api";
import { useGlassTheme } from "../styles/useGlassTheme";
import { useAppStore } from "../stores/useAppStore";

const CHAIN_COLORS: Record<string, string> = {
  Esselunga: "#D32F2F",
  Lidl: "#0039A6",
  Coop: "#E53935",
  Iperal: "#1565C0",
  Carrefour: "#004E9A",
  Conad: "#E31E24",
  Eurospin: "#1A4D8F",
  Aldi: "#00205B",
  "MD Discount": "#E5007D",
  "Penny Market": "#CD1719",
  "PAM Panorama": "#E4002B",
};

export default function StoreMapScreen() {
  const glass = useGlassTheme();
  const userLat = useAppStore((s) => s.userLat);
  const userLon = useAppStore((s) => s.userLon);
  const mapRef = useRef<HTMLDivElement>(null);

  const { data: stores, isLoading } = useQuery({
    queryKey: ["stores"],
    queryFn: () => getStores(),
  });

  const storesWithCoords = useMemo(
    () => (stores ?? []).filter((s) => s.lat != null && s.lon != null),
    [stores]
  );

  useEffect(() => {
    if (Platform.OS !== "web" || !mapRef.current || storesWithCoords.length === 0) return;

    let mapInstance: any = null;

    const initMap = async () => {
      const L = await import("leaflet");

      // Fix default icon path issue with bundlers
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      const center: [number, number] =
        userLat && userLon ? [userLat, userLon] : [45.585, 9.274]; // default: Monza

      mapInstance = L.map(mapRef.current!, { zoomControl: true }).setView(center, 12);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
      }).addTo(mapInstance);

      // Add store markers
      for (const store of storesWithCoords) {
        const color = CHAIN_COLORS[store.chain_name ?? ""] ?? "#333";
        const icon = L.divIcon({
          className: "custom-marker",
          html: `<div style="background:${color};width:12px;height:12px;border-radius:50%;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.3)"></div>`,
          iconSize: [16, 16],
          iconAnchor: [8, 8],
        });

        const marker = L.marker([store.lat!, store.lon!], { icon }).addTo(mapInstance);

        const hours = store.opening_hours
          ? Object.entries(store.opening_hours)
              .map(([day, time]) => `<b>${day}:</b> ${time}`)
              .join("<br/>")
          : "";

        marker.bindPopup(
          `<b>${store.chain_name ?? "Supermercato"}</b><br/>` +
            `${store.name ?? ""}<br/>` +
            `${store.address ?? ""}, ${store.city ?? ""}<br/>` +
            (hours ? `<br/>${hours}` : "")
        );
      }

      // Add user location marker
      if (userLat && userLon) {
        const userIcon = L.divIcon({
          className: "user-marker",
          html: `<div style="background:#2563EB;width:14px;height:14px;border-radius:50%;border:3px solid #fff;box-shadow:0 0 8px rgba(37,99,235,0.5)"></div>`,
          iconSize: [20, 20],
          iconAnchor: [10, 10],
        });
        L.marker([userLat, userLon], { icon: userIcon }).addTo(mapInstance);
      }
    };

    // Inject Leaflet CSS
    if (!document.getElementById("leaflet-css")) {
      const link = document.createElement("link");
      link.id = "leaflet-css";
      link.rel = "stylesheet";
      link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(link);
    }

    initMap();

    return () => {
      mapInstance?.remove?.();
    };
  }, [storesWithCoords, userLat, userLon]);

  if (Platform.OS !== "web") {
    return (
      <View style={[styles.container, styles.center]}>
        <Text style={{ color: glass.colors.textSecondary }}>
          La mappa e' disponibile solo su web browser.
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: glass.colors.surface }]}>
      <View style={styles.header}>
        <IconButton icon="arrow-left" size={24} onPress={() => router.back()} />
        <Text variant="titleMedium" style={{ color: glass.colors.textPrimary }}>
          Negozi vicini
        </Text>
        <Text variant="labelSmall" style={{ color: glass.colors.textMuted, marginRight: 12 }}>
          {storesWithCoords.length} negozi
        </Text>
      </View>
      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" />
        </View>
      ) : (
        <div
          ref={mapRef as any}
          style={{ flex: 1, width: "100%", height: "100%" }}
        />
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
  },
  center: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
  },
});
