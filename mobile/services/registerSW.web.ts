/**
 * Register the service worker on web.
 * Metro picks .web.ts automatically when building for web.
 */
export async function registerServiceWorker(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;

  try {
    const registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
    });
    console.log("Service Worker registrato, scope:", registration.scope);

    // Check for updates periodically (every 60 minutes)
    setInterval(() => {
      registration.update();
    }, 60 * 60 * 1000);
  } catch (err) {
    console.error("Registrazione Service Worker fallita:", err);
  }
}
