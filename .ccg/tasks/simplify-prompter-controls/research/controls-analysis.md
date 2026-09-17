# Control cleanup analysis

Independent local source review after the two required external analysis requests failed with HTTP 401. References below describe the source reviewed before implementation. No production files changed and no tests run for this research-only subtask.

## Files Found

- `app.js` — startup/storage, import status, settings synchronization, reader lifecycle, keyboard/fullscreen handling.
- `index.html` — sample action, icon-button labels, start hint, font panel and toolbar markup.
- `tests/verify_ui.py` — browser regressions and reusable reader/settings helpers.
- `tests/capture_ui.py` — screenshots; currently assumes an initial sample and opens the font panel.
- `README.md:10`, `README.md:13`, `README.md:30`, `index.html:135` — obsolete sample/panel/help wording.
- `.ccg/spec/frontend/index.md` — preserve saved empty drafts, optional browser APIs, native dialog focus restoration, control keyboard behavior, and reading progress on font/viewport changes. Its old panel/slider description will need updating.

## Dependencies

### Startup and removals

- `app.js:9` reads `importLabel` before any event registration. `setImportBusy(false)` at `app.js:459` writes that label again. Replace both dependencies with the import button's accessible name before deleting its text span.
- `SAMPLE_TEXT` is used only for the startup fallback (`app.js:458`) and sample click (`app.js:469`). Remove the constant and handler; initialize from `savedDraft === null ? '' : savedDraft` (or `savedDraft ?? ''`). Keep `savedText`, defensive storage handling, and `updateDocument()` intact. Do not migrate or erase already saved content, including previously saved samples and empty strings.
- `startHint` is written by every `applySettings()` call (`app.js:112`), including initial `updateDocument()`. Remove that assignment and the HTML hint only. Countdown normalization, selector, overlay, timer, and start/exit lifecycle are independent and should stay.
- Remove `setFontSizePanel` (`app.js:202`) and calls in start, exit, and initialization (`app.js:402`, `app.js:441`, `app.js:460`). Remove `fontSizeBtn`, `closeFontSizeBtn`, and `playerFontSizeRange` listeners (`app.js:527`). Remove the player range update/ARIA write (`app.js:94`, `app.js:97`). Keep settings-dialog `fontSizeRange` and its listener.
- Remove `session.panelEscapeTime` declaration/reset (`app.js:43`, `app.js:394`) and both Escape suppression branches (`app.js:568`, `app.js:598`). Keep the remaining session fields and cleanup.

### Reuse the font adjustment path

`smallerFontBtn` / `largerFontBtn` → `changeFontSizeBy(-2 / 2)` (`app.js:530`) → `changeSetting` (`app.js:120`) → `applySettings(true)` → `measureReader()` → `saveSettings()`.

- Keep the two existing button IDs, `playerFontSizeValue`, 10–100 bounds, ±2 handlers, boundary `disabled` state, settings-input synchronization, and storage key.
- `measureReader()` (`app.js:227`) preserves the prior reading fraction, recomputes text height/travel, cancels an active drag safely, and redraws progress. It does not reset `mode`, elapsed time, or animation state. Do not route font clicks through restart/reset functions.
- Move the buttons/value into a labelled toolbar group outside `readerViewport` and `readerMirror`, as speed already is (`index.html:157`). Remove the output's obsolete `for="playerFontSizeRange"`; its visible number/unit can follow the speed display.

## Patterns

- Icon-only Settings can retain its existing `aria-label`, `aria-haspopup`, and `aria-controls` (`index.html:50`), adding a title. Preserve `app.js:661`–`app.js:676`: opening focuses Close, and closing restores Settings focus.
- Icon-only Import needs an explicit idle `aria-label` and title. `setImportBusy()` (`app.js:176`) should switch them to “正在导入…” and back while retaining `disabled`, `aria-busy`, `aria-describedby="importHint"`, and `updateDraftControls()`. The import token/revision/undo/error paths (`app.js:471`) need no change.
- Escape should call `exitPlayer()` on the first press, before the generic control-target shortcut guard (`app.js:564`). On native fullscreen loss, the existing active/native-fullscreen condition should call `exitPlayer(false)` directly, then retain `reflow(true)`. The active guard makes a subsequent fullscreen event harmless after keyboard exit.
- `beginPlayback()` has a panel-specific focus condition (`app.js:381`). Replace it with ordinary reader focus handling. To preserve interaction with always-visible font/speed buttons during countdown, focus the reader only if focus remains on the initial Exit button or lies outside `display`; preserve focus on another toolbar button. No panel focus restoration remains.
- Keep the global control-target guard (`app.js:576`): Space/Enter on a focused font button should activate that button, and arrows must not alter scroll speed. Existing pointer handlers belong to the separate reading surface, so toolbar clicks should not pause playback.

## Risks and test updates

