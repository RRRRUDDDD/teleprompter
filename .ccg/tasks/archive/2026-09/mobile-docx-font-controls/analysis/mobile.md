## Analysis: 移动端适配 + DOCX 导入 + 提词页字号控件

Read: `index.html` (216 lines), `styles.css` (381), `app.js` (618), `.ccg/spec/frontend/index.md`, plus the archived validation harness under `.ccg/tasks/archive/2026-09/modernize-teleprompter-ui/validation/`.

### Current State

- Single-file-per-concern static app, no build. `app.js` is one IIFE; all state in `settings` / `session` / `preview`. Mobile is already the base stylesheet, desktop lives in `@media (min-width: 901px)` (`styles.css:244-313`). Preserving desktop therefore means **not touching the base rules' box sizes without a matching desktop override**.
- Player controls: `restart | speed− value speed+ | 暂停 | exit` (`index.html:193-199`). Tap-to-pause and drag-to-scrub already exist via Pointer Events with a 6px tap threshold (`app.js:511-535`).
- Import is TXT-only, extension-gated, 1 MB cap, `replaceDraft` gives undo (`app.js:463-474`).
- Prior validation (17 Chromium + 17 WebKit Playwright checks, axe 0 violations) is archived and reusable; it contains 3 references to `#pauseBtn` that will need updating in the new task's copy.

---

### 1. Mobile adaptation — concrete gaps found

| # | Issue | File | Minimal fix |
|---|---|---|---|
| M1 | **Toolbar overflows at 320px once pause is replaced.** Today at ≤370px: 44 + (44+25+44) + 73 + 44 + padding 12 + gaps 6 = **292px** inside a 296px box — it fits by 4px. A size stepper (113px) instead of 暂停 (73px) makes it 332px. | `styles.css:358-361`, `index.html:193-199` | In the `max-width: 370px` block add `flex-wrap: wrap; row-gap: 6px;` to `.player-toolbar` (two rows: steppers / restart+exit). 390px still fits one row (332 ≤ 366), so desktop and 390 are untouched. |
| M2 | **Landscape 844×390 loses ~60% of the reading area** to the bottom mask: `mask-image` fades from `calc(100% - 135px)` (`styles.css:192`), leaving ~200px of readable text at 390px height. | `styles.css:192`, `365-377` | Hoist the two mask stops into a var (`--reader-fade-end/-start`) and shrink them in the existing `(max-width:900px) and (max-height:520px)` block (e.g. 96px/56px). Base + desktop values unchanged. |
| M3 | **320×568 portrait needs ~760px of scroll** before reaching 开始提词, ~110px of it decorative intro. The short-viewport compaction only triggers at `max-height: 520px`. | `styles.css:50-56`, `365-377` | Add a narrow-portrait rule (`@media (max-width: 340px)`) that trims `.page-intro` padding/`h1` size, or extend the existing compaction to `max-height: 600px`. Don't hide the tabs. |
| M4 | **No horizontal safe-area on header/main.** `.header-inner { padding: 0 20px }` and `.app-main { padding: 0 18px }` ignore `env(safe-area-inset-left/right)`; only `.launchbar` handles it. Notched iPhone in landscape clips the brand and card edges. | `styles.css:38`, `49` | `padding-left: max(18px, env(safe-area-inset-left))` etc. Desktop block already overrides both paddings to 0 with a centered width, so no desktop impact. |
| M5 | **No top safe-area.** `viewport-fit=cover` + `display: standalone` (manifest) means the 68px header can sit under the status bar on notched iPhones added to the home screen. | `styles.css:37`, `index.html:5` | `.app-header { height: auto; min-height: 68px; padding-top: env(safe-area-inset-top) }`; the desktop block sets `height: 75px` — change it to `min-height` there too. |
| M6 | **Sub-44px touch target:** `.guide-controls input[type="color"]` is 23×36 with only an `sr-only` label, so there is no larger hit area (`styles.css:170`, `index.html:169`). | `styles.css:170` | In the `max-width: 900px` block: `height: 44px; width: 34px`. The desktop-only sizing stays in `@media (min-width: 901px)`. |
| M7 | Toast is not keyboard-aware (`bottom: calc(100px + safe-area)`), unlike `.launchbar` which uses `--keyboard-offset`. | `styles.css:240` | `bottom: calc(100px + env(safe-area-inset-bottom) + var(--keyboard-offset, 0px))`. Low priority. |

