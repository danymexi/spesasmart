import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { registerPushToken } from "./api";

// ── Configure notification handler ──────────────────────────────────────────

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

// ── Types ────────────────────────────────────────────────────────────────────

export interface NotificationData {
  type: "price_alert" | "new_offer" | "flyer_update" | "deal_expiring";
  productId?: number;
  flyerId?: number;
  title?: string;
  body?: string;
}

// ── Register for push notifications ─────────────────────────────────────────

export async function registerForPushNotifications(
  userId: string
): Promise<string | null> {
  if (!Device.isDevice) {
    console.warn(
      "Le notifiche push richiedono un dispositivo fisico."
    );
    return null;
  }

  // Check existing permissions
  const { status: existingStatus } =
    await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  // Request permissions if not already granted
  if (existingStatus !== "granted") {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== "granted") {
    console.warn("Permesso per le notifiche push non concesso.");
    return null;
  }

  // Get Expo push token
  const tokenData = await Notifications.getExpoPushTokenAsync({
    projectId: "spesasmart-project-id",
  });
  const token = tokenData.data;

  // Configure Android notification channel
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "Notifiche SpesaSmart",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#1B5E20",
    });

    await Notifications.setNotificationChannelAsync("price-alerts", {
      name: "Avvisi Prezzo",
      description:
        "Notifiche quando un prodotto nella tua lista scende di prezzo.",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#FF6F00",
    });

    await Notifications.setNotificationChannelAsync("flyers", {
      name: "Nuovi Volantini",
      description: "Notifiche per nuovi volantini disponibili.",
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }

  // Register token with backend
  try {
    const platform: "ios" | "android" =
      Platform.OS === "ios" ? "ios" : "android";
    await registerPushToken(userId, token, platform);
  } catch (error) {
    console.error(
      "Errore nella registrazione del token push:",
      error
    );
  }

  return token;
}

// ── Get push token (without registering) ────────────────────────────────────

export async function getPushToken(): Promise<string | null> {
  if (!Device.isDevice) return null;

  const { status } = await Notifications.getPermissionsAsync();
  if (status !== "granted") return null;

  try {
    const tokenData = await Notifications.getExpoPushTokenAsync({
      projectId: "spesasmart-project-id",
    });
    return tokenData.data;
  } catch {
    return null;
  }
}

// ── Notification listeners ──────────────────────────────────────────────────

export function addNotificationReceivedListener(
  callback: (notification: Notifications.Notification) => void
): Notifications.Subscription {
  return Notifications.addNotificationReceivedListener(callback);
}

export function addNotificationResponseListener(
  callback: (response: Notifications.NotificationResponse) => void
): Notifications.Subscription {
  return Notifications.addNotificationResponseReceivedListener(callback);
}

// ── Parse notification data ─────────────────────────────────────────────────

export function parseNotificationData(
  notification: Notifications.Notification
): NotificationData | null {
  const data = notification.request.content.data;
  if (!data || typeof data !== "object") return null;

  return {
    type: data.type as NotificationData["type"],
    productId: data.productId as number | undefined,
    flyerId: data.flyerId as number | undefined,
    title: notification.request.content.title ?? undefined,
    body: notification.request.content.body ?? undefined,
  };
}

// ── Schedule local notification ─────────────────────────────────────────────

export async function scheduleLocalNotification(
  title: string,
  body: string,
  data?: Record<string, unknown>,
  delaySeconds: number = 0
): Promise<string> {
  const trigger =
    delaySeconds > 0 ? { seconds: delaySeconds } : null;

  return await Notifications.scheduleNotificationAsync({
    content: {
      title,
      body,
      data: data ?? {},
      sound: true,
    },
    trigger,
  });
}

// ── Cancel all scheduled notifications ──────────────────────────────────────

export async function cancelAllNotifications(): Promise<void> {
  await Notifications.cancelAllScheduledNotificationsAsync();
}

// ── Get badge count ─────────────────────────────────────────────────────────

export async function getBadgeCount(): Promise<number> {
  return await Notifications.getBadgeCountAsync();
}

export async function setBadgeCount(count: number): Promise<void> {
  await Notifications.setBadgeCountAsync(count);
}