- **Startup crash:** dangling removed-element references will abort initialization; search all removed IDs/functions after editing.
- **Implicit sample fixtures:** `test_settings_persistence_mirror_colors_and_visibility` (`tests/verify_ui.py:459`) clicks Start without filling a draft. Add an explicit fixture. `capture_ui.py:43`–`capture_ui.py:52` also starts a fresh page without text; capture the empty homepage first, then fill a fixture for player screenshots. The later narrow screenshot reuses that saved fixture.
- **Import status:** replace `importLabel` assertions in `test_async_import_cannot_overwrite_a_later_edit` (`tests/verify_ui.py:414`) with button accessible-name/busy/disabled assertions, retaining draft protection checks.
- **Font regressions:** update tests beginning at `tests/verify_ui.py:520`, `:555`, `:608`, and `:624` to exercise visible ± buttons, settings/storage synchronization, 2 px steps, disabled 10/100 boundaries, playing/paused/finished preservation, progress, timer, completion, and replay. Replace slider arrow tests with focused-button Space/Enter and arrow isolation. One Escape should hide the player and restore Start focus. Use actual button clicks for player font changes; hidden settings inputs would bypass the interaction being verified.
- **Responsive regressions:** update `tests/verify_ui.py:731`, `:764`, and `:791` to check both font buttons/value directly, preserving 320/390/landscape/desktop bounds, ≥44 px button targets, rotation progress/timer checks, and blocked-API coverage. Preserve native fullscreen exit coverage at `:839` and countdown tests at `:653` and `:679`.
- **Evidence scripts:** remove panel opening/closing from `tests/capture_ui.py:57`, `:62`, and `:76`; record the always-visible toolbar. Prior-task validation scripts also mention the panel but are historical artifacts, not current regression entry points.
- Add a fresh-context assertion for empty text, disabled Start/Clear, absent sample/hint/panel controls, and named icon buttons. Existing saved-empty and plain-text/persistence tests already cover draft retention.

Recommended verification after implementation: JavaScript syntax check, full existing Chromium and WebKit suites, then responsive screenshot capture. Research did not execute these checks.

## Scope addition: local script library

The parent relayed the expanded user request after the initial review: prepare multiple scripts, retrieve them individually, retain the control simplification, and start without a sample. This section covers scripts only; PWA work is assigned elsewhere.

### Data model and ownership

- Introduce one versioned canonical local-storage record, e.g. `flow.teleprompter.drafts.v1`, shaped as `{version: 1, activeId, drafts: [{id, title, text, createdAt, updatedAt}]}`. Stable IDs, rather than titles or array positions, identify scripts. Keep reader settings global under the existing settings key.
- A small library module can own normalization, migration, persistence, and create/update/delete/restore operations. `app.js` remains responsible for the editor DOM, playback, imports, and notifications. If file ownership is split, agree the module API first: get active/list, update active, activate ID, create, delete with snapshot, restore, and a persistence result.
- Use a UUID when available with a local ID fallback that works without secure-context APIs. Validate record shape, unique nonempty IDs, string titles/text, and a valid active ID. Do not silently truncate saved text or discard valid records because one record is malformed.
- Maintain active document content in memory on every edit, before any storage attempt. The editor DOM must not become a second independent source of truth. Keep records in a stable list order instead of reordering the picker on every keystroke.

### Naming, new scripts, and selection

- A compact labelled native script picker, “新建文稿”, editable title, and a named delete icon satisfy the request while preserving the existing single-editor screen. Native selection also provides keyboard/mobile accessibility. A modal library is possible, but would add another focus lifecycle unnecessarily for this scope.
- Generate an editable “未命名文稿” / numbered default name. Trim surrounding whitespace and use a reasonable title limit; empty title falls back to the untitled label. Titles may duplicate because IDs distinguish records. Avoid repeatedly replacing a user's chosen title with the first text line or imported filename.
- New creates and selects an empty script. Keep at least one empty script after deleting the final record so the existing editor always has a valid target. A first visit can have one empty untitled record; it must contain no sample text.
- Selection sequence: synchronize the outgoing editor into its record; flush pending persistence; invalidate pending import/undo assumptions; select the new ID; load text/title; update counts, save status and controls; persist the active ID. Separate “render this record” from “save this textarea”, since current `updateDocument()` (`app.js:131`) writes as it renders. Avoid writing B's text into A while switching.
- Keep switching in editor mode. Playback continues to take a text snapshot at `startPlayer()` (`app.js:396`); script management need not change a running session. Returning from playback should show the same selected script.

### Legacy migration and saving