Verified as already correct, do not "fix": `100svh`/`100dvh` usage, 16px font on every mobile input (no iOS zoom), `--keyboard-offset` logic (`app.js:579-585`) with the `>120px` guard, `interactive-widget=resizes-content`, `.app-main` bottom padding (124px vs 73px launchbar), `touch-action: manipulation` on controls and `touch-action: none` on the reader, all `env()` insets in `.player-hud` / `.player-bottom` / `.launchbar`.

---

### 2. DOCX import

#### Options

| Option | Pros | Cons | Effort |
|---|---|---|---|
| **A. `DecompressionStream('deflate-raw')` + ~80-line ZIP/central-directory reader + `DOMParser`** | Zero dependencies, no new files, keeps the "文稿只留在你的设备" claim and the no-build rule literal; ~2.5 KB of `app.js` | You own edge cases (ZIP64, STORED entries, strict-OOXML namespace); needs Safari 16.4+ / Chrome 103+ | M |
| B. Vendor `jszip.min.js` (~96 KB) or `mammoth.browser.min.js` (~200 KB+) | Battle-tested on exotic documents; works without `DecompressionStream` | New tracked binary blob, license/update burden, contradicts the lean static profile, slower first paint on mobile data | S–M |
| C. TXT only + "请另存为 .txt" | No risk | Doesn't meet the requirement | — |

**Recommendation: A, with B as a documented fallback** if real-world files prove flaky, and a clear message when `DecompressionStream` is missing (`此浏览器暫不支持 DOCX，请另存为 .txt 后导入`) — that covers iOS < 16.4 and stripped WebViews.

#### Implementation notes (all inside `app.js`, near `app.js:463-474`)

```
readDocx(file):
  bytes = new Uint8Array(await file.arrayBuffer())
  find EOCD (0x06054b50) scanning back ≤64 KB; if not found or ZIP64 marker → throw
  walk central directory → locate entry matching /^word\/document(\d*)\.xml$/ (localName-agnostic)
  read local header → payload; method 8 → DecompressionStream('deflate-raw'), method 0 → raw slice
  DOMParser.parseFromString(utf8, 'application/xml'); reject if querySelector('parsererror')
  TreeWalker over elements, dispatch on **localName only**:
    't' → += textContent | 'tab' → '\t' | 'br'/'cr' → '\n' | end of 'p' → '\n'
    skip 'instrText', 'delText' (field codes / tracked deletions)
```

Pitfalls to design for:

1. **Namespace:** Strict OOXML uses `http://purl.oclc.org/ooxml/wordprocessingml/main`, not the 2006 URI. Match by `localName`, never by `w:t` tag string.
2. **Data descriptors:** local-header sizes can be zero-with-bit-3-set. Take sizes from the central directory, not the local header.
3. **Import race / clobber.** `app.js:463` already awaits; DOCX inflate is slower, so a second pick, a 清空, or 开始提词 mid-parse can be overwritten. Add an `importToken` counter, capture it before the await, bail if it changed; also bail if `active()`. Disable `#importBtn` and swap its label to `正在解析…` while parsing (also prevents double-tap on mobile).
4. **Never overwrite on failure** (explicit requirement): empty extraction, parse error, unsupported, or over-limit must `showToast(...)` and `return` before `replaceDraft`.
5. **Distinct messages** for `.doc` / `.pages` / `.pdf` — users will try them. Keep extension-based validation; iOS Files often hands over an empty `file.type`.
6. **Two caps:** file size (~4 MB for DOCX, keep 1 MB for TXT) *and* extracted length (reject above ~200–300 k chars). Reject rather than silently truncate. Note the pre-existing perf risk: `pre-wrap` reflow on a 1 M-char draft is already slow and gets re-triggered on every font-size tap (§3).
7. `accept` becomes `.txt,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document` (`index.html:89`) — treat it as a hint only; Android pickers ignore it.
8. Copy to update: help step 01 (`index.html:208`, says "UTF-8 的 .txt"), the import button's desktop label (`index.html:86`), `README.md`. Rendering stays `textContent` (`app.js:124`, `401`) so `<script>` inside `w:t` is inert — keep it that way.

---

### 3. Pause → font-size stepper

Structure to mirror `.player-speed` (`index.html:196`): `role="group" aria-label="字号"`, `#smallerFontBtn` / `#playbackFontSize` (`aria-live="polite"`) / `#largerFontBtn`, step **2px**, bounds reuse `numericBounds.fontSize` = [10,100]. `changeSetting('fontSize', …)` already writes `#text` style, syncs `#fontSize` + `#fontSizeRange`, and persists (`app.js:113-117`, `79-111`), so "同步设置与保存" is free.

