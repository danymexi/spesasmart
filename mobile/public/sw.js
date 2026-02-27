/* eslint-disable no-restricted-globals */
const CACHE_NAME = "spesasmart-v3";
const PRECACHE_URLS = ["/", "/manifest.json"];

// ── Install: precache shell ──────────────────────────────────────────────────

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: clean old caches ───────────────────────────────────────────────

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== CACHE_NAME)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

// ── Fetch: network-first for API, cache-first for assets ─────────────────────

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== "GET") return;

  // Only handle http/https requests (skip chrome-extension://, etc.)
  if (!url.protocol.startsWith("http")) return;

  // API calls: network only (don't cache dynamic data)
  if (url.pathname.startsWith("/api/")) return;

  // For navigation requests (SPA), serve the cached index
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/"))
    );
    return;
  }

  // Static assets: stale-while-revalidate
  event.respondWith(
    caches.match(request).then((cached) => {
      const fetchPromise = fetch(request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => cached);

      return cached || fetchPromise;
    })
  );
});

// ── Push: display notification ───────────────────────────────────────────────

self.addEventListener("push", (event) => {
  let data = { title: "SpesaSmart", body: "Nuova offerta disponibile!" };

  if (event.data) {
    try {
      data = event.data.json();
    } catch {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: "/pwa-icons/icon-192.png",
    badge: "/pwa-icons/icon-192.png",
    vibrate: [200, 100, 200],
    data: data,
    actions: [{ action: "open", title: "Apri" }],
  };

  event.waitUntil(self.registration.showNotification(data.title, options));
});

// ── Notification click: open or focus the app ────────────────────────────────

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  // Determine the URL to open based on notification data
  let targetUrl = "/";
  const data = event.notification.data;
  if (data) {
    if (data.productId) {
      targetUrl = `/product/${data.productId}`;
    } else if (data.flyerId) {
      targetUrl = `/flyer/${data.flyerId}`;
    }
  }

  event.waitUntil(
    self.clients.matchAll({ type: "window" }).then((clients) => {
      // Focus existing window if available
      for (const client of clients) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      // Otherwise open a new window
      return self.clients.openWindow(targetUrl);
    })
  );
});
