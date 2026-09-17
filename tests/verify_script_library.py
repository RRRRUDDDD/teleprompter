"""Draft storage regressions, independent of the app UI under development.

Run a static server on port 4175, then ``python tests/verify_script_library.py``.
TELEPROMPTER_TEST_URL and TELEPROMPTER_TEST_BROWSER override the URL/browser.
"""

import os
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("TELEPROMPTER_TEST_URL", "http://127.0.0.1:4175").rstrip("/")
BROWSER = os.environ.get("TELEPROMPTER_TEST_BROWSER", "chromium")
MODULE = Path(__file__).resolve().parents[1] / "script-library.js"
HARNESS = BASE_URL + "/__script_library_test__.html"


class ScriptLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = getattr(cls.playwright, BROWSER).launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(service_workers="block")
        self.context.route("**/__script_library_test__.html", lambda route: route.fulfill(
            status=200, content_type="text/html", body="<!doctype html><title>Storage test</title>"
        ))
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.load_harness()

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def load_harness(self):
        self.page.goto(HARNESS)
        self.page.add_script_tag(path=str(MODULE))

    def open_library(self, legacy=None):
        return self.page.evaluate("""async legacy => {
            window.statuses = [];
            window.statusEvents = [];
            window.library = await FlowScriptLibrary.open({
                legacyText: legacy === null ? localStorage.getItem('savedText') : legacy,
                onStatus: event => { statuses.push(event.state); statusEvents.push(event); },
            });
            return {active: library.active, records: library.list(), statuses};
        }""", legacy)

    def database_snapshot(self):
        return self.page.evaluate("""() => new Promise((resolve, reject) => {
            const request = indexedDB.open(FlowScriptLibrary.databaseName);
            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                const db = request.result;
                const tx = db.transaction(['drafts', 'meta'], 'readonly');
                const drafts = tx.objectStore('drafts').getAll();
                const meta = tx.objectStore('meta').getAll();
                tx.oncomplete = () => {
                    db.close();
                    resolve({drafts: drafts.result, meta: meta.result});
                };
                tx.onabort = () => { db.close(); reject(tx.error); };
            };
        })""")

    def open_second_tab(self):
        page = self.context.new_page()
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.goto(HARNESS)
        page.add_script_tag(path=str(MODULE))
        page.evaluate("async () => { window.library = await FlowScriptLibrary.open(); }")
        return page

    def test_blank_start_and_clone_isolation(self):
        opened = self.open_library()
        self.assertEqual(opened["active"]["text"], "")
        self.assertEqual(opened["active"]["title"], "")
        self.assertEqual(len(opened["records"]), 1)
        self.assertEqual(opened["statuses"], ["saving", "saved"])
        actual = self.page.evaluate("""() => {
            const active = library.active;
            const list = library.list();
            active.text = 'outside edit';
            list[0].title = 'outside title';
            list.length = 0;
            return {active: library.active, count: library.list().length};
        }""")
        self.assertEqual(actual["active"], opened["active"])
        self.assertEqual(actual["count"], 1)
        self.assertEqual(self.database_snapshot()["drafts"], opened["records"])

    def test_legacy_migrates_once_and_existing_empty_draft_wins(self):
        original = self.open_library("旧文稿 👋\nSecond line")["active"]
        self.page.evaluate("async () => { await library.update({text: ''}); }")
        self.load_harness()
        opened = self.open_library("stale legacy mirror")
        self.assertEqual(opened["active"]["id"], original["id"])
        self.assertEqual(opened["active"]["text"], "")
        self.assertEqual(len(opened["records"]), 1)
        snapshot = self.database_snapshot()
        self.assertIn({"key": "legacyMigration", "value": 1}, snapshot["meta"])
        self.assertEqual(self.page.evaluate("localStorage.getItem('savedText')"), "")

    def test_migration_marker_prevents_reimport_after_database_is_empty(self):
        self.open_library("legacy")
        self.page.evaluate("""() => new Promise((resolve, reject) => {
            const request = indexedDB.open(FlowScriptLibrary.databaseName);
            request.onsuccess = () => {
                const db = request.result;
                const tx = db.transaction('drafts', 'readwrite');
                tx.objectStore('drafts').clear();
                tx.oncomplete = () => { db.close(); resolve(); };
                tx.onabort = () => reject(tx.error);
            };
        })""")
        self.load_harness()
        opened = self.open_library("must not resurrect")
        self.assertEqual(opened["active"]["text"], "")
        self.assertEqual(len(opened["records"]), 1)

    def test_create_edit_select_and_refresh(self):
        first = self.open_library("first text")["active"]
        result = self.page.evaluate("""async firstId => {
            const second = await library.create({title: 'B'.repeat(140), text: 'second'});
            const pending = library.update({title: '第二篇', text: 'edited second'});
            const immediate = library.active;
            await pending;
            const selected = await library.select(firstId);
            return {second, immediate, selected, statuses};
        }""", first["id"])
        self.assertEqual(len(result["second"]["title"]), 120)
        self.assertEqual(result["immediate"]["text"], "edited second")
        self.assertEqual(result["immediate"]["id"], result["second"]["id"])
        self.assertGreater(result["immediate"]["updatedAt"], result["second"]["updatedAt"])
        self.assertEqual(result["immediate"]["createdAt"], result["second"]["createdAt"])
        self.assertEqual(result["selected"], first)
        self.load_harness()
        opened = self.open_library()
        self.assertEqual(opened["active"], first)
        self.assertEqual(len(opened["records"]), 2)
        self.assertIn(result["immediate"], opened["records"])

    def test_rapid_queue_preserves_each_draft_and_only_mirrors_final_active_revision(self):
        first = self.open_library("old")["active"]
        result = self.page.evaluate("""async firstId => {
            statuses.length = 0;
            window.mirrors = [];
            const original = Storage.prototype.setItem;
            Storage.prototype.setItem = function(key, value) {
                if (key === 'savedText') mirrors.push(value);
                return original.call(this, key, value);
            };
            library.update({text: 'first v1'});
            library.create({title: 'second', text: 'second v1'});
            const secondId = library.active.id;
            library.update({text: 'second final'});
            library.select(firstId);
            library.update({title: 'first final title', text: 'first final'});
            const immediate = library.active;
            const pendingStatuses = [...statuses];
            await library.flush();
            Storage.prototype.setItem = original;
            return {immediate, pendingStatuses, statuses, mirrors, secondId};
        }""", first["id"])
        self.assertEqual(result["immediate"]["text"], "first final")
        self.assertEqual(result["pendingStatuses"], ["saving"])
        self.assertEqual(result["statuses"], ["saving", "saved"])
        self.assertEqual(result["mirrors"], ["first final"])
        snapshot = self.database_snapshot()
        by_id = {draft["id"]: draft for draft in snapshot["drafts"]}
        self.assertEqual(by_id[first["id"]]["text"], "first final")
        self.assertEqual(by_id[result["secondId"]]["text"], "second final")
        self.assertIn({"key": "activeId", "value": first["id"]}, snapshot["meta"])

    def test_deleting_last_draft_and_restore_protects_new_edits(self):
        original = self.open_library("original content")["active"]
        result = self.page.evaluate("""async id => {
            const removed = await library.remove(id);
            const blank = library.active;
            await library.update({text: 'new work after deletion'});
            await library.restore(removed);
            return {removed, blank, active: library.active, records: library.list()};
        }""", original["id"])
        self.assertEqual(result["removed"], original)
        self.assertEqual(result["blank"]["text"], "")
        self.assertNotEqual(result["blank"]["id"], original["id"])
        self.assertEqual(result["active"]["id"], result["blank"]["id"])
        self.assertEqual(result["active"]["text"], "new work after deletion")
        self.assertIn(original, result["records"])
        self.load_harness()
        self.assertEqual(self.open_library()["active"], result["active"])

    def test_delete_nonactive_restore_and_duplicate_restore(self):
        first = self.open_library("first")["active"]
        result = self.page.evaluate("""async firstId => {
            const second = await library.create({text: 'second'});
            const removed = await library.remove(firstId);
            const afterDelete = library.active;
            await library.restore(removed);
            await library.restore({...removed, text: 'must not overwrite'});
            const missing = await library.remove('missing');
            const missingSelection = await library.select('missing');
            return {second, afterDelete, records: library.list(), missing, missingSelection};
        }""", first["id"])
        self.assertEqual(result["afterDelete"], result["second"])
        self.assertEqual(len(result["records"]), 2)
        self.assertIn(first, result["records"])
        self.assertIsNone(result["missing"])
        self.assertIsNone(result["missingSelection"])

    def test_open_failure_keeps_legacy_and_allows_memory_crud(self):
        self.page.evaluate("""() => {
            indexedDB.open = () => { throw new DOMException('blocked', 'SecurityError'); };
            localStorage.setItem('savedText', 'durable legacy');
        }""")
        first = self.open_library()["active"]
        self.assertEqual(first["text"], "durable legacy")
        result = self.page.evaluate("""async firstId => {
            await library.update({text: 'memory first'});
            const second = await library.create({text: 'memory second'});
            await library.select(firstId);
            const removed = await library.remove(second.id);
            await library.restore(removed);
            await library.flush();
            return {records: library.list(), active: library.active, statuses,
                mirror: localStorage.getItem('savedText')};
        }""", first["id"])
        self.assertEqual(result["active"]["text"], "memory first")
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["mirror"], "durable legacy")
        self.assertEqual(result["statuses"], ["saving", "unavailable"])

    def test_failed_write_is_atomic_and_later_changes_do_not_claim_saved(self):
        first = self.open_library("durable first")["active"]
        result = self.page.evaluate("""async firstId => {
            statuses.length = 0;
            const original = IDBObjectStore.prototype.put;
            IDBObjectStore.prototype.put = function(value, ...args) {
                if (this.name === 'meta') {
                    IDBObjectStore.prototype.put = original;
                    this.transaction.abort();
                    throw new DOMException('disk full', 'QuotaExceededError');
                }
                return original.call(this, value, ...args);
            };
            const created = await library.create({title: 'unsaved', text: 'memory second'});
            await library.update({text: 'latest memory second'});
            await library.select(firstId);
            await library.update({text: 'latest memory first'});
            await library.flush();
            return {created, records: library.list(), active: library.active, statuses,
                mirror: localStorage.getItem('savedText')};
        }""", first["id"])
        self.assertEqual(result["statuses"], ["saving", "unavailable"])
        self.assertEqual(result["active"]["text"], "latest memory first")
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["mirror"], "durable first")
        self.assertEqual(self.database_snapshot()["drafts"], [first])
        self.load_harness()
        self.assertEqual(self.open_library()["active"], first)

    def test_localstorage_mirror_failure_does_not_break_canonical_save(self):
        self.page.evaluate("""() => {
            Storage.prototype.setItem = () => { throw new DOMException('full', 'QuotaExceededError'); };
        }""")
        self.open_library("first")
        self.page.evaluate("async () => { await library.update({text: 'saved in IndexedDB'}); }")
        self.assertEqual(self.page.evaluate("statuses.at(-1)"), "saved")
        self.load_harness()
        self.assertEqual(self.open_library()["active"]["text"], "saved in IndexedDB")

    def test_other_tab_records_survive_and_selection_does_not_overwrite_other_tab_edit(self):
        first = self.open_library("first")["active"]
        second_page = self.context.new_page()
        second_page.goto(HARNESS)
        second_page.add_script_tag(path=str(MODULE))
        second = second_page.evaluate("""async () => {
            window.library = await FlowScriptLibrary.open();
            await library.update({text: 'edited in another tab'});
            return await library.create({text: 'created in another tab'});
        }""")
        self.page.evaluate("async id => { await library.select(id); }", first["id"])
        snapshot = self.database_snapshot()
        by_id = {draft["id"]: draft for draft in snapshot["drafts"]}
        self.assertEqual(by_id[first["id"]]["text"], "edited in another tab")
        self.page.evaluate("async id => { await library.remove(id); }", first["id"])
        self.assertIn(second, self.database_snapshot()["drafts"])
        self.load_harness()
        opened = self.open_library()
        self.assertIn(second, opened["records"])
        self.assertEqual(len(opened["records"]), 2)

    def test_stale_title_edit_preserves_other_tab_body_and_retains_local_edits(self):
        first = self.open_library("original body")["active"]
        other = self.open_second_tab()
        other.evaluate("async () => { await library.update({text: 'new body from another tab'}); }")
        before = self.database_snapshot()
        result = self.page.evaluate("""async id => {
            await library.update({title: 'local title'});
            const conflicting = library.active;
            await library.create({text: 'still usable in memory'});
            await library.select(id);
            await library.update({text: 'further local edits'});
            await library.flush();
            return {conflicting, active: library.active, count: library.list().length,
                status: statusEvents.at(-1), mirror: localStorage.getItem('savedText')};
        }""", first["id"])
        self.assertEqual(result["conflicting"]["title"], "local title")
        self.assertEqual(result["conflicting"]["text"], "original body")
        self.assertEqual(result["active"]["text"], "further local edits")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["status"], {"state": "unavailable", "reason": "conflict"})
        self.assertEqual(result["mirror"], "new body from another tab")
        self.assertEqual(self.database_snapshot(), before)

    def test_stale_delete_cannot_remove_other_tab_newer_body_or_persist_blank(self):
        first = self.open_library("original body")["active"]
        other = self.open_second_tab()
        other.evaluate("async () => { await library.update({text: 'new body survives stale deletion'}); }")
        before = self.database_snapshot()
        result = self.page.evaluate("""async id => {
            const removed = await library.remove(id);
            const blank = library.active;
            await library.update({text: 'new memory draft'});
            await library.restore(removed);
            return {removed, blank, active: library.active, records: library.list(),
                status: statusEvents.at(-1), mirror: localStorage.getItem('savedText')};
        }""", first["id"])
        self.assertEqual(result["removed"], first)
        self.assertEqual(result["blank"]["text"], "")
        self.assertEqual(result["active"]["text"], "new memory draft")
        self.assertIn(first, result["records"])
        self.assertEqual(result["status"], {"state": "unavailable", "reason": "conflict"})
        self.assertEqual(result["mirror"], "new body survives stale deletion")
        self.assertEqual(self.database_snapshot(), before)

    def test_stale_edit_cannot_resurrect_other_tab_deletion(self):
        first = self.open_library("original body")["active"]
        other = self.open_second_tab()
        other.evaluate("""async id => {
            await library.remove(id);
            await library.update({text: 'replacement from another tab'});
        }""", first["id"])
        before = self.database_snapshot()
        result = self.page.evaluate("""async () => {
            library.update({title: 'local title after remote deletion'});
            library.update({text: 'latest local body'});
            await library.flush();
            return {active: library.active, status: statusEvents.at(-1),
                mirror: localStorage.getItem('savedText')};
        }""")
        self.assertEqual(result["active"]["id"], first["id"])
        self.assertEqual(result["active"]["title"], "local title after remote deletion")
        self.assertEqual(result["active"]["text"], "latest local body")
        self.assertEqual(result["status"], {"state": "unavailable", "reason": "conflict"})
        self.assertEqual(result["mirror"], "replacement from another tab")
        self.assertEqual(self.database_snapshot(), before)
        self.assertNotIn(first["id"], [draft["id"] for draft in before["drafts"]])

    def test_future_database_is_not_downgraded_or_replaced(self):
        self.page.evaluate("""() => new Promise((resolve, reject) => {
            const request = indexedDB.open(FlowScriptLibrary.databaseName, 2);
            request.onupgradeneeded = () => request.result.createObjectStore('future');
            request.onsuccess = () => {
                const db = request.result;
                const tx = db.transaction('future', 'readwrite');
                tx.objectStore('future').put('keep this', 'sentinel');
                tx.oncomplete = () => { db.close(); resolve(); };
                tx.onabort = () => reject(tx.error);
            };
        })""")
        opened = self.open_library("recoverable legacy")
        self.assertEqual(opened["statuses"], ["saving", "unavailable"])
        self.assertEqual(opened["active"]["text"], "recoverable legacy")
        self.page.evaluate("async () => { await library.update({text: 'memory only'}); }")
        actual = self.page.evaluate("""() => new Promise(resolve => {
            const request = indexedDB.open(FlowScriptLibrary.databaseName);
            request.onsuccess = () => {
                const db = request.result;
                const tx = db.transaction('future', 'readonly');
                const sentinel = tx.objectStore('future').get('sentinel');
                tx.oncomplete = () => { db.close(); resolve({version: db.version, value: sentinel.result}); };
            };
        })""")
        self.assertEqual(actual, {"version": 2, "value": "keep this"})

    def test_invalid_database_records_are_not_overwritten(self):
        self.open_library("saved")
        self.page.evaluate("""() => new Promise(resolve => {
            const request = indexedDB.open(FlowScriptLibrary.databaseName);
            request.onsuccess = () => {
                const db = request.result;
                const tx = db.transaction('drafts', 'readwrite');
                tx.objectStore('drafts').put({id: 'unknown-format', richText: {important: true}});
                tx.oncomplete = () => { db.close(); resolve(); };
            };
        })""")
        before = self.database_snapshot()
        self.load_harness()
        opened = self.open_library("fallback")
        self.assertEqual(opened["statuses"], ["saving", "unavailable"])
        self.page.evaluate("async () => { await library.create({text: 'memory only'}); }")
        self.assertEqual(self.database_snapshot(), before)

    def test_open_timeout_returns_fallback_and_closes_late_database_handle(self):
        self.page.evaluate("""() => {
            window.lateClosed = false;
            indexedDB.open = () => {
                const request = {};
                setTimeout(() => {
                    request.result = {close: () => { window.lateClosed = true; }};
                    request.onsuccess();
                }, 3250);
                return request;
            };
        }""")
        opened = self.open_library("keep during timeout")
        self.assertEqual(opened["active"]["text"], "keep during timeout")
        self.assertEqual(opened["statuses"], ["saving", "unavailable"])
        self.page.wait_for_function("window.lateClosed === true", timeout=3000)

    def test_version_change_releases_connection_and_keeps_session_edits(self):
        self.open_library("original")
        self.page.evaluate("""() => new Promise((resolve, reject) => {
            const request = indexedDB.open(FlowScriptLibrary.databaseName, 2);
            request.onsuccess = () => { request.result.close(); resolve(); };
            request.onerror = () => reject(request.error);
        })""")
        self.page.evaluate("async () => { await library.update({text: 'kept in memory'}); }")
        self.assertEqual(self.page.evaluate("library.active.text"), "kept in memory")
        self.assertEqual(self.page.evaluate("statuses.at(-1)"), "unavailable")
        self.assertEqual(self.page.evaluate("localStorage.getItem('savedText')"), "original")


if __name__ == "__main__":
    unittest.main(verbosity=2)