Four things will break or drift if not handled:

1. **`beginPlayback()` calls `$('pauseBtn').focus()` (`app.js:382`)** — a dangling ID throws `TypeError` on null and kills every countdown start. Retarget it. Best answer: make `#readerViewport` focusable (`tabindex="0"` + `aria-label="轻点暂停或继续提词"`) and focus that — it also gives the tap-to-pause gesture its first keyboard/AT equivalent.
2. **Space-key guard references `pauseBtn` (`app.js:227`).** Simplify to `if (event.target.closest('button')) return;` so Space on a focused ± button performs native activation while Space on the reader toggles pause. Keep `togglePause()` itself — tap, Space, gamepad button 0 (`app.js:291`) and `visibilitychange` (`app.js:251`) all depend on it.
3. **Reading position and progress drift.** `applySettings()` changes `#text` font size but nothing updates `session.textHeight` / `startY` / `y`, and `renderPosition()`'s travel term uses `settings.fontSize` (`app.js:232-239`). The fraction-preserving re-anchor already exists inside `reflow()` (`app.js:586-599`) — extract it (e.g. `syncReaderMetrics()`) and call it from both. This is the single most important correctness item, and it satisfies "调整字号不重置阅读进度或播放状态" (`mode` and `session.elapsed` are untouched by `changeSetting`).
4. **Lost state affordance.** With the button gone, paused state is signalled only by `#playbackStatus` (`role="status"`, `app.js:225`) — and `.player-tip` is `display: none` in landscape (`styles.css:373`). Drive the tip text from `renderPlaybackState()`: playing → `轻点画面暂停 · 上下拖动调整位置`, paused → `轻点画面继续`, finished → `轻点画面重播`. Also drop `$('pauseBtn').disabled` / `#pauseLabel` / `#pauseIcon` from `renderPlaybackState` (`app.js:226-229`); `#i-pause` stays in use by the preview toggle.

Secondary points:

- **Finished state** currently replays via the pause button. Tap-to-reader already routes to `restartPlayback()` (`app.js:265`) and `#restartBtn` covers the button path — no new control needed, but emphasize `#restartBtn` when `.player[data-state="finished"]` (dataset is already set at `app.js:224`).
- Add `$('playbackFontSize').textContent = settings.fontSize` beside `playbackSpeed` (`app.js:106`), and disable ± at the bounds there (worth doing for the speed pair too — right now the value silently stops moving at 10/100).
- Allow font changes during `countdown`; the re-anchor keeps the first line at the guide line. Keep `#restartBtn` disabled as-is.
- Optional, cheap: `Minus`/`Equal` keys for ±2 in the keydown map (`app.js:232-236`), documented in `.shortcut-strip` (`index.html:122`) and the help `<dl>` (`index.html:209`). Leave the gamepad map alone.
- No new pause risk from the buttons: `.player-bottom` is `pointer-events: none` with `.player-toolbar` re-enabled and is a sibling of `#readerViewport` (`styles.css:202-204`), so taps never reach the drag handler. Confirm with a test anyway (#15 below).
- Known cosmetic debt the new stepper would inherit: `.player-speed small { font-size: 8px; color: #92aa9b }` on `#25372fe8` is ≈3.4:1 — below AA. axe passed previously because the player is `hidden` during the editor scan. Bump to ~`#a9c0b1` / 9px and scan with the player open.
- `applySettings()` ends in `stopPreview(true)`, which measures `#previewStage` while `#controls` is hidden → scale ≈ 0.0009. Harmless (recomputed on exit, and the speed buttons already do this today) but it now runs on every font tap; guard with `if (!active())` if you want it clean.

---

### Risks & Mitigations

1. `#pauseBtn` removal breaks `beginPlayback` focus and the Space guard → grep `pauseBtn|pauseIcon|pauseLabel` across `index.html`, `app.js`, `README.md`, and the new validation script before finishing.
2. Toolbar overflow at 320px → assert the toolbar's bounding box is inside the viewport at 320×568 in a browser test, not by eyeballing.
3. Font change desyncs reading position → assert `aria-valuenow` before/after ± within a small tolerance.
4. DOCX parser too strict for real files → ship the explicit-failure path first (draft untouched + actionable toast), keep Option B in reserve.
5. `DecompressionStream` unavailable → feature-detect and message; verify with `delete window.DecompressionStream`.
6. Base-stylesheet edits leaking to desktop → every mobile size change goes in `@media (max-width: 900px)` / `max-width: 370px`, or gets a paired override in the 901px block.
7. GitHub Pages subpath — `worker.js` is **not registered anywhere** and hardcodes `/teleprompter/` paths. Leave it alone; don't register a service worker in this task or a stale cache will mask the update.

---

### Test Scenarios (extend the archived `verify_ui.py` / `capture_ui.py` pattern)

Layout — 1) 320×568: no horizontal overflow (`scrollWidth <= innerWidth`), player toolbar box within viewport, every control ≥40×40. 2) 390×844: single-row toolbar, all controls in bounds. 3) 844×390 presenting: text visible above the fade, HUD/toolbar clear of the guide line, rotation preserves reading fraction (existing test). 4) Focus `#inputText`, assert the launchbar stays visible and `--keyboard-offset` is `0px` under `resizes-content`; state plainly that a real soft keyboard and on-device screen readers are still unverified (as `validation/results.md` already does).

