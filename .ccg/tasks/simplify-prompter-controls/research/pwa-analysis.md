# PWA analysis

Scope: offline/install behavior only. Read the current frontend spec and production loading/settings code. This is independent source analysis; the parent reports that both required external Claude analysis calls failed with HTTP 401, so those calls are not successful reviews.

## Files Found

- `worker.js:1`: unregistered legacy worker. Installs an unversioned `teleprompter-app` cache containing only three hardcoded `/teleprompter/` URLs; fetches use global `caches.match` without method/origin filtering.
- `manifest.json:1`: already has relative start/scope/icon URLs, standalone display, Chinese labels, and valid declared 192/512 icon sizes. Needs only bounded metadata changes, such as a stable relative `id`.
- `index.html:14`: manifest is fetched unconditionally, including under `file://`; the classic deferred scripts at lines 18–19 have no registration module.
- `index.html:87`: native settings dialog provides the installation/status insertion point. Existing help only briefly mentions Safari home-screen installation at line 136.
- `app.js:45`: all reader activity is private to the app IIFE. `startPlayer`/`exitPlayer` toggle `body.is-presenting` at lines 401/440. `updateDocument` synchronously saves the current draft at line 131, but saving can fail without preventing editing (`writeStorage`, line 53).
- `document-import.js:14`: captures its own script URL for `vendor/fflate-0.8.3.min.js`; `loadZipLibrary` at line 42 injects this classic script on the first DOCX import.
- `vendor/fflate-0.8.3.min.js`, `favicon.ico`, `apple-touch-icon.png`, `icon-192.png`, `icon-512.png`, `icon.png`: existing local resources; no CDN/runtime font dependency was found in the HTML/CSS.
- `styles.css:19`, `styles.css:42`, `styles.css:101`: reliable `[hidden]`, 44 px button targets, and a scrollable dialog body are reusable.
- `tests/verify_ui.py:100`: existing Python unittest + synchronous Playwright harness; creates fresh contexts and collects page/console errors. Its vendor failure interception at line 407 conflicts with a live worker cache.
- `.ccg/spec/frontend/index.md`: requires static deployment, relative URLs, direct-file compatibility, local-only DOCX processing, and storage failures that preserve editing.

## Dependencies

```text
index.html
  -> styles.css
  -> document-import.js -> lazy vendor/fflate-0.8.3.min.js
  -> [new script-library module, final filename owned by parent]
  -> app.js
  -> new pwa.js -> conditional manifest link + scoped worker registration
worker.js -> one versioned cache containing the complete installed app shell
manifest.json -> local icons + relative app entry/scope
```

The PWA module should not read or write draft/library/settings storage. Native worker waiting gives safe updates without accessing `app.js` state, dispatching save events, or adding dirty-state APIs.

## Patterns and recommended implementation

### Independent file ownership

- PWA implementation owner: `worker.js`, `manifest.json`, new `pwa.js`, new `tests/verify_pwa.py`.
- Parent/UI owner: the exact head/settings markup below in `index.html`; any small spacing/wrapping rules in `styles.css`; the final new library script filename and placement.
- Existing test owner: disable service workers in the ordinary UI/import regression contexts, including helper-created contexts. Dedicated PWA tests explicitly allow workers. This preserves the intent of `page.route` import-failure tests without weakening PWA coverage.
- Parent/docs owner: explain offline preparation, browser-specific installation, and the close-all-windows update workflow in README/spec. Every shipped app-shell change must bump the worker cache version.

### Exact DOM contract for the parent

Replace the unconditional manifest link with an inert link; `pwa.js` sets its absolute `href` only on HTTP(S). Add the classic deferred PWA script after the existing application scripts. Classic scripts preserve direct-file loading.

```html
<link rel="manifest" id="appManifest">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<!-- Existing document-import, library, and app scripts remain in their order. -->
<script src="./pwa.js" defer></script>
```

Insert one section into `.dialog-body`, before `.help-notes`; keep install text visible because this action needs an understandable label.

```html
<section class="settings-section" id="pwaSettings" aria-labelledby="pwaSettingsTitle">
  <h3 id="pwaSettingsTitle">安装与离线</h3>
  <p class="section-description" id="pwaStatus" role="status" aria-live="polite">正在检查离线状态…</p>
  <button type="button" class="tonal-button" id="installAppBtn"
          aria-describedby="pwaInstallHint" hidden>安装到设备</button>
  <p class="section-description" id="pwaInstallHint">可通过浏览器菜单添加到主屏幕或安装应用。</p>
</section>
```

