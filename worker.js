'use strict';

// Bump the release whenever any app-shell resource changes.
const RELEASE = 'shell-20260917-v1';
const CACHE_PREFIX = `flow-teleprompter::${encodeURIComponent(self.registration.scope)}::`;
const CACHE_NAME = CACHE_PREFIX + RELEASE;
const SHELL_FILES = [
    'index.html', 'styles.css', 'app.js', 'document-import.js', 'script-library.js',
    'pwa.js', 'manifest.json', 'favicon.ico', 'apple-touch-icon.png',
    'icon-192.png', 'icon-512.png', 'icon.png', 'vendor/fflate-0.8.3.min.js',
];
const SHELL_URLS = SHELL_FILES.map((file) => new URL(file, self.registration.scope).href);
const SHELL_PATHS = new Map(SHELL_URLS.map((url) => [new URL(url).pathname, url]));
const SCOPE_URL = new URL(self.registration.scope);
const ENTRY_URL = new URL('index.html', SCOPE_URL).href;

self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE_NAME);
        try {
            await cache.addAll(SHELL_URLS.map((url) => new Request(url, { cache: 'reload' })));
        } catch (error) {
            await caches.delete(CACHE_NAME);
            throw error;
        }
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const names = await caches.keys();
        await Promise.all(names.filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
            .map((name) => caches.delete(name)));
        // First installs can serve lazy DOCX assets immediately. Updates wait naturally
        // until every page using the old worker is closed; never skipWaiting here.
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);
    if (url.origin !== SCOPE_URL.origin || !url.pathname.startsWith(SCOPE_URL.pathname)) return;
    const cachedURL = url.pathname === SCOPE_URL.pathname ? ENTRY_URL : SHELL_PATHS.get(url.pathname);
    if (!cachedURL) return;
    event.respondWith((async () => {
        const cache = await caches.open(CACHE_NAME);
        return await cache.match(cachedURL) || fetch(event.request);
    })());
});

self.addEventListener('message', (event) => {
    if (event.data?.type !== 'FLOW_OFFLINE_STATUS' || !event.ports[0]) return;
    event.waitUntil((async () => {
        let ready = false;
        try {
            const cache = await caches.open(CACHE_NAME);
            ready = (await Promise.all(SHELL_URLS.map((url) => cache.match(url)))).every(Boolean);
        } catch (_) {
            // Storage denial/eviction must not be reported as offline readiness.
        }
        event.ports[0].postMessage({ ready });
    })());
});
