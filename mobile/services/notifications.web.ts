/**
 * Web Push notifications implementation.
 * Metro resolves .web.ts automatically when building for web.
 */
import apiClient from "./api";

// ── Types ────────────────────────────────────────────────────────────────────

export interface NotificationData {
  type: "price_alert" | "new_offer" | "flyer_update" | "deal_expiring";
  productId?: number;
  flyerId?: number;
  title?: string;
  body?: string;
}

// ── VAPID public key (fetched from backend) ──────────────────────────────────

let vapidPublicKey: string | null = null;

async function getVapidPublicKey(): Promise<string | null> {
  if (vapidPublicKey) return vapidPublicKey;
  try {
    const res = await apiClient.get<{ public_key: string }>("/web-push/vapid-key");
    vapidPublicKey = res.data.public_key;
    return vapidPublicKey;
  } catch (err) {
    console.error("Failed to fetch VAPID public key:", err);
    return null;
  }
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

// ── Register for push notifications ─────────────────────────────────────────

export async function registerForPushNotifications(
  userId: string
): Promise<string | null> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    console.warn("Web Push non supportato in questo browser.");
    return null;
  }

  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      console.warn("Permesso per le notifiche non concesso.");
      return null;
    }

    const publicKey = await getVapidPublicKey();
    if (!publicKey) return null;

    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });

    // Send subscription to backend
    await apiClient.post("/web-push/subscribe", {
      user_id: userId,
      subscription: subscription.toJSON(),
    });

    return JSON.stringify(subscription);
  } catch (err) {
    console.error("Errore nella registrazione push web:", err);
    return null;
  }
}

// ── Get push token (without registering) ────────────────────────────────────

export async function getPushToken(): Promise<string | null> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return null;
  if (Notification.permission !== "granted") return null;

  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    return subscription ? JSON.stringify(subscription) : null;
  } catch {
    return null;
  }
}

// ── Notification listeners (no-op on web — SW handles display) ──────────────

export function addNotificationReceivedListener(
  _callback: (notification: unknown) => void
): { remove: () => void } {
  return { remove: () => {} };
}

export function addNotificationResponseListener(
  _callback: (response: unknown) => void
): { remove: () => void } {
  return { remove: () => {} };
}

// ── Parse notification data ─────────────────────────────────────────────────

export function parseNotificationData(
  _notification: unknown
): NotificationData | null {
  return null;
}

// ── Schedule local notification ─────────────────────────────────────────────

export async function scheduleLocalNotification(
  title: string,
  body: string,
  _data?: Record<string, unknown>,
  delaySeconds: number = 0
): Promise<string> {
  if (Notification.permission === "granted") {
    if (delaySeconds > 0) {
      setTimeout(() => new Notification(title, { body }), delaySeconds * 1000);
    } else {
      new Notification(title, { body });
    }
  }
  return "web-notification";
}

// ── Cancel all scheduled notifications (no-op on web) ───────────────────────

export async function cancelAllNotifications(): Promise<void> {}

// ── Badge count (no-op on web) ──────────────────────────────────────────────

export async function getBadgeCount(): Promise<number> {
  return 0;
}

export async function setBadgeCount(_count: number): Promise<void> {}
