"use strict";

const CACHE_NAME = "xenomind-shell-v2";
const SHELL_URL = new URL("/", self.location.origin).href;
const APP_SHELL = ["/", "/IOS_SHORTCUTS.md", "/manifest.json", "/icon.svg", "/apple-touch-icon.png", "/voice_command_parser.js"]
  .map((path) => new URL(path, self.location.origin).href);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key.startsWith("xenomind-shell-") && key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    const navigationUrl = new URL(request.url);
    const isCockpitPage = ["/", "/index.html", "/iphone_cockpit.html"]
      .includes(navigationUrl.pathname);
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok && isCockpitPage) {
          const copy = response.clone();
          event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.put(SHELL_URL, copy)));
        }
        return response;
      }).catch(() => caches.match(request).then((cachedPage) => cachedPage
        || caches.match(SHELL_URL, { ignoreSearch: true })
        .then((cachedShell) => cachedShell || new Response("XENOMIND is offline.", { status: 503 }))))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)));
      }
      return response;
    }))
  );
});
