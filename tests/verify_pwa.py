"""Real service-worker regressions. Run: python tests/verify_pwa.py.

An isolated localhost server serves production files under / and /teleprompter/.
Release changes and failed requests exist only in memory, never in source files.
"""

import io
import mimetypes
import re
import struct
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SHELL = (
    "index.html", "styles.css", "app.js", "document-import.js", "script-library.js",
    "pwa.js", "manifest.json", "favicon.ico", "apple-touch-icon.png", "icon-192.png",
    "icon-512.png", "icon.png", "vendor/fflate-0.8.3.min.js",
)


class AppServer:
    def __init__(self):
        self.assets = {name: (ROOT / name).read_bytes() for name in (*SHELL, "worker.js")}
        self.releases = {"/": 1, "/teleprompter/": 1}
        self.failures = set()
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                path = unquote(urlsplit(self.path).path)
                owner.requests.append(("GET", path))
                scope = "/teleprompter/" if path.startswith("/teleprompter/") else "/"
                name = path[len(scope):] or "index.html"
                if path in owner.failures:
                    self.respond(404, b"Missing test asset", "text/plain")
                    return
                if name not in owner.assets:
                    self.respond(200, b"Uncached server response", "text/plain")
                    return
                content = owner.assets[name]
                if name == "worker.js":
                    content = re.sub(
                        rb"const RELEASE = '[^']+';",
                        f"const RELEASE = 'test-release-{owner.releases[scope]}';".encode(),
                        content,
                    )
                elif name == "index.html":
                    content = content.replace(
                        b"</head>",
                        f'<meta name="test-release" content="{owner.releases[scope]}"></head>'.encode(),
                    )
                self.respond(200, content, mimetypes.guess_type(name)[0] or "application/octet-stream")

            def do_POST(self):
                owner.requests.append(("POST", urlsplit(self.path).path))
                self.respond(200, b"Uncached POST response", "text/plain")

            def respond(self, status, content, mime):
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(content)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class PWATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.server = AppServer()
        self.context = self.browser.new_context(service_workers="allow")
        self.context.add_init_script("""
            Element.prototype.requestFullscreen = undefined;
            Element.prototype.webkitRequestFullscreen = undefined;
        """)
        self.errors = []
        self.page = self.new_page()

    def new_page(self):
        page = self.context.new_page()
        page.set_default_timeout(10000)
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        return page

    def tearDown(self):
        self.context.close()
        self.server.close()
        self.assertEqual(self.errors, [])

    def open_ready(self, scope="/", page=None):
        page = page or self.page
        page.goto(self.server.url + scope)
        expect(page.locator("body")).to_have_attribute("data-library-ready", "true")
        expect(page.locator("#offlineStatus")).to_have_attribute("data-state", "ready")
        self.assertEqual(page.evaluate("navigator.serviceWorker.controller.scriptURL"),
                         self.server.url + scope + "worker.js")
        return page

    def cache_names(self, page=None):
        return (page or self.page).evaluate("caches.keys()")

    def assert_offline_bootstrap(self, scope):
        page = self.open_ready(scope)
        self.assertEqual(page.evaluate("typeof window.fflate"), "undefined")
        page.locator("#draftTitle").fill("离线文稿一")
        page.locator("#inputText").fill("已经准备好的离线文稿")
        page.locator("#openLibraryBtn").click()
        page.locator("#newDraftBtn").click()
        page.locator("#draftTitle").fill("离线文稿二")
        page.locator("#inputText").fill("第二篇也提前准备好了")
        page.locator("#openLibraryBtn").click()
        page.get_by_role("button", name="打开文稿：离线文稿一", exact=True).click()
        page.wait_for_function("localStorage.getItem('savedText') === '已经准备好的离线文稿'")
        self.context.set_offline(True)
        expect(page.locator("#offlineStatus")).to_have_attribute("data-state", "offline")
        for path in (scope, scope + "index.html?source=offline"):
            response = page.goto(self.server.url + path)
            self.assertTrue(response.from_service_worker)
            expect(page.locator("body")).to_have_attribute("data-library-ready", "true")
            expect(page.locator("#inputText")).to_have_value("已经准备好的离线文稿")
            expect(page.locator("#offlineStatus")).to_have_attribute("data-state", "offline")
            self.assertEqual(page.locator("body").evaluate("el => getComputedStyle(el).marginTop"), "0px")

        page.locator("#openLibraryBtn").click()
        page.get_by_role("button", name="打开文稿：离线文稿二", exact=True).click()
        expect(page.locator("#inputText")).to_have_value("第二篇也提前准备好了")
        page.locator("#inputText").fill("第二篇离线修改也会保存")
        expect(page.locator("#saveLabel")).to_have_text("已自动保存")
        page.reload()
        expect(page.locator("body")).to_have_attribute("data-library-ready", "true")
        expect(page.locator("#inputText")).to_have_value("第二篇离线修改也会保存")
        page.locator("#openLibraryBtn").click()
        page.get_by_role("button", name="打开文稿：离线文稿一", exact=True).click()
        expect(page.locator("#inputText")).to_have_value("已经准备好的离线文稿")

        # No previous online DOCX import: the lazy ZIP decoder must load from precache.
        self.assertEqual(page.evaluate("typeof window.fflate"), "undefined")
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as docx:
            docx.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>首次离线 Word 导入成功</w:t></w:r></w:p></w:body></w:document>')
        page.locator("#importFile").set_input_files({
            "name": "offline.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "buffer": package.getvalue(),
        })
        expect(page.locator("#inputText")).to_have_value("首次离线 Word 导入成功")
        self.assertEqual(page.evaluate("typeof window.fflate.unzipSync"), "function")
        page.locator("#importFile").set_input_files({
            "name": "offline.txt", "mimeType": "text/plain", "buffer": "离线 TXT 也可导入".encode(),
        })
        expect(page.locator("#inputText")).to_have_value("离线 TXT 也可导入")
        page.locator("#openSettingsBtn").click()
        page.locator("#countdownSetting").select_option("0")
        page.locator("#doneSettingsBtn").click()
        page.locator("#startBtn").click()
        expect(page.locator("#display")).to_have_attribute("data-state", "playing")

    def test_offline_root_and_first_docx(self):
        self.assert_offline_bootstrap("/")

    def test_offline_subdirectory_and_first_docx(self):
        self.assert_offline_bootstrap("/teleprompter/")

    def test_manifest_and_declared_icon_dimensions(self):
        self.open_ready("/teleprompter/")
        manifest = self.page.evaluate("fetch(document.getElementById('appManifest').href).then(r => r.json())")
        for field in ("scope", "start_url", "id"):
            self.assertEqual(manifest[field], "./")
        self.assertEqual(manifest["display"], "standalone")
        for icon in manifest["icons"]:
            raw = (ROOT / icon["src"]).read_bytes()
            self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", raw[16:24])
            self.assertEqual(icon["sizes"], f"{width}x{height}")
            self.assertEqual(width, height)
        diagnostics = self.context.new_cdp_session(self.page)
        self.assertEqual(diagnostics.send("Page.getInstallabilityErrors")["installabilityErrors"], [])

    def test_unrelated_requests_are_not_cached_or_intercepted(self):
        self.open_ready("/teleprompter/")
        for path in ("/other-application", "/teleprompter/not-an-asset"):
            response = self.page.evaluate("url => fetch(url).then(r => r.text())", self.server.url + path)
            self.assertEqual(response, "Uncached server response")
        self.assertEqual(self.page.evaluate("fetch('app.js', {method: 'POST'}).then(r => r.text())"),
                         "Uncached POST response")
        entries = self.page.evaluate("""async () => {
            const result = [];
            for (const name of await caches.keys()) {
                result.push(...(await (await caches.open(name)).keys()).map(r => r.url));
            }
            return result;
        }""")
        self.assertEqual(set(entries), {self.server.url + "/teleprompter/" + file for file in SHELL})
        self.context.set_offline(True)
        self.assertTrue(self.page.evaluate("fetch('/other-application').then(() => false, () => true)"))
        self.assertTrue(self.page.evaluate("fetch('/teleprompter/not-an-asset').then(() => false, () => true)"))

    def test_waiting_update_preserves_two_pages_and_owned_caches(self):
        reader_text = "继续提词，不被更新打断。\n" * 60
        editor_text = "编辑中仍然保留的文字"
        reader = self.open_ready()
        reader.locator("#draftTitle").fill("更新测试提词稿")
        reader.locator("#inputText").fill(reader_text)
        expect(reader.locator("#saveLabel")).to_have_text("已自动保存")
        reader.locator("#openSettingsBtn").click()
        reader.locator("#countdownSetting").select_option("0")
        reader.locator("#doneSettingsBtn").click()
        reader.locator("#startBtn").click()
        expect(reader.locator("#display")).to_have_attribute("data-state", "playing")
        editor = self.open_ready(page=self.new_page())
        editor.locator("#openLibraryBtn").click()
        editor.locator("#newDraftBtn").click()
        editor.locator("#draftTitle").fill("更新测试编辑稿")
        editor.locator("#inputText").fill(editor_text)
        expect(editor.locator("#saveLabel")).to_have_text("已自动保存")
        editor.locator("#inputText").focus()
        for page in (reader, editor):
            page.evaluate("""() => {
                window.originalController = navigator.serviceWorker.controller;
                window.controllerChanges = 0;
                navigator.serviceWorker.addEventListener('controllerchange', () => window.controllerChanges++);
            }""")
        initial_cache = next(name for name in self.cache_names() if name.endswith("test-release-1"))
        foreign_scope = "flow-teleprompter::" + self.page.evaluate("encodeURIComponent(location.origin + '/another/')") + "::test-release-1"
        preserved = ["unrelated-app-cache", foreign_scope, "teleprompter-app"]
        self.page.evaluate("names => Promise.all(names.map(name => caches.open(name)))", preserved)
        self.server.releases["/"] = 2
        reader.evaluate("navigator.serviceWorker.getRegistration().then(r => r.update())")
        reader.wait_for_function("navigator.serviceWorker.getRegistration().then(r => !!r.waiting)")
        expect(reader.locator("#updateStatus")).to_contain_text("关闭所有提词器窗口")
        for page in (reader, editor):
            self.assertTrue(page.evaluate("originalController === navigator.serviceWorker.controller && controllerChanges === 0"))
            self.assertEqual(page.locator('meta[name="test-release"]').get_attribute("content"), "1")
        expect(reader.locator("#display")).to_have_attribute("data-state", "playing")
        expect(reader.locator("#text")).to_have_text(reader_text)
        expect(reader.locator("#inputText")).to_have_value(reader_text)
        expect(editor.locator("#inputText")).to_have_value(editor_text)
        expect(editor.locator("#inputText")).to_be_focused()
        editor.locator("#openSettingsBtn").click()
        expect(editor.locator("#updateStatus")).to_be_visible()
        expect(editor.locator("#updateStatus")).to_contain_text("关闭所有提词器窗口")
        editor.locator("#doneSettingsBtn").click()
        self.assertIn(initial_cache, self.cache_names())
        reader.close()
        self.assertTrue(editor.evaluate("navigator.serviceWorker.getRegistration().then(r => !!r.waiting)"))
        self.assertEqual(editor.evaluate("controllerChanges"), 0)
        waiting_worker = next(worker for worker in self.context.service_workers
                              if worker.evaluate("RELEASE === 'test-release-2'"))
        editor.close()
        # Observe activation without opening another controlled page too early.
        self.assertTrue(waiting_worker.evaluate("""() => new Promise(resolve => {
            const deadline = Date.now() + 10000;
            const timer = setInterval(() => {
                if (self.registration.active?.state === 'activated' && !self.registration.waiting) {
                    clearInterval(timer);
                    resolve(true);
                } else if (Date.now() > deadline) {
                    clearInterval(timer);
                    resolve(false);
                }
            }, 25);
        })"""))
        self.page = self.new_page()
        self.open_ready()
        self.page.wait_for_function("navigator.serviceWorker.getRegistration().then(r => r.active?.state === 'activated' && !r.waiting)")
        self.page.reload()
        self.assertEqual(self.page.locator('meta[name="test-release"]').get_attribute("content"), "2")
        names = self.cache_names()
        self.assertNotIn(initial_cache, names)
        for name in preserved:
            self.assertIn(name, names)
        expect(self.page.locator("#draftTitle")).to_have_value("更新测试编辑稿")
        expect(self.page.locator("#inputText")).to_have_value(editor_text)
        self.page.locator("#openLibraryBtn").click()
        expect(self.page.locator(".draft-open")).to_have_count(2)
        self.page.get_by_role("button", name="打开文稿：更新测试提词稿", exact=True).click()
        expect(self.page.locator("#inputText")).to_have_value(reader_text)
        self.page.locator("#openLibraryBtn").click()
        self.page.get_by_role("button", name="打开文稿：更新测试编辑稿", exact=True).click()
        expect(self.page.locator("#inputText")).to_have_value(editor_text)

    def test_failed_update_keeps_previous_offline_shell(self):
        self.open_ready()
        self.server.releases["/"] = 2
        self.server.failures.add("/vendor/fflate-0.8.3.min.js")
        self.page.evaluate("""async () => {
            const registration = await navigator.serviceWorker.getRegistration();
            window.failedInstall = new Promise(resolve => {
                registration.addEventListener('updatefound', () => {
                    const worker = registration.installing;
                    worker.addEventListener('statechange', () => {
                        if (worker.state === 'redundant') resolve(true);
                    });
                }, {once: true});
            });
            await registration.update();
        }""")
        self.assertTrue(self.page.evaluate("window.failedInstall"))
        self.assertFalse(self.page.evaluate("navigator.serviceWorker.getRegistration().then(r => !!r.waiting)"))
        self.context.set_offline(True)
        self.page.reload()
        expect(self.page.locator("#offlineStatus")).to_have_attribute("data-state", "offline")
        self.assertEqual(self.page.locator('meta[name="test-release"]').get_attribute("content"), "1")

    def test_failed_first_install_and_cache_eviction_are_not_ready(self):
        self.server.failures.add("/vendor/fflate-0.8.3.min.js")
        self.page.goto(self.server.url)
        expect(self.page.locator("#offlineStatus")).to_have_attribute("data-state", "unavailable")
        self.assertFalse(self.page.evaluate("!!navigator.serviceWorker.controller"))
        self.server.failures.clear()
        self.page.reload()
        expect(self.page.locator("#offlineStatus")).to_have_attribute("data-state", "ready")
        self.page.evaluate("caches.keys().then(names => Promise.all(names.map(name => caches.delete(name))))")
        self.context.set_offline(True)
        expect(self.page.locator("#offlineStatus")).to_have_attribute("data-state", "unavailable")

    def test_install_prompt_requires_click_and_is_consumed(self):
        self.open_ready()
        self.page.locator("#openSettingsBtn").click()
        for outcome in ("dismissed", "accepted", "rejected"):
            self.page.evaluate("""outcome => {
                const event = new Event('beforeinstallprompt', {cancelable: true});
                window.promptCalls = 0;
                event.prompt = () => {
                    window.promptCalls++;
                    return outcome === 'rejected' ? Promise.reject(new Error('unavailable')) : Promise.resolve();
                };
                event.userChoice = Promise.resolve({outcome});
                window.dispatchEvent(event);
                window.promptDefaultPrevented = event.defaultPrevented;
            }""", outcome)
            self.assertTrue(self.page.evaluate("promptDefaultPrevented"))
            self.assertEqual(self.page.evaluate("promptCalls"), 0)
            expect(self.page.locator("#installAppBtn")).to_be_visible()
            self.page.locator("#installAppBtn").click()
            self.assertEqual(self.page.evaluate("promptCalls"), 1)
            expect(self.page.locator("#installAppBtn")).to_be_hidden()
        self.page.evaluate("window.dispatchEvent(new Event('appinstalled'))")
        expect(self.page.locator("#installHint")).to_contain_text("已安装")
        expect(self.page.locator("#installAppBtn")).to_be_hidden()

    def test_ios_help_unsupported_browser_and_file_mode(self):
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'});
            Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});
        """)
        self.open_ready()
        expect(self.page.locator("#installHint")).to_contain_text("共享")
        expect(self.page.locator("#installAppBtn")).to_be_hidden()
        self.context.add_init_script("delete Navigator.prototype.serviceWorker")
        self.page.reload()
        expect(self.page.locator("#offlineStatus")).to_have_attribute("data-state", "unsupported")
        requests = []
        self.page.on("request", lambda request: requests.append(request.url))
        self.page.goto((ROOT / "index.html").as_uri())
        expect(self.page.locator("body")).to_have_attribute("data-library-ready", "true")
        expect(self.page.locator("#offlineStatus")).to_have_attribute("data-state", "unsupported")
        self.page.locator("#inputText").fill("本地文件仍可编辑")
        self.assertFalse(any("manifest.json" in url or "worker.js" in url for url in requests))
        self.assertIsNone(self.page.locator("#appManifest").get_attribute("href"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
