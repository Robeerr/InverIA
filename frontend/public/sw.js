// InverIA Service Worker — versión mínima (solo permite instalar como PWA)
// No cachea assets para evitar conflictos con Vercel y deploys frecuentes

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", () => self.clients.claim());

// Sin caché — todas las peticiones van directo a la red
// Esto garantiza que siempre se sirve la versión más reciente del frontend