DOCX — 5) Happy path: build the `.docx` in Python `zipfile` with two paragraphs plus `w:tab` and `w:br` → paragraphs preserved, toast shown, panel switches to editor, value survives reload. 6) Empty body → toast, draft unchanged. 7) Random bytes with a `.docx` name → toast, draft unchanged, zero `pageerror`. 8) `.doc` / `.pdf` / oversized file / over-length extraction → distinct messages, draft unchanged. 9) Race: two `set_input_files` back-to-back, and a docx import immediately followed by 清空 → latest user action wins. 10) `delete window.DecompressionStream` → DOCX shows the save-as-txt message, TXT import still works. 11) `w:t` containing `<script>` → rendered as text, `window.injected` is null.

Player font size — 12) Start without countdown, `+`×3 → `#playbackFontSize`, `#fontSize`, `#fontSizeRange` all agree, `data-state` still `playing`, `aria-valuenow` within tolerance, value persists after reload. 13) `−` to 10 → clamps, button disabled, no error. 14) After `+`, tap the reader → `paused`, tap again → `playing`; 40px drag still does not pause. 15) Clicking `+` alone never changes `data-state`. 16) Finished: short text at speed 100 → `finished`, reader tap restarts, `#restartBtn` enabled. 17) During countdown: ± usable, `#restartBtn` disabled, no error. 18) Space with focus on the reader toggles pause; Space with focus on `#fasterBtn` bumps speed instead. 19) Mirror on: `#readerMirror` is `scaleX(-1)`, toolbar unmirrored after a font change. 20) Fullscreen API deleted → player still fills the viewport, font controls work. 21) axe-core run **with the player open** (new coverage — catches toolbar contrast and stepper labels). 22) Serve under `/teleprompter/` and confirm no absolute paths were introduced.

---

### Action Items

1. [ ] `app.js` — extract `syncReaderMetrics()` from `reflow()`; call it after any `fontSize` change.
2. [ ] `index.html` / `app.js` — replace `#pauseBtn` with the `#smallerFontBtn` / `#playbackFontSize` / `#largerFontBtn` group; make `#readerViewport` focusable; retarget `beginPlayback()` focus; fix the Space guard; drive `.player-tip` from `renderPlaybackState()`; render + bound-disable the value in `applySettings()`.
3. [ ] `styles.css` — M1 toolbar wrap at ≤370px, M2 landscape mask vars, M4/M5 safe-area insets, M6 guide colour-input target, M3 narrow-portrait intro trim, M7 toast offset. Every change scoped to mobile media queries or paired with a desktop override.
4. [ ] `app.js` — DOCX reader (Option A) + feature detection + `importToken` race guard + `active()` bail + size/length caps + per-failure messages; `accept` attribute update.
5. [ ] Copy: help dialog step 01 and shortcuts, `.shortcut-strip`, import button label, `README.md` (it still documents a 暫停 button and `.txt` only).
6. [ ] New `.ccg/tasks/mobile-docx-font-controls/validation/`: copy the archived harness, drop the 3 `#pauseBtn` assertions, add scenarios 1–22, run Chromium + WebKit + axe (player open), `node --check app.js`, `git diff --check`, refresh screenshots at 320/390/844-landscape.

---
SESSION_ID: cf3d7703-2e0b-4a94-8a35-664acf267c32