- A valid library is authoritative. Only when its key is absent should legacy `savedText` be migrated into one script; `null` means a fresh blank script and `''` means a valid saved empty script. Existing sample text stored by a previous version is user data at this point and must not be erased.
- Preserve `savedText` as a compatibility mirror of the selected script, including changes of selection. Write the canonical library first, and update the mirror only after that succeeds. Separate keys are not a transaction; never treat a successful mirror write as proof that the library was saved.
- Current `readStorage()` (`app.js:49`) conflates absence with a read exception. The library loader should distinguish missing, unavailable, invalid, and unsupported-version data. Do not overwrite an unreadable or future-format library with a new empty record. If recovering malformed data from `savedText`, preserve the raw original first; a failed backup must not trigger deletion/overwrite.
- Keep immediate model updates and a single persistence function. If serialization is debounced for a larger library, flush on selection, new/delete, import completion, Start, blur, and page hide; existing fill-then-reload tests depend on durable edits. Do not reread storage while switching, since that would replace unsaved in-memory edits after a failed write.
- Quota and disabled storage must leave all in-memory scripts usable and show a truthful unsaved state. Never clear records, truncate text, or fall back to overwriting another script to make a write succeed. The full library plus `savedText` mirror increases storage usage. Existing `writeStorage()` and `updateDocument()` share the save indicator, so a later settings/mirror success must not clear a still-failed library status.

### Import and undo races

- Current import protection (`app.js:477`–`app.js:495`) captures token, global revision, and textarea text. Add captured script ID and a monotonically increasing selection epoch. Check token, ID still exists, active ID, epoch, revision/text, and editor mode before committing. The epoch rejects A → B → A even when A's text is unchanged.
- On new/switch/delete of the active script, invalidate the pending import token and release its busy UI immediately. The old Promise may finish later but must not modify any record or clear a newer import's busy state. Preserve the existing “finally only if token still current” rule. Keep the importer itself unchanged; the app decides which script receives valid text.
- Clear and import undo must capture the target ID, prior text, and post-operation revision. Undo can restore that record only if it still exists and is unchanged; it must never write into whichever textarea happens to be selected later. A per-record revision allows safe background restoration, or the existing conservative behavior can refuse undo after selection changes.
- Delete undo needs a full detached snapshot of the deleted record and its list position, not merely the previous textarea value. Restore the same ID when absent. Preserve edits/selection made after deletion; if deletion created a pristine fallback blank script, undo may remove only that unchanged fallback and select the restored script. Otherwise restore to the library without replacing the current editor.
- Reuse `showToast()`'s one-shot undo UI (`app.js:144`), but keep clear/import undo and delete undo as separate operations with their own identity/revision checks. Render every title/preview through `textContent` or input `value`.

### Additional meaningful regressions

- Fresh blank library; missing legacy value, saved empty value, and nonempty legacy value; repeated reload does not duplicate migration. A valid library wins over a stale `savedText` mirror.
- Create A/B, rename, edit independently, switch repeatedly, reload with the active selection retained, and start playback from the selected text. Clearing A and resetting settings must not modify B.
- Delete inactive/active/final scripts; undo restores the correct record and preserves newer edits or selection. Clear/import undo after switching never overwrites another script.
- Pending import followed by switch, A → B → A, new, delete, text edit, and a second import. Stale completion/failure/finally must leave the latest selection, content, and busy state correct.
- Simulated read failure and canonical-write quota failure preserve in-memory drafts across switching and keep save status unsaved. Malformed/future library data must not be silently replaced.
- Existing legacy-injection test `test_corrupt_settings_preserve_draft_and_valid_ranges` (`tests/verify_ui.py:505`) writes `savedText` after page initialization. Once the library exists, seed the old data before first navigation or remove the library key in this migration fixture; changing only the compatibility mirror should no longer replace a valid library.

### Final storage decision: IndexedDB

The parent selected IndexedDB after the initial localStorage option above. This supersedes the canonical-storage recommendation; identity, UI, import/undo guards, and unsaved in-memory behavior still apply.

- **Tradeoff:** localStorage has a simple synchronous implementation but blocks on whole-library serialization and reaches its modest quota quickly. IndexedDB supports asynchronous writes per script and generally larger quotas, at the cost of asynchronous initialization, transaction/error handling, and test setup/cleanup. Keep only the current text mirror in `savedText`.
- Use a `drafts` object store keyed by stable script ID and a `meta` store for active ID and a one-time legacy-migration marker. Create/import/delete/restore and any corresponding active-ID update should commit in one `readwrite` transaction across both stores. Switching should persist the outgoing record and destination active ID consistently. Capture IDs/revisions before scheduling writes; never let a delayed save read the newly selected textarea.
- Initial migration must check its marker and create the migrated script, active ID, and marker in the same transaction. Empty `savedText` is still valid legacy content. A later empty library must not trigger remigration of the compatibility mirror. The legacy-injection regression must reset IndexedDB before navigation, not merely a localStorage library key.
- Announce “saved” on transaction completion, not individual request success. Avoid unrelated asynchronous work inside a live transaction, which can close automatically. Keep current in-memory records after open/read/write/abort failures and report unsaved state; prevent edits made while opening the database from being replaced by a late initial load.
- Update the `savedText` mirror after successful canonical commit, with an active-ID/revision guard so a stale completion cannot mirror a previously selected script. The mirror cannot be part of an IndexedDB transaction; IndexedDB remains authoritative even when the mirror is stale or unavailable.