`pwa.js` exclusively owns these status/hint strings and the install button's hidden/disabled state. It must tolerate absent optional nodes. No update button or new dialog is needed. Normal settings close/focus behavior stays in `app.js` (`app.js:661`).

### Registration and installation UI (`pwa.js`)

1. Capture the module's base URL synchronously from `document.currentScript.src`, following `document-import.js:14`. Resolve `manifest.json`, `worker.js`, and the containing-directory scope against that captured URL, not an absolute `/teleprompter/` path or a later `document.currentScript` read.
2. Set the manifest link only for `http:` or `https:`. Before service-worker API access, require one of those protocols, a secure context, and `serviceWorker` support. This allows HTTPS GitHub Pages and trustworthy HTTP localhost/127.0.0.1; direct file use must issue neither manifest fetches nor registration attempts. In unsupported contexts show a calm, useful status and preserve all normal app features.
3. Call `register(workerURL, { scope: baseURL.href, updateViaCache: 'none' })`; catch all registration/update promises. No console logging is needed for optional capability failures. Inspect the returned registration's existing `installing`, `waiting`, and `active` workers as well as future `updatefound`/`statechange` events; do not miss an installation already in progress when registration resolves.
4. Report offline readiness after this registration has an activated worker and the page is controlled. Registration acceptance alone does not prove that precaching succeeded. Avoid treating an unrelated broader-scope `navigator.serviceWorker.ready` registration as proof. Observe `controllerchange` to refresh status only, never to navigate.
5. Capture `beforeinstallprompt`, call `preventDefault`, and expose the button only while a usable deferred prompt exists and the app is not standalone. Invoke `prompt()` directly in the click handler before awaiting `userChoice`; disable while pending, consume/clear the event on either outcome, and handle rejection. Hide the button on `appinstalled`. A later fresh event may expose it again.
6. Detect standalone via `(display-mode: standalone)` and `navigator.standalone === true`. For iPhone/iPad outside standalone, show “在 Safari 中打开，轻点‘共享’，再选‘添加到主屏幕’。” Include iPad desktop-mode detection (`MacIntel` plus multiple touch points). Other browsers get a menu-based fallback when no native prompt exists. Unsupported `beforeinstallprompt` is normal, especially on iOS.
7. Keep status changes inside settings. Never open the dialog, prompt automatically, change reading focus, clear storage, or refresh the document. A browser recheck on ordinary page registration is sufficient; periodic update timers are unnecessary for this scope.

### Offline worker (`worker.js`)

- Use a release identifier plus a deployment-specific prefix, for example `flow-teleprompter::${encodeURIComponent(self.registration.scope)}::shell-v1`. CacheStorage is origin-wide: including the scope prevents root and Pages/subdirectory installations from deleting or reading each other's generations.
- Precache `index.html`, `styles.css`, `app.js`, `document-import.js`, `pwa.js`, the final new library JS module, `manifest.json`, `favicon.ico`, `apple-touch-icon.png`, `icon-192.png`, `icon-512.png`, `icon.png`, and `vendor/fflate-0.8.3.min.js`. Resolve all URLs against `self.registration.scope`. The parent must confirm the library filename before integration. Do not add unused audio/video, research files, or external credit links.
- Use one `event.waitUntil(cache.addAll(...))` installation transaction, with requests using `cache: 'reload'` to bypass stale browser HTTP-cache entries. Installation must fail if a required asset cannot be cached; do not activate a partially prepared generation. Distinct releases must use distinct cache names so a failed update cannot damage the active generation.
- Do **not** call `skipWaiting`, including from install handlers or messages. On activation, delete only older cache names beginning with this exact scoped prefix, then `clients.claim()` so the first prepared install can serve lazy assets without requiring a reload. Never delete all origin caches. The old unscoped `teleprompter-app` cache can be left unused; deleting it from an arbitrary scope could affect another still-active legacy installation.
- Intercept only GET requests from the same origin and inside the registration scope. Use an explicit app-shell resource allowlist. Let unrelated URLs/methods use normal browser networking; do not cache arbitrary navigation, imported documents, or external requests.
- Serve the active generation's cached shell and static assets first, looking only in `caches.open(CACHE_NAME)`, never global `caches.match`. Canonicalize only the known app entry paths (the scope directory and its `index.html`) to cached `index.html`; this supports both entry URLs and harmless entry query strings offline. Unknown paths should retain normal server/404 behavior.
- Do not network-refresh cached HTML independently of cached JS/CSS. On this unbundled site that can load new HTML against old scripts and break DOM contracts. A fully precached generation plus natural waiting keeps each open session consistent. Missing cached resources may use normal network fallback, without populating arbitrary runtime entries.

