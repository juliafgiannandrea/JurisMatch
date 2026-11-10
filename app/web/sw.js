// Service worker do JurisMatch.
// App shell em pré-cache (versão no nome do cache). /api/* vai sempre para a rede: busca e PDF nunca são cacheados.

const VERSAO = "v2";
const CACHE = `jurismatch-shell-${VERSAO}`;
const SHELL = [
  "/",
  "/index.html",
  "/styles.css",
  "/app.js",
  "/js/api.js",
  "/js/dom.js",
  "/js/store.js",
  "/manifest.webmanifest",
  "/icons/icon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-512.png",
  "/icons/apple-touch-icon.png",
];

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: "reload" })))));
  // Sem skipWaiting aqui: a página mostra "Atualizar" e quem decide é a pessoa.
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil((async () => {
    const nomes = await caches.keys();
    await Promise.all(nomes.filter((n) => n.startsWith("jurismatch-") && n !== CACHE).map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener("message", (ev) => {
  if (ev.data?.tipo === "pular-espera") self.skipWaiting();
});

self.addEventListener("fetch", (ev) => {
  const req = ev.request;
  if (req.method !== "GET") return; // POST /api/buscar segue direto para a rede
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/api/")) {
    ev.respondWith(fetch(req)); // sempre rede, nunca cache
    return;
  }

  if (req.mode === "navigate") {
    // Rede primeiro (pega index novo); offline cai no shell. ?q= é tratado pelo app.js.
    ev.respondWith(
      fetch(req).catch(async () => (await caches.match("/index.html", { cacheName: CACHE })) ?? Response.error())
    );
    return;
  }

  // Arquivos do shell: cache primeiro, rede como reserva.
  ev.respondWith(
    caches.match(req, { cacheName: CACHE, ignoreSearch: true }).then((hit) => hit ?? fetch(req))
  );
});