### Safe update policy

When `registration.waiting` exists, report “有新版本；结束后关闭所有提词器窗口，再重新打开即可更新。” Preserve the existing active worker and cache while any controlled page remains. Closing just one of several tabs must not activate the waiting worker. On next activation, scoped old caches can be removed because the prior generation has no controlled pages left.

This policy needs no editing/reading/import locks and makes no automatic `location.reload`, navigation, or forced activation. Even a paused reader, failed localStorage write, pending import, or a second tab's unsaved draft remains untouched. A normal browser reload may still be served by the old worker while another controlled window remains; document the close-all-windows requirement rather than promising that one refresh always updates.

### Manifest (`manifest.json`)

Retain `start_url: "./"`, `scope: "./"`, `display: "standalone"`, the existing colors/language/icons, and add stable relative `id: "./"`. Keep orientation unrestricted for landscape reading. Do not claim maskable icon support without inspecting/designing safe-zone artwork; current icons may remain `purpose: "any"` or use its default. No install-prompt capability is guaranteed just by adding manifest fields.

## Meaningful verification

Use the existing Python + Playwright conventions, with a separate stdlib HTTP server fixture for PWA lifecycle tests. Serve real worker files over localhost; Playwright page request interception is not a reliable way to replace worker installation resources. For update tests, mutate only a temporary served copy or in-memory server responses, never production files.

1. **Real offline bootstrap:** visit online, wait for the correct activated/controller state, take the context offline, then reopen/reload both the directory entry and `index.html?source=offline`. Verify the shell, styles, editing, saved library content, and playback work; assert responses come from the worker where appropriate.
2. **First-ever offline DOCX:** before any online DOCX import, verify `window.fflate` is undefined, go offline, generate a small deflated DOCX in memory (`tests/verify_ui.py:46` pattern), import it, and verify text. This catches the most important missing-precache regression while preserving lazy execution.
3. **Scope:** run the same bootstrap under `/` and a nested Pages-style path, check registration scopes/resource URLs, and prove unrelated root paths are not intercepted by the nested worker.
4. **Waiting without interruption:** keep two controlled pages open, one reading and one editing, publish a new worker version/assets, request `registration.update`, and wait for `waiting`. Assert no document navigation/controller replacement, draft change, focus theft, or reader reset. Close only one page and confirm the worker still waits; close all and reopen to verify the new generation activates.
5. **Owned cleanup:** seed an unrelated cache and another scope's cache, update/activate, then assert only this scope's older generations disappear. Confirm user localStorage/library data remains.
6. **Failed precache:** return a 404 for a required new-release asset. Assert the old worker/cache remain functional offline and no misleading “offline ready” state is shown for a failed first install.
7. **Direct file and unsupported capability:** load the local file in Chromium/WebKit; assert no manifest request, worker registration, page error, or console error, and verify editing/import still work. Stub an unsupported/rejected registration separately to check graceful UI.
8. **Install UI:** synthetic prompt events can verify click-only prompting, dismissal/acceptance cleanup, `appinstalled`, standalone hiding, and iOS help. They do not prove native installation; actual home-screen installation remains a browser/device smoke check. Check the settings section at 320 px width and in landscape.

## Risks

- A worker makes ordinary Playwright `page.route` vendor-failure tests unreliable (`tests/verify_ui.py:407`) and may alter network-request assertions (`tests/verify_ui.py:299`). Block workers only in the ordinary UI/import suite; retain enabled coverage in the dedicated suite.
- A static manifest `href` can cause file-scheme CORS console errors before script-level capability guards run. Conditional association must happen in the head/PWA contract, not just around registration.
- Forgetting the release-version bump can leave existing installs on old HTML/JS indefinitely. Treat app-shell changes and cache-version updates as one release operation; include the new library module in the precache immediately.
- Global cache matching/deletion leaks across apps on shared GitHub Pages origins. Scope every cache namespace and match the current cache explicitly.
- A forced refresh after successful storage writes is still unsafe across tabs, pending imports, or storage failures. Natural waiting removes this unnecessary integration risk.
- Browser storage eviction and iOS installation support are platform-controlled. Describe offline availability as prepared after an online visit; do not promise permanent storage or a programmatic iOS install dialog.
