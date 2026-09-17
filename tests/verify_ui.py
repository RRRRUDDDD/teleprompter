"""Browser regressions for the local, mobile-first teleprompter.

Start a static server, then run ``py -3.11 tests/verify_ui.py``.
TELEPROMPTER_TEST_URL and TELEPROMPTER_TEST_BROWSER override the URL/browser.
DOCX fixtures are generated in memory; no Office SDK or document download is used.
"""

import io
import json
import math
import os
import re
import time
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path
from xml.sax.saxutils import escape

from playwright.sync_api import expect, sync_playwright


BASE_URL = os.environ.get("TELEPROMPTER_TEST_URL", "http://127.0.0.1:4175")
BROWSER = os.environ.get("TELEPROMPTER_TEST_BROWSER", "chromium")
SETTINGS_KEY = "flow.teleprompter.settings.v1"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
STRICT_NS = "http://purl.oclc.org/ooxml/wordprocessingml/main"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
LONG_DRAFT = "\n".join(f"第 {n} 段：让文字跟上自己的节奏。 Keep a steady reading pace." for n in range(1, 61))
NO_FULLSCREEN = """
Element.prototype.requestFullscreen = undefined;
Element.prototype.webkitRequestFullscreen = undefined;
"""
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def word_document(body, namespace=WORD_NS):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{namespace}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<w:body>{body}<w:sectPr/></w:body></w:document>"
    )


def paragraph(text):
    return f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def make_docx(document=None, namespace=WORD_NS, extra_entries=None):
    """A small, valid Word package, including an external link that must not load."""
    if document is None:
        body = paragraph("你好，Flow 👋")
        body += (
            "<w:p><w:r><w:t>Latin text &amp; 中文</w:t><w:br/>"
            "<w:t>下一行</w:t><w:tab/><w:t>制表位</w:t></w:r></w:p>"
            "<w:tbl><w:tr><w:tc>" + paragraph("单元格 A") + "</w:tc><w:tc>"
            + paragraph("Cell B") + "</w:tc></w:tr></w:tbl>"
            '<w:p><w:hyperlink r:id="rIdLink"><w:r><w:t>链接文字</w:t>'
            "</w:r></w:hyperlink></w:p>"
        )
        body += paragraph('<script>window.docxExecuted = true</script>')
        body += paragraph('<img src="https://docx-import.invalid/image" onerror="window.docxExecuted=true">')
        document = word_document(body, namespace)
    entries = {
        "[Content_Types].xml": (
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>'
        ),
        "word/document.xml": document,
        "word/_rels/document.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdLink" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            'Target="https://docx-import.invalid/should-not-load" TargetMode="External"/>'
            "</Relationships>"
        ),
    }
    entries.update(extra_entries or {})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, data in entries.items():
            package.writestr(name, data)
    return stream.getvalue()


class TeleprompterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = getattr(cls.playwright, BROWSER).launch(headless=True)
        cls.browser_logs = []

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.errors = []
        self.requests = []
        self.console_messages = []
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
        self.context.add_init_script(NO_FULLSCREEN)
        self.page = self.context.new_page()
        self.page.set_default_timeout(8000)
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("request", lambda request: self.requests.append(request.url))
        self.page.on("console", lambda message: self.console_messages.append(message.text) if message.type == "error" else None)
        self.page.goto(BASE_URL, wait_until="networkidle")
        self.wait_ready()

    def tearDown(self):
        self.context.close()
        self.browser_logs.append({"test": self.id(), "page_errors": self.errors, "console_errors": self.console_messages})
        self.assertEqual(self.errors, [], "Uncaught browser errors")

    def open_settings(self, page=None):
        page = page or self.page
        page.locator("#openSettingsBtn").click()
        expect(page.locator("#settingsDialog")).to_be_visible()

    def wait_ready(self, page=None):
        expect((page or self.page).locator("body")).to_have_attribute("data-library-ready", "true")

    def wait_saved(self, draft=None, page=None):
        page = page or self.page
        if draft is None:
            draft = page.locator("#inputText").input_value()
        page.wait_for_function("text => localStorage.getItem('savedText') === text", arg=draft)
        expect(page.locator("#saveLabel")).to_have_text("已自动保存")

    def reload_page(self, page=None):
        page = page or self.page
        self.wait_saved(page=page)
        page.reload(wait_until="networkidle")
        self.wait_ready(page)

    def open_library(self, page=None):
        page = page or self.page
        page.locator("#openLibraryBtn").click()
        expect(page.locator("#libraryDialog")).to_be_visible()

    def draft_item(self, title, page=None):
        page = page or self.page
        return page.locator(".draft-item").filter(has=page.get_by_text(title, exact=True))

    def create_draft(self, title, text, page=None):
        page = page or self.page
        self.open_library(page)
        page.locator("#newDraftBtn").click()
        expect(page.locator("#libraryDialog")).to_be_hidden()
        expect(page.locator("#inputText")).to_have_value("")
        page.locator("#draftTitle").fill(title)
        page.locator("#inputText").fill(text)

    def select_draft(self, title, page=None):
        page = page or self.page
        self.open_library(page)
        self.draft_item(title, page).locator(".draft-open").click()
        expect(page.locator("#libraryDialog")).to_be_hidden()
        expect(page.locator("#draftTitle")).to_have_value(title)

    def change_reader_font(self, target, page=None):
        page = page or self.page
        current = int(page.locator("#playerFontSizeValue").inner_text())
        self.assertEqual(abs(target - current) % 2, 0)
        button = "#largerFontBtn" if target > current else "#smallerFontBtn"
        for _ in range(abs(target - current) // 2):
            page.locator(button).click()
        expect(page.locator("#playerFontSizeValue")).to_have_text(str(target))

    def configure(self, page=None, **values):
        page = page or self.page
        self.open_settings(page)
        for name, value in values.items():
            control = page.locator(f"#{name}")
            if isinstance(value, bool):
                control.set_checked(value)
            elif control.evaluate("el => el.tagName") == "SELECT":
                control.select_option(str(value))
            else:
                control.fill(str(value))
                control.press("Tab")
        page.locator("#doneSettingsBtn").click()
        expect(page.locator("#settingsDialog")).to_be_hidden()

    def start_reader(self, page=None, draft=LONG_DRAFT, **settings):
        page = page or self.page
        page.locator("#inputText").fill(draft)
        self.configure(page, countdownSetting=0, **settings)
        page.locator("#startBtn").click()
        expect(page.locator("#display")).to_have_attribute("data-state", "playing")

    def upload(self, name, data, mime="", page=None):
        (page or self.page).locator("#importFile").set_input_files(
            {"name": name, "mimeType": mime, "buffer": data}
        )

    def set_range(self, selector, value, page=None):
        (page or self.page).locator(selector).evaluate(
            "(el, value) => { el.value = String(value); el.dispatchEvent(new Event('input', {bubbles: true})); }",
            value,
        )

    def tap_reader(self, page=None):
        page = page or self.page
        bounds = page.locator("#readerViewport").bounding_box()
        page.locator("#readerViewport").click(
            position={"x": bounds["width"] * 0.45, "y": bounds["height"] * 0.3}
        )

    def reader_metrics(self, page=None):
        return (page or self.page).evaluate("""() => {
            const text = document.getElementById('text');
            const viewport = document.getElementById('display');
            const y = new DOMMatrix(getComputedStyle(text).transform).m42;
            return {
                y,
                height: text.offsetHeight,
                viewportHeight: viewport.clientHeight,
                fraction: (viewport.clientHeight / 2 - y) / text.offsetHeight,
                remaining: y + text.offsetHeight - viewport.clientHeight / 2,
                progress: Number(document.getElementById('readingProgress').getAttribute('aria-valuenow')),
                timer: document.getElementById('timer').textContent,
            };
        }""")

    def settle_layout(self, page=None):
        (page or self.page).evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

    def resize_mock_visual_viewport(self, page, height, offset_top=0):
        page.evaluate("""({height, offsetTop}) => {
            Object.assign(window.testViewport, {height, offsetTop});
            window.testViewport.dispatchEvent(new Event('resize'));
        }""", {"height": height, "offsetTop": offset_top})
        self.settle_layout(page)

    def activate_at_current_position(self, page, selector, interaction):
        """Use the original hit point so a blur-triggered layout jump cannot be retried away."""
        expect(page.locator(selector)).to_be_visible()
        bounds = page.locator(selector).bounding_box()
        x = bounds["x"] + bounds["width"] / 2
        y = bounds["y"] + bounds["height"] / 2
        if interaction == "touch":
            page.touchscreen.tap(x, y)
        else:
            page.mouse.move(x, y)
            page.mouse.down()
            # A normal press spans animation frames, including the queued numeric-input blur.
            self.settle_layout(page)
            page.mouse.up()

    @contextmanager
    def phone(self, width=390, height=844, init_script=NO_FULLSCREEN):
        with self.browser.new_context(viewport={"width": width, "height": height}, is_mobile=True, has_touch=True, service_workers="block") as context:
            if init_script:
                context.add_init_script(init_script)
            page = context.new_page()
            page.set_default_timeout(8000)
            page.on("pageerror", lambda error: self.errors.append(str(error)))
            page.on("console", lambda message: self.console_messages.append(message.text) if message.type == "error" else None)
            page.goto(BASE_URL, wait_until="networkidle")
            self.wait_ready(page)
            yield page

    def assert_fits_viewport(self, selector, page=None, minimum_target=False):
        page = page or self.page
        control = page.locator(selector)
        expect(control).to_be_visible()
        bounds = control.bounding_box()
        viewport = page.viewport_size
        self.assertGreaterEqual(bounds["x"], -1, selector)
        self.assertGreaterEqual(bounds["y"], -1, selector)
        self.assertLessEqual(bounds["x"] + bounds["width"], viewport["width"] + 1, selector)
        self.assertLessEqual(bounds["y"] + bounds["height"], viewport["height"] + 1, selector)
        if minimum_target:
            self.assertGreaterEqual(bounds["width"], 44, selector)
            self.assertGreaterEqual(bounds["height"], 44, selector)

    def assert_rejected_import(self, name, data, mime=""):
        draft = "请保留这一份正在编辑的文稿。"
        self.page.locator("#inputText").fill(draft)
        self.upload(name, data, mime)
        expect(self.page.locator("#toastMessage")).to_have_text(re.compile(r"[\u4e00-\u9fff]"))
        expect(self.page.locator("#importFile")).to_have_value("")
        expect(self.page.locator("#inputText")).to_have_value(draft)
        self.wait_saved(draft)

    def test_editor_persistence_and_plain_text_rendering(self):
        draft = "你好，镜头。\nKeep your own pace.\n<script>window.injected = true</script>"
        self.page.locator("#inputText").fill(draft)
        expect(self.page.locator("#wordCount")).to_have_text(str(len(re.sub(r"\s", "", draft))))
        self.reload_page()
        expect(self.page.locator("#inputText")).to_have_value(draft)
        self.start_reader(draft=draft)
        expect(self.page.locator("#text")).to_have_text(draft)
        expect(self.page.locator("#text script")).to_have_count(0)
        self.assertIsNone(self.page.evaluate("window.injected"))

    def test_clear_undo_and_saved_empty_draft(self):
        draft = "这段文字应当可以恢复。"
        self.page.locator("#inputText").fill(draft)
        self.page.locator("#clearBtn").click()
        expect(self.page.locator("#inputText")).to_have_value("")
        expect(self.page.locator("#startBtn")).to_be_disabled()
        self.page.locator("#toastAction").click()
        expect(self.page.locator("#inputText")).to_have_value(draft)
        self.page.locator("#clearBtn").click()
        self.reload_page()
        expect(self.page.locator("#inputText")).to_have_value("")
        expect(self.page.locator("#startBtn")).to_be_disabled()

    def test_editor_keyboard_does_not_start_playback(self):
        editor = self.page.locator("#inputText")
        editor.fill("Hello")
        editor.press("End")
        editor.press("Space")
        self.page.keyboard.insert_text("world")
        editor.press("ArrowLeft")
        editor.press("Escape")
        expect(editor).to_have_value("Hello world")
        expect(self.page.locator("#display")).to_be_hidden()

    def test_single_editor_and_dialog_contract(self):
        expect(self.page.locator("#inputText")).to_be_visible()
        expect(self.page.locator("#inputText")).to_have_value("")
        expect(self.page.locator("#startBtn")).to_be_disabled()
        expect(self.page.locator("#sampleBtn, #startHint, #importLabel")).to_have_count(0)
        expect(self.page.locator("#settingsDialog")).to_be_hidden()
        expect(self.page.locator("#previewText, .mobile-tabs, [role=tablist], #pauseBtn")).to_have_count(0)
        for selector in ["#importBtn", "#openSettingsBtn"]:
            button = self.page.locator(selector)
            expect(button).to_have_text("")
            expect(button.locator("svg")).to_have_count(1)
            self.assertTrue(button.get_attribute("aria-label"))
            self.assertTrue(button.get_attribute("title"))
            self.assert_fits_viewport(selector, minimum_target=True)
        self.open_settings()
        self.assertTrue(self.page.locator("#settingsDialog").evaluate("el => el.matches(':modal')"))
        for name in ["fontFamily", "fontSize", "fontSizeRange", "fontColor", "bgColor", "speed", "speedRange", "countdownSetting", "mirror", "showTimer", "refLineColor", "refLineWidth"]:
            expect(self.page.locator(f"#settingsDialog #{name}")).to_have_count(1)

    def test_library_create_rename_search_switch_and_refresh(self):
        title = '开场 <img src=x onerror="window.titleExecuted=true">'
        self.page.locator("#draftTitle").fill(title)
        self.page.locator("#inputText").fill("第一篇原稿。")
        self.create_draft("第二篇访谈", "第二篇保留内容。")
        self.open_library()
        expect(self.page.locator(".draft-item")).to_have_count(2)
        expect(self.page.locator("#draftCount")).to_have_text("2")
        expect(self.page.locator("#draftList img, #draftList script")).to_have_count(0)
        self.assertIsNone(self.page.evaluate("window.titleExecuted"))
        first_id = self.draft_item(title).get_attribute("data-draft-id")
        self.page.locator("#librarySearch").fill("访谈")
        expect(self.page.locator(".draft-item:visible")).to_have_count(1)
        expect(self.draft_item("第二篇访谈")).to_be_visible()
        self.page.locator("#librarySearch").fill("第一篇原稿")
        expect(self.page.locator(".draft-item:visible")).to_have_count(1)
        expect(self.draft_item(title)).to_be_visible()
        expect(self.page.locator("#draftCount")).to_have_text("2")
        self.page.locator("#librarySearch").fill("不会匹配任何文稿")
        expect(self.page.locator(".draft-item:visible")).to_have_count(0)
        expect(self.page.locator("#libraryEmpty")).to_be_visible()
        self.page.locator("#librarySearch").fill("")
        self.draft_item(title).locator(".draft-open").click()
        expect(self.page.locator("#libraryDialog")).to_be_hidden()
        expect(self.page.locator("#inputText")).to_have_value("第一篇原稿。")
        self.page.locator("#draftTitle").fill("开场修订")
        self.page.locator("#inputText").fill("第一篇新内容，切换时必须保存。")
        self.select_draft("第二篇访谈")
        expect(self.page.locator("#inputText")).to_have_value("第二篇保留内容。")
        self.reload_page()
        expect(self.page.locator("#draftTitle")).to_have_value("第二篇访谈")
        expect(self.page.locator("#inputText")).to_have_value("第二篇保留内容。")
        self.select_draft("开场修订")
        expect(self.page.locator("#inputText")).to_have_value("第一篇新内容，切换时必须保存。")
        self.open_library()
        expect(self.draft_item("开场修订")).to_have_attribute("data-draft-id", first_id)
        expect(self.page.locator(".draft-item")).to_have_count(2)

    def test_library_delete_undo_preserves_current_edits(self):
        self.page.locator("#draftTitle").fill("保留稿")
        self.page.locator("#inputText").fill("保留稿原文。")
        self.create_draft("待删除稿", "删除后撤销应恢复的原文。")
        self.open_library()
        deleted_id = self.draft_item("待删除稿").get_attribute("data-draft-id")
        self.draft_item("待删除稿").locator(".draft-delete").click()
        expect(self.page.locator(f'.draft-item[data-draft-id="{deleted_id}"]')).to_have_count(0)
        expect(self.page.locator("#libraryFeedbackMessage")).to_have_attribute("role", "status")
        expect(self.page.locator("#undoDeleteBtn")).to_be_visible()
        self.page.locator("#closeLibraryBtn").click()
        expect(self.page.locator("#draftTitle")).to_have_value("保留稿")
        self.page.locator("#inputText").fill("删除另一篇后刚写的新内容。")
        self.open_library()
        self.page.locator("#undoDeleteBtn").click()
        expect(self.draft_item("待删除稿")).to_be_visible()
        self.page.locator("#closeLibraryBtn").click()
        expect(self.page.locator("#draftTitle")).to_have_value("保留稿")
        expect(self.page.locator("#inputText")).to_have_value("删除另一篇后刚写的新内容。")
        self.select_draft("待删除稿")
        expect(self.page.locator("#inputText")).to_have_value("删除后撤销应恢复的原文。")
        self.reload_page()
        self.open_library()
        expect(self.draft_item("待删除稿")).to_have_attribute("data-draft-id", deleted_id)
        expect(self.page.locator(".draft-item")).to_have_count(2)

    def test_library_delete_last_draft_keeps_blank_editor_and_can_undo(self):
        self.page.locator("#draftTitle").fill("唯一文稿")
        self.page.locator("#inputText").fill("唯一文稿原文。")
        self.open_library()
        self.draft_item("唯一文稿").locator(".draft-delete").click()
        expect(self.draft_item("唯一文稿")).to_have_count(0)
        self.page.locator("#closeLibraryBtn").click()
        expect(self.page.locator("#inputText")).to_have_value("")
        expect(self.page.locator("#startBtn")).to_be_disabled()
        self.page.locator("#inputText").fill("删除最后一篇后开始的新稿。")
        self.open_library()
        self.page.locator("#undoDeleteBtn").click()
        expect(self.draft_item("唯一文稿")).to_be_visible()
        self.page.locator("#closeLibraryBtn").click()
        expect(self.page.locator("#inputText")).to_have_value("删除最后一篇后开始的新稿。")
        self.select_draft("唯一文稿")
        expect(self.page.locator("#inputText")).to_have_value("唯一文稿原文。")

    def test_library_pending_import_cannot_modify_another_draft(self):
        self.page.locator("#draftTitle").fill("导入目标")
        self.page.locator("#inputText").fill("导入目标原文。")
        self.create_draft("正在编辑", "第二篇原文。")
        self.select_draft("导入目标")
        self.page.evaluate("""() => {
            window.FlowDocumentImport = {
                read: () => new Promise(resolve => { window.resolvePendingImport = resolve; })
            };
        }""")
        self.upload("pending.txt", b"pending", "text/plain")
        self.page.wait_for_function("typeof window.resolvePendingImport === 'function'")
        expect(self.page.locator("#importBtn")).to_have_attribute("aria-busy", "true")
        self.select_draft("正在编辑")
        self.page.locator("#inputText").fill("切稿后新增的内容。")
        self.page.evaluate("window.resolvePendingImport('迟到的导入结果。')")
        expect(self.page.locator("#importBtn")).to_have_attribute("aria-busy", "false")
        expect(self.page.locator("#inputText")).to_have_value("切稿后新增的内容。")
        self.reload_page()
        expect(self.page.locator("#inputText")).to_have_value("切稿后新增的内容。")
        self.select_draft("导入目标")
        expect(self.page.locator("#inputText")).to_have_value("导入目标原文。")

    def test_library_old_undo_cannot_replace_a_different_draft(self):
        self.page.locator("#draftTitle").fill("第一篇")
        self.page.locator("#inputText").fill("第一篇正文。")
        self.create_draft("第二篇", "第二篇正文。")
        self.select_draft("第一篇")
        self.page.locator("#clearBtn").click()
        self.select_draft("第二篇")
        if self.page.locator("#toastAction").is_visible():
            self.page.locator("#toastAction").click()
        expect(self.page.locator("#inputText")).to_have_value("第二篇正文。")
        self.reload_page()
        expect(self.page.locator("#inputText")).to_have_value("第二篇正文。")

    def test_library_migrates_legacy_text_once_and_prefers_indexeddb(self):
        init_script = NO_FULLSCREEN + """
            if (!sessionStorage.getItem('legacy-test-seeded')) {
                localStorage.setItem('savedText', '升级之前已经保存的稿子。');
                sessionStorage.setItem('legacy-test-seeded', 'true');
            }
        """
        with self.phone(init_script=init_script) as phone:
            expect(phone.locator("#inputText")).to_have_value("升级之前已经保存的稿子。")
            phone.locator("#draftTitle").fill("已迁移的稿子")
            phone.locator("#inputText").fill("迁移之后的新正文。")
            self.wait_saved("迁移之后的新正文。", phone)
            phone.evaluate("localStorage.setItem('savedText', '过时的兼容镜像。')")
            phone.reload(wait_until="networkidle")
            self.wait_ready(phone)
            expect(phone.locator("#draftTitle")).to_have_value("已迁移的稿子")
            expect(phone.locator("#inputText")).to_have_value("迁移之后的新正文。")
            self.open_library(phone)
            expect(phone.locator(".draft-item")).to_have_count(1)

    def test_library_storage_failure_keeps_session_usable_and_unsaved(self):
        init_script = NO_FULLSCREEN + """
            localStorage.setItem('savedText', '存储不可用时仍保留旧正文。');
            Object.defineProperty(window, 'indexedDB', {value: {
                open() { throw new DOMException('blocked', 'SecurityError'); }
            }});
        """
        with self.phone(init_script=init_script) as phone:
            expect(phone.locator("#inputText")).to_have_value("存储不可用时仍保留旧正文。")
            phone.locator("#inputText").fill("会话中仍然可以编辑和提词。")
            expect(phone.locator("#saveLabel")).to_have_text(re.compile("未.*保存"))
            self.configure(phone, speed=65, countdownSetting=0)
            expect(phone.locator("#saveLabel")).to_have_text(re.compile("未.*保存"))
            phone.locator("#startBtn").click()
            expect(phone.locator("#display")).to_have_attribute("data-state", "playing")
            phone.locator("#exitBtn").click()
            expect(phone.locator("#inputText")).to_have_value("会话中仍然可以编辑和提词。")
            expect(phone.locator("#saveLabel")).to_have_text(re.compile("未.*保存"))

    def test_mobile_library_dialog_title_limit_and_focus(self):
        with self.phone(width=320, height=568) as phone:
            phone.locator("#draftTitle").fill("稿" * 130)
            expect(phone.locator("#draftTitle")).to_have_attribute("maxlength", "120")
            self.assertLessEqual(len(phone.locator("#draftTitle").input_value()), 120)
            phone.locator("#draftTitle").blur()
            self.open_library(phone)
            self.assertTrue(phone.locator("#libraryDialog").evaluate("el => el.matches(':modal')"))
            for selector in ["#libraryDialog", "#newDraftBtn", "#closeLibraryBtn", "#librarySearch"]:
                self.assert_fits_viewport(selector, phone)
            phone.locator("#inputText").evaluate("el => el.focus()")
            self.assertTrue(phone.locator("#libraryDialog").evaluate("el => el.contains(document.activeElement)"))
            phone.keyboard.press("Escape")
            expect(phone.locator("#libraryDialog")).to_be_hidden()
            expect(phone.locator("#openLibraryBtn")).to_be_focused()

    def test_library_create_and_select_focus_editor_fields(self):
        self.page.locator("#draftTitle").fill("已有文稿")
        self.page.locator("#inputText").fill("已有正文。")
        self.open_library()
        self.page.locator("#newDraftBtn").click()
        expect(self.page.locator("#libraryDialog")).to_be_hidden()
        self.settle_layout()
        expect(self.page.locator("#draftTitle")).to_be_focused()
        self.page.keyboard.insert_text("新建文稿")
        expect(self.page.locator("#draftTitle")).to_have_value("新建文稿")
        self.select_draft("已有文稿")
        self.settle_layout()
        expect(self.page.locator("#inputText")).to_be_focused()
        expect(self.page.locator("#inputText")).to_have_value("已有正文。")

    def test_library_actions_stay_accessible_with_landscape_search_keyboard(self):
        width, height, visible_height, offset_top = 844, 390, 230, 20
        init_script = NO_FULLSCREEN + f"""
            window.testViewport = new EventTarget();
            Object.assign(window.testViewport, {{height: {height}, width: {width}, offsetTop: 0, offsetLeft: 0, scale: 1}});
            Object.defineProperty(window, 'visualViewport', {{value: window.testViewport}});
        """
        for button in ["#closeLibraryBtn", "#newDraftBtn", "#undoDeleteBtn"]:
            for interaction in ["mouse", "touch"]:
                with self.subTest(button=button, interaction=interaction), self.phone(width, height, init_script) as phone:
                    phone.locator("#draftTitle").fill("保留文稿")
                    phone.locator("#inputText").fill("仍在书库里的内容。")
                    self.create_draft("待恢复文稿", "删除后可以撤销的内容。", phone)
                    self.open_library(phone)
                    self.draft_item("待恢复文稿", phone).locator(".draft-delete").click()
                    expect(self.draft_item("待恢复文稿", phone)).to_have_count(0)
                    expect(phone.locator("#undoDeleteBtn")).to_be_visible()
                    phone.locator("#librarySearch").focus()
                    self.resize_mock_visual_viewport(phone, visible_height, offset_top)
                    phone.wait_for_function("document.body.classList.contains('keyboard-open')")
                    expect(phone.locator("#librarySearch")).to_be_focused()
                    for selector in ["#libraryDialog", "#librarySearch", "#closeLibraryBtn", "#newDraftBtn", "#undoDeleteBtn"]:
                        expect(phone.locator(selector)).to_be_visible()
                        bounds = phone.locator(selector).bounding_box()
                        self.assertGreaterEqual(bounds["y"], offset_top - 1, selector)
                        self.assertLessEqual(bounds["y"] + bounds["height"], offset_top + visible_height + 1, selector)
                        self.assertGreaterEqual(bounds["x"], -1, selector)
                        self.assertLessEqual(bounds["x"] + bounds["width"], width + 1, selector)
                        if selector.endswith("Btn"):
                            self.assertGreaterEqual(bounds["width"], 44, selector)
                            self.assertGreaterEqual(bounds["height"], 44, selector)
                    # Use the pre-blur hit point while the visual viewport stays shortened.
                    self.activate_at_current_position(phone, button, interaction)
                    if button == "#undoDeleteBtn":
                        expect(self.draft_item("待恢复文稿", phone)).to_have_count(1)
                        expect(phone.locator("#libraryDialog")).to_be_visible()
                        expect(phone.locator("#undoDeleteBtn")).to_be_hidden()
                    else:
                        expect(phone.locator("#libraryDialog")).to_be_hidden()
                        self.settle_layout(phone)
                        destination = "#draftTitle" if button == "#newDraftBtn" else "#openLibraryBtn"
                        expect(phone.locator(destination)).to_be_focused()
                    self.assertEqual(phone.evaluate("visualViewport.height"), visible_height)
                    self.assertEqual(phone.evaluate("visualViewport.offsetTop"), offset_top)

    def test_text_import_and_undo(self):
        self.page.locator("#inputText").fill("导入前的文稿。")
        self.upload("访谈稿.TXT", "\ufeff第一问。\nSecond question 👋".encode("utf-8"), "text/plain")
        expect(self.page.locator("#inputText")).to_have_value("第一问。\nSecond question 👋")
        self.page.locator("#toastAction").click()
        expect(self.page.locator("#inputText")).to_have_value("导入前的文稿。")

    def test_txt_does_not_load_zip_library(self):
        self.upload("纯文字.txt", "直接导入，无需解压库。".encode("utf-8"), "")
        expect(self.page.locator("#inputText")).to_have_value("直接导入，无需解压库。")
        self.assertFalse(any("fflate" in url for url in self.requests), self.requests)

    def test_docx_paragraph_break_tab_table_and_literal_html(self):
        self.upload("讲稿.docx", make_docx(), DOCX_MIME)
        expect(self.page.locator("#inputText")).to_have_value(re.compile("你好，Flow 👋"))
        value = self.page.locator("#inputText").input_value()
        self.assertIn("Latin text & 中文\n下一行\t制表位", value)
        self.assertRegex(value, r"单元格 A\s+Cell B")
        self.assertIn("链接文字", value)
        self.start_reader(draft=value)
        expect(self.page.locator("#text")).to_have_text(value)
        expect(self.page.locator("#text script, #text img")).to_have_count(0)
        self.assertIsNone(self.page.evaluate("window.docxExecuted"))
        self.assertFalse(any("docx-import.invalid" in url for url in self.requests))

    def test_docx_uppercase_missing_mime_and_strict_namespace(self):
        self.upload("大写扩展名.DOCX", make_docx(namespace=STRICT_NS), "")
        expect(self.page.locator("#inputText")).to_have_value(re.compile("你好，Flow 👋"))
        self.assertIn("Latin text & 中文\n下一行\t制表位", self.page.locator("#inputText").input_value())
        value = self.page.locator("#inputText").input_value()
        self.reload_page()
        expect(self.page.locator("#inputText")).to_have_value(value)

    def test_docx_preserves_nonbreaking_hyphen(self):
        document = word_document(
            "<w:p><w:r><w:t>well</w:t><w:noBreakHyphen/><w:t>being</w:t></w:r></w:p>"
        )
        self.upload("nonbreaking-hyphen.docx", make_docx(document), DOCX_MIME)
        expected = "well\u2011being"
        expect(self.page.locator("#inputText")).to_have_value(expected)
        self.wait_saved(expected)
        self.reload_page()
        expect(self.page.locator("#inputText")).to_have_value(expected)

    def test_docx_undo_and_reselecting_same_file(self):
        draft = "导入前仍有价值的草稿。"
        package = make_docx(word_document(paragraph("新的 Word 文稿。")))
        self.page.locator("#inputText").fill(draft)
        self.upload("same.docx", package, DOCX_MIME)
        expect(self.page.locator("#inputText")).to_have_value("新的 Word 文稿。")
        self.wait_saved("新的 Word 文稿。")
        self.page.locator("#toastAction").click()
        expect(self.page.locator("#inputText")).to_have_value(draft)
        self.upload("same.docx", package, DOCX_MIME)
        expect(self.page.locator("#inputText")).to_have_value("新的 Word 文稿。")

    def test_empty_invalid_and_unsupported_imports_preserve_draft(self):
        cases = [
            ("empty.txt", b"\xef\xbb\xbf \r\n\t", "text/plain"),
            ("invalid.docx", b"This is not a ZIP archive.", DOCX_MIME),
            ("empty.docx", make_docx(word_document("<w:p/>")), DOCX_MIME),
            ("broken-xml.docx", make_docx("<w:document><broken>"), DOCX_MIME),
            ("old.doc", b"old binary Word format", "application/msword"),
            ("unsupported.pdf", b"%PDF-1.7", "application/pdf"),
        ]
        for name, data, mime in cases:
            with self.subTest(file=name):
                # A fresh navigation prevents a previous toast from satisfying the error check.
                self.reload_page()
                self.assert_rejected_import(name, data, mime)

    def test_missing_word_document_preserves_draft(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as package:
            package.writestr("unrelated.xml", "<root>Not a Word document</root>")
        self.assert_rejected_import("missing.docx", stream.getvalue(), DOCX_MIME)

    def test_file_size_limits_preserve_draft(self):
        for name, size in [("large.txt", 1024 * 1024 + 1), ("large.docx", 10 * 1024 * 1024 + 1)]:
            with self.subTest(file=name):
                self.reload_page()
                draft = "文件太大时也应保留我。"
                self.page.locator("#inputText").fill(draft)
                # Allocate the real oversized File in-browser instead of transferring 10 MiB over the driver.
                self.page.locator("#importFile").evaluate("""(input, {name, size}) => {
                    const files = new DataTransfer();
                    files.items.add(new File([new Uint8Array(size)], name));
                    input.files = files.files;
                    input.dispatchEvent(new Event('change', {bubbles: true}));
                }""", {"name": name, "size": size})
                expect(self.page.locator("#toastMessage")).to_have_text(re.compile(r"[\u4e00-\u9fff]"))
                expect(self.page.locator("#importFile")).to_have_value("")
                expect(self.page.locator("#inputText")).to_have_value(draft)
                self.wait_saved(draft)

    def test_docx_xml_and_extracted_text_limits_preserve_draft(self):
        oversized_xml = word_document(paragraph("少量正文") + "<!--" + "x" * (8 * 1024 * 1024) + "-->")
        cases = [
            ("xml-limit.docx", make_docx(oversized_xml), DOCX_MIME),
            ("text-limit.docx", make_docx(word_document(paragraph("x" * 1_000_001))), DOCX_MIME),
            ("text-limit.txt", b"x" * 1_000_001, "text/plain"),
        ]
        for name, data, mime in cases:
            with self.subTest(file=name):
                self.reload_page()
                self.assert_rejected_import(name, data, mime)

    def test_zip_load_failure_is_retryable(self):
        package = make_docx(word_document(paragraph("重试后可以导入。")))
        failed_requests = []

        def fail_library(route):
            failed_requests.append(route.request.url)
            route.abort()

        self.page.route("**/vendor/fflate-*.js", fail_library)
        self.assert_rejected_import("retry.docx", package, DOCX_MIME)
        self.assertEqual(len(failed_requests), 1)
        self.page.unroute("**/vendor/fflate-*.js", fail_library)
        self.upload("retry.docx", package, DOCX_MIME)
        expect(self.page.locator("#inputText")).to_have_value("重试后可以导入。")

    def test_async_import_cannot_overwrite_a_later_edit(self):
        self.page.locator("#inputText").fill("开始导入前的内容。")
        idle_label = self.page.locator("#importBtn").get_attribute("aria-label")
        self.page.evaluate("""() => {
            window.FlowDocumentImport = {
                read: () => new Promise(resolve => { window.resolvePendingImport = resolve; })
            };
        }""")
        self.upload("slow.docx", make_docx(), DOCX_MIME)
        self.page.wait_for_function("typeof window.resolvePendingImport === 'function'")
        expect(self.page.locator("#importBtn")).to_have_attribute("aria-busy", "true")
        expect(self.page.locator("#importBtn")).to_be_disabled()
        expect(self.page.locator("#importBtn")).not_to_have_attribute("aria-label", idle_label)
        self.page.locator("#inputText").fill("这是等待期间刚刚写下的新文稿。")
        self.page.evaluate("window.resolvePendingImport('不应覆盖新文稿的导入结果。')")
        expect(self.page.locator("#importBtn")).to_have_attribute("aria-busy", "false")
        expect(self.page.locator("#importBtn")).to_have_attribute("aria-label", idle_label)
        expect(self.page.locator("#importBtn")).to_be_enabled()
        expect(self.page.locator("#importFile")).to_have_value("")
        expect(self.page.locator("#inputText")).to_have_value("这是等待期间刚刚写下的新文稿。")
        self.reload_page()
        expect(self.page.locator("#inputText")).to_have_value("这是等待期间刚刚写下的新文稿。")

    def test_modal_focus_escape_buttons_and_backdrop(self):
        self.open_settings()
        self.page.locator("#inputText").evaluate("el => el.focus()")
        self.assertTrue(self.page.locator("#settingsDialog").evaluate("el => el.contains(document.activeElement)"))
        for _ in range(22):
            # Native dialogs permit a Tab stop in browser chrome (hasFocus() becomes false).
            # Every focused document control must still belong to the modal.
            self.assertTrue(self.page.locator("#settingsDialog").evaluate("el => !document.hasFocus() || el.contains(document.activeElement)"))
            self.page.keyboard.press("Tab")
        self.page.keyboard.press("Escape")
        expect(self.page.locator("#settingsDialog")).to_be_hidden()
        expect(self.page.locator("#openSettingsBtn")).to_be_focused()
        for close_button in ["#closeSettingsBtn", "#doneSettingsBtn"]:
            self.open_settings()
            self.page.locator(close_button).click()
            expect(self.page.locator("#settingsDialog")).to_be_hidden()
            expect(self.page.locator("#openSettingsBtn")).to_be_focused()
        self.open_settings()
        self.page.locator("#fontSize").click()
        expect(self.page.locator("#settingsDialog")).to_be_visible()
        bounds = self.page.locator("#settingsDialog").bounding_box()
        self.assertTrue(bounds["x"] > 2 or bounds["y"] > 2, "Dialog needs an exposed backdrop")
        self.page.mouse.click(1, 1)
        expect(self.page.locator("#settingsDialog")).to_be_hidden()
        expect(self.page.locator("#openSettingsBtn")).to_be_focused()

    def test_settings_persistence_mirror_colors_and_visibility(self):
        self.page.locator("#inputText").fill(LONG_DRAFT)
        self.configure(fontSize=64, speed=70, mirror=True, showTimer=False, refLineWidth=0, countdownSetting=0)
        self.open_settings()
        for name, value in [("fontColor", "#ffee00"), ("bgColor", "#102030"), ("refLineColor", "#ff0088")]:
            self.set_range(f"#{name}", value)
        family = self.page.locator("#fontFamily option").last.get_attribute("value")
        self.page.locator("#fontFamily").select_option(family)
        self.page.locator("#doneSettingsBtn").click()
        self.reload_page()
        self.open_settings()
        for name, value in [("fontSize", "64"), ("fontSizeRange", "64"), ("speed", "70"), ("speedRange", "70"), ("fontColor", "#ffee00"), ("bgColor", "#102030"), ("refLineColor", "#ff0088"), ("fontFamily", family)]:
            expect(self.page.locator(f"#{name}")).to_have_value(value)
        expect(self.page.locator("#mirror")).to_be_checked()
        expect(self.page.locator("#showTimer")).not_to_be_checked()
        self.page.locator("#doneSettingsBtn").click()
        self.page.locator("#startBtn").click()
        expect(self.page.locator("#text")).to_have_css("font-size", "64px")
        expect(self.page.locator("#text")).to_have_css("color", "rgb(255, 238, 0)")
        expect(self.page.locator("#display")).to_have_css("background-color", "rgb(16, 32, 48)")
        expect(self.page.locator("#timer")).to_be_hidden()
        expect(self.page.locator("#referenceLine")).to_be_hidden()
        self.assertEqual(self.page.locator("#readerMirror").evaluate("el => new DOMMatrix(getComputedStyle(el).transform).m11"), -1)
        self.assertTrue(self.page.locator("#controlButtons").evaluate("el => !el.closest('#readerMirror')"))

    def test_reset_settings_preserves_draft(self):
        self.open_settings()
        setting_values = """() => Object.fromEntries(
            Array.from(document.querySelectorAll('#settingsDialog input, #settingsDialog select'))
                .filter(el => el.id)
                .map(el => [el.id, el.type === 'checkbox' ? el.checked : el.value])
        )"""
        defaults = self.page.evaluate(setting_values)
        self.page.locator("#doneSettingsBtn").click()
        draft = "重置的是设置，文稿应当保留。"
        self.page.locator("#inputText").fill(draft)
        self.configure(fontSize=91, speed=15, mirror=True, showTimer=False, countdownSetting=0)
        self.open_settings()
        self.page.locator("#resetSettingsBtn").click()
        self.assertEqual(self.page.evaluate(setting_values), defaults)
        self.page.locator("#doneSettingsBtn").click()
        expect(self.page.locator("#inputText")).to_have_value(draft)
        self.reload_page()
        expect(self.page.locator("#inputText")).to_have_value(draft)
        self.open_settings()
        self.assertEqual(self.page.evaluate(setting_values), defaults)

    def test_corrupt_settings_preserve_draft_and_valid_ranges(self):
        default_color = self.page.locator("#fontColor").input_value()
        init_script = NO_FULLSCREEN + """
            localStorage.setItem('savedText', '旧文稿仍然在。');
            localStorage.setItem('flow.teleprompter.settings.v1', JSON.stringify({fontSize: 900, speed: -100, fontFamily: '<script>', mirror: 'true', fontColor: 'broken'}));
        """
        with self.phone(init_script=init_script) as phone:
            expect(phone.locator("#inputText")).to_have_value("旧文稿仍然在。")
            self.open_settings(phone)
            expect(phone.locator("#fontSize")).to_have_value("100")
            expect(phone.locator("#speed")).to_have_value("10")
            expect(phone.locator("#mirror")).not_to_be_checked()
            expect(phone.locator("#fontColor")).to_have_value(default_color)
            self.assertNotEqual(phone.locator("#fontFamily").input_value(), "<script>")

    def test_reader_font_controls_replace_pause_button(self):
        self.start_reader(fontSize=36)
        expect(self.page.locator("#readerViewport")).to_have_attribute("role", "button")
        expect(self.page.locator("#playbackStatus")).to_have_attribute("role", "status")
        expect(self.page.locator("#fontSizeBtn, #fontSizePanel, #playerFontSizeRange, #closeFontSizeBtn, #pauseBtn")).to_have_count(0)
        expect(self.page.locator("#controlButtons button")).to_have_count(6)
        expect(self.page.locator("#playerFontSizeValue")).to_have_text("36")
        self.page.locator("#largerFontBtn").click()
        expect(self.page.locator("#playerFontSizeValue")).to_have_text("38")
        expect(self.page.locator("#display")).to_have_attribute("data-state", "playing")

    def test_reader_tap_space_enter_and_drag_preserve_pause_state(self):
        self.start_reader()
        self.tap_reader()
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        before = self.reader_metrics()
        bounds = self.page.locator("#readerViewport").bounding_box()
        x = bounds["x"] + bounds["width"] * 0.45
        y = bounds["y"] + bounds["height"] * 0.3
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x, y + 110, steps=6)
        self.page.mouse.up()
        after = self.reader_metrics()
        self.assertAlmostEqual(after["y"] - before["y"], 110, delta=2)
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        self.page.locator("#readerViewport").focus()
        self.page.keyboard.press("Space")
        expect(self.page.locator("#display")).to_have_attribute("data-state", "playing")
        self.page.keyboard.press("Enter")
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        self.tap_reader()
        expect(self.page.locator("#display")).to_have_attribute("data-state", "playing")

    def test_direct_font_buttons_preserve_progress_timer_and_persistence(self):
        self.page.clock.install()
        self.start_reader(fontSize=36)
        self.page.clock.run_for(10000)
        self.tap_reader()
        before = self.reader_metrics()
        self.assertGreater(before["progress"], 0)
        self.change_reader_font(64)
        expect(self.page.locator("#fontSize")).to_have_value("64")
        expect(self.page.locator("#fontSizeRange")).to_have_value("64")
        expect(self.page.locator("#text")).to_have_css("font-size", "64px")
        self.settle_layout()
        after = self.reader_metrics()
        self.assertAlmostEqual(after["fraction"], before["fraction"], delta=0.015)
        self.assertAlmostEqual(after["progress"], before["progress"], delta=3)
        self.assertEqual(after["timer"], before["timer"])
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        self.page.locator("#largerFontBtn").click()
        expect(self.page.locator("#playerFontSizeValue")).to_have_text("66")
        self.page.locator("#smallerFontBtn").click()
        expect(self.page.locator("#playerFontSizeValue")).to_have_text("64")
        speed = self.page.locator("#playbackSpeed").inner_text()
        button = self.page.locator("#largerFontBtn")
        button.focus()
        button.press("ArrowRight")
        expect(self.page.locator("#playerFontSizeValue")).to_have_text("64")
        expect(self.page.locator("#playbackSpeed")).to_have_text(speed)
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        button.press("Space")
        expect(self.page.locator("#playerFontSizeValue")).to_have_text("66")
        button.press("Enter")
        expect(self.page.locator("#playerFontSizeValue")).to_have_text("68")
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        for boundary, button in [(100, "#largerFontBtn"), (10, "#smallerFontBtn")]:
            self.change_reader_font(boundary)
            expect(self.page.locator(button)).to_be_disabled()
            expect(self.page.locator("#playerFontSizeValue")).to_have_text(str(boundary))
        self.change_reader_font(58)
        self.page.keyboard.press("Escape")
        expect(self.page.locator("#display")).to_be_hidden()
        self.reload_page()
        self.open_settings()
        expect(self.page.locator("#fontSize")).to_have_value("58")
        expect(self.page.locator("#fontSizeRange")).to_have_value("58")
        self.assertEqual(self.page.evaluate(f"JSON.parse(localStorage.getItem('{SETTINGS_KEY}')).fontSize"), 58)

    def test_direct_font_buttons_do_not_pause_playback(self):
        self.start_reader(fontSize=36)
        self.page.locator("#largerFontBtn").click()
        expect(self.page.locator("#text")).to_have_css("font-size", "38px")
        expect(self.page.locator("#display")).to_have_attribute("data-state", "playing")
        self.page.locator("#smallerFontBtn").click()
        expect(self.page.locator("#text")).to_have_css("font-size", "36px")
        expect(self.page.locator("#display")).to_have_attribute("data-state", "playing")

    def test_enlarged_font_updates_completion_and_replay(self):
        self.page.clock.install()
        draft = "\n".join(["Stay with this sentence as the font changes."] * 4)
        self.start_reader(draft=draft, fontSize=20, speed=100)
        self.page.clock.run_for(200)
        # Real pointer clicks take longer on WebKit; freeze playback while preparing
        # the larger layout so those clicks cannot consume the original deadline.
        self.tap_reader()
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        original = self.reader_metrics()
        self.change_reader_font(100)
        self.settle_layout()
        enlarged = self.reader_metrics()
        self.assertGreater(enlarged["remaining"], original["remaining"] + 100)
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        self.tap_reader()
        expect(self.page.locator("#display")).to_have_attribute("data-state", "playing")
        self.page.clock.run_for(math.ceil(max(0, original["remaining"]) / 100 * 1000 + 200))
        expect(self.page.locator("#display")).to_have_attribute("data-state", "playing")
        remaining = self.reader_metrics()["remaining"]
        self.page.clock.run_for(math.ceil(max(0, remaining) / 100 * 1000 + 300))
        expect(self.page.locator("#display")).to_have_attribute("data-state", "finished")
        expect(self.page.locator("#readingProgress")).to_have_attribute("aria-valuenow", "100")
        timer = self.page.locator("#timer").inner_text()
        self.page.clock.run_for(2000)
        expect(self.page.locator("#timer")).to_have_text(timer)
        self.change_reader_font(60)
        expect(self.page.locator("#display")).to_have_attribute("data-state", "finished")
        self.page.locator("#restartBtn").click()
        expect(self.page.locator("#display")).to_have_attribute("data-state", "playing")
        expect(self.page.locator("#timer")).to_have_text("00:00")
        self.assertLess(self.reader_metrics()["progress"], 5)

    def test_countdown_pause_timer_and_exit(self):
        self.page.locator("#inputText").fill(LONG_DRAFT)
        self.configure(countdownSetting=5)
        self.page.clock.install()
        self.page.locator("#startBtn").click()
        expect(self.page.locator("#display")).to_have_attribute("data-state", "countdown")
        expect(self.page.locator("#countdownNumber")).to_have_text("5")
        self.page.locator("#readerViewport").focus()
        self.page.keyboard.press("Space")
        expect(self.page.locator("#display")).to_have_attribute("data-state", "countdown")
        self.page.clock.run_for(5200)
        expect(self.page.locator("#countdown")).to_be_hidden()
        expect(self.page.locator("#display")).to_have_attribute("data-state", "playing")
        self.page.clock.run_for(2000)
        self.tap_reader()
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        timer = self.page.locator("#timer").inner_text()
        self.page.clock.run_for(3000)
        expect(self.page.locator("#timer")).to_have_text(timer)
        self.page.locator("#readerViewport").press("Enter")
        self.page.clock.run_for(1200)
        self.assertNotEqual(self.page.locator("#timer").inner_text(), timer)
        self.page.keyboard.press("Escape")
        expect(self.page.locator("#controls")).to_be_visible()
        expect(self.page.locator("#display")).to_be_hidden()

    def test_exit_during_countdown_and_repeated_start(self):
        self.page.clock.install()
        self.page.locator("#inputText").fill(LONG_DRAFT)
        self.configure(countdownSetting=5)
        for _ in range(2):
            self.page.locator("#startBtn").click()
            expect(self.page.locator("#display")).to_have_attribute("data-state", "countdown")
            self.page.locator("#exitBtn").click()
            self.page.clock.run_for(6000)
            expect(self.page.locator("#display")).to_be_hidden()
            expect(self.page.locator("#controls")).to_be_visible()
        self.start_reader()
        expect(self.page.locator("#countdown")).to_be_hidden()

    def test_speed_buttons_keep_bounds_and_saved_settings(self):
        self.start_reader()
        self.tap_reader()
        for _ in range(20):
            if self.page.locator("#fasterBtn").is_enabled():
                self.page.locator("#fasterBtn").click()
        expect(self.page.locator("#playbackSpeed")).to_have_text("100")
        for _ in range(25):
            if self.page.locator("#slowerBtn").is_enabled():
                self.page.locator("#slowerBtn").click()
        expect(self.page.locator("#playbackSpeed")).to_have_text("10")
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        self.page.locator("#exitBtn").click()
        self.open_settings()
        expect(self.page.locator("#speed")).to_have_value("10")
        expect(self.page.locator("#speedRange")).to_have_value("10")

    def test_gamepad_edges_and_return(self):
        self.page.evaluate("""() => {
            window.testPad = {buttons: Array.from({length: 16}, () => ({pressed: false})), axes: [0, 0]};
            Object.defineProperty(navigator, 'getGamepads', {value: () => [window.testPad]});
        }""")
        self.page.clock.install()
        self.start_reader()
        self.page.evaluate("window.testPad.buttons[0].pressed = true")
        self.page.clock.run_for(100)
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        self.page.clock.run_for(400)
        expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
        self.page.evaluate("window.testPad.buttons[0].pressed = false")
        self.page.clock.run_for(100)
        self.page.evaluate("window.testPad.buttons[0].pressed = true")
        self.page.clock.run_for(100)
        expect(self.page.locator("#display")).to_have_attribute("data-state", "playing")
        self.page.evaluate("window.testPad.buttons[1].pressed = true")
        self.page.clock.run_for(100)
        expect(self.page.locator("#display")).to_be_hidden()

    def test_mobile_desktop_layout_and_touch_targets(self):
        for width, height in [(320, 568), (390, 844), (844, 390), (1440, 1000)]:
            with self.subTest(viewport=(width, height)):
                self.page.set_viewport_size({"width": width, "height": height})
                self.reload_page()
                self.page.locator("#inputText").fill(LONG_DRAFT)
                self.page.locator("#inputText").blur()
                self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width + 1)
                for selector in ["#openLibraryBtn", "#openSettingsBtn", "#importBtn", "#clearBtn", "#startBtn"]:
                    self.assert_fits_viewport(selector, minimum_target=True)
                settings_bounds = self.page.locator("#openSettingsBtn").bounding_box()
                self.assertGreater(settings_bounds["x"], width / 2)
                self.open_settings()
                self.assert_fits_viewport("#settingsDialog")
                self.assert_fits_viewport("#closeSettingsBtn", minimum_target=True)
                for selector in ["#fontSize", "#countdownSetting", "#refLineWidth", "#resetSettingsBtn", "#doneSettingsBtn"]:
                    self.page.locator(selector).scroll_into_view_if_needed()
                    self.assert_fits_viewport(selector)
                self.page.locator("#countdownSetting").select_option("0")
                self.page.locator("#doneSettingsBtn").click()
                self.page.locator("#startBtn").click()
                self.tap_reader()
                expect(self.page.locator("#display")).to_have_attribute("data-state", "paused")
                for selector in ["#restartBtn", "#slowerBtn", "#fasterBtn", "#smallerFontBtn", "#largerFontBtn", "#exitBtn"]:
                    self.assert_fits_viewport(selector, minimum_target=True)
                expect(self.page.locator("#controlButtons button")).to_have_count(6)
                self.assert_fits_viewport("#playerFontSizeValue")
                buttons = self.page.locator("#controlButtons button").evaluate_all("""buttons => buttons.map(button => {
                    const {x, y, width, height} = button.getBoundingClientRect();
                    return {id: button.id, x, y, width, height};
                })""")
                for index, first in enumerate(buttons):
                    for second in buttons[index + 1:]:
                        overlap_x = min(first["x"] + first["width"], second["x"] + second["width"]) - max(first["x"], second["x"])
                        overlap_y = min(first["y"] + first["height"], second["y"] + second["height"]) - max(first["y"], second["y"])
                        self.assertTrue(overlap_x <= 1 or overlap_y <= 1, f"Overlapping buttons: {first['id']}, {second['id']}")
                if width <= 400:
                    bounds = {button["id"]: button for button in buttons}
                    self.assertAlmostEqual(bounds["slowerBtn"]["y"], bounds["fasterBtn"]["y"], delta=1)
                    self.assertAlmostEqual(bounds["smallerFontBtn"]["y"], bounds["largerFontBtn"]["y"], delta=1)
                    speed_bottom = max(bounds[name]["y"] + bounds[name]["height"] for name in ["slowerBtn", "fasterBtn"])
                    font_top = min(bounds[name]["y"] for name in ["smallerFontBtn", "largerFontBtn"])
                    self.assertLessEqual(speed_bottom, font_top + 1)
                self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width + 1)
                self.page.locator("#exitBtn").click()

    def test_touch_rotation_preserves_position_timer_and_direct_controls(self):
        with self.phone() as phone:
            phone.clock.install()
            self.start_reader(phone, fontSize=36)
            phone.clock.run_for(3000)
            phone.touchscreen.tap(175, 245)
            expect(phone.locator("#display")).to_have_attribute("data-state", "paused")
            before = self.reader_metrics(phone)
            for width, height in [(844, 390), (390, 844)]:
                phone.set_viewport_size({"width": width, "height": height})
                self.settle_layout(phone)
                after = self.reader_metrics(phone)
                self.assertAlmostEqual(after["fraction"], before["fraction"], delta=0.015)
                self.assertEqual(after["timer"], before["timer"])
                expect(phone.locator("#display")).to_have_attribute("data-state", "paused")
                self.assert_fits_viewport("#smallerFontBtn", phone, minimum_target=True)
                self.assert_fits_viewport("#largerFontBtn", phone, minimum_target=True)
                self.assert_fits_viewport("#controlButtons", phone)
                self.assertLessEqual(phone.evaluate("document.documentElement.scrollWidth"), width + 1)
            phone.touchscreen.tap(175, 245)
            expect(phone.locator("#display")).to_have_attribute("data-state", "playing")
            phone.locator("#exitBtn").click()
            expect(phone.locator("#controls")).to_be_visible()
            self.assertFalse(phone.locator("body").evaluate("el => el.classList.contains('keyboard-open')"))

    def test_optional_browser_apis_unavailable_or_rejected(self):
        variants = {
            "absent": NO_FULLSCREEN + "Object.defineProperty(navigator, 'wakeLock', {value: undefined});",
            "rejected": """
                Element.prototype.requestFullscreen = () => Promise.reject(new Error('blocked'));
                Element.prototype.webkitRequestFullscreen = undefined;
                Object.defineProperty(navigator, 'wakeLock', {value: {
                    request: () => Promise.reject(new Error('blocked'))
                }});
            """,
        }
        storage_blocked = """
            Storage.prototype.getItem = () => { throw new DOMException('blocked', 'SecurityError'); };
            Storage.prototype.setItem = () => { throw new DOMException('blocked', 'SecurityError'); };
        """
        for name, init_script in variants.items():
            with self.subTest(apis=name), self.phone(init_script=init_script + storage_blocked) as phone:
                draft = "浏览器限制存储与全屏时，仍然可以提词。"
                self.start_reader(phone, draft=draft)
                phone.touchscreen.tap(175, 245)
                expect(phone.locator("#display")).to_have_attribute("data-state", "paused")
                self.change_reader_font(50, phone)
                expect(phone.locator("#text")).to_have_css("font-size", "50px")
                phone.locator("#exitBtn").click()
                expect(phone.locator("#inputText")).to_have_value(draft)

    def test_wake_lock_is_released_on_exit(self):
        self.page.add_init_script("""
            window.lockRequests = 0;
            window.lockReleases = 0;
            Object.defineProperty(navigator, 'wakeLock', {value: {
                request: async () => {
                    window.lockRequests += 1;
                    return {addEventListener() {}, release: async () => { window.lockReleases += 1; }};
                }
            }});
        """)
        self.reload_page()
        self.start_reader()
        self.page.wait_for_function("window.lockRequests === 1")
        self.page.locator("#exitBtn").click()
        self.page.wait_for_function("window.lockReleases === 1")
        self.page.locator("#startBtn").click()
        self.page.wait_for_function("window.lockRequests === 2")
        self.page.locator("#exitBtn").click()
        self.page.wait_for_function("window.lockReleases === 2")

    def test_native_fullscreen_exit_returns_to_editor_when_supported(self):
        with self.phone(init_script="") as phone:
            self.start_reader(phone)
            if not phone.evaluate("Boolean(document.fullscreenElement || document.webkitFullscreenElement)"):
                self.skipTest("Browser uses the in-page fullscreen fallback")
            phone.evaluate("() => (document.exitFullscreen || document.webkitExitFullscreen).call(document)")
            expect(phone.locator("#display")).to_be_hidden()
            expect(phone.locator("#controls")).to_be_visible()

    def test_visual_viewport_keyboard_hint_recovers(self):
        # This checks viewport event handling; real iOS/Android keyboard behavior still needs a device.
        init_script = NO_FULLSCREEN + """
            window.testViewport = new EventTarget();
            // Init scripts precede viewport metadata; use the configured mobile CSS dimensions.
            Object.assign(window.testViewport, {height: 844, width: 390, offsetTop: 0, scale: 1});
            Object.defineProperty(window, 'visualViewport', {value: window.testViewport});
        """
        with self.phone(init_script=init_script) as phone:
            phone.locator("#inputText").focus()
            phone.evaluate("window.testViewport.height = 490; window.testViewport.dispatchEvent(new Event('resize'))")
            phone.wait_for_function("document.body.classList.contains('keyboard-open')")
            height = phone.evaluate("parseFloat(document.documentElement.style.getPropertyValue('--app-height'))")
            self.assertAlmostEqual(height, 490, delta=1)
            phone.locator("#inputText").blur()
            phone.evaluate("window.testViewport.height = 844; window.testViewport.dispatchEvent(new Event('resize'))")
            phone.wait_for_function("!document.body.classList.contains('keyboard-open')")
            self.assert_fits_viewport("#startBtn", phone, minimum_target=True)

    def test_settings_dialog_stays_inside_visual_viewport_with_keyboard(self):
        # A keyboard can shrink and pan the visual viewport without resizing the layout viewport.
        # Check the visible interval itself; fitting inside innerHeight alone misses covered buttons.
        for width, height, visible_height, offset_top in [(390, 844, 490, 40), (844, 390, 230, 20)]:
            with self.subTest(viewport=(width, height), visible=(offset_top, visible_height)):
                init_script = NO_FULLSCREEN + f"""
                    window.testViewport = new EventTarget();
                    Object.assign(window.testViewport, {{height: {height}, width: {width}, offsetTop: 0, offsetLeft: 0, scale: 1}});
                    Object.defineProperty(window, 'visualViewport', {{value: window.testViewport}});
                """
                with self.phone(width, height, init_script) as phone:
                    self.open_settings(phone)
                    initial_bounds = phone.locator("#settingsDialog").bounding_box()
                    phone.locator("#fontSize").focus()
                    phone.evaluate("""({height, offsetTop}) => {
                        Object.assign(window.testViewport, {height, offsetTop});
                        window.testViewport.dispatchEvent(new Event('resize'));
                    }""", {"height": visible_height, "offsetTop": offset_top})
                    phone.wait_for_function("document.body.classList.contains('keyboard-open')")
                    self.settle_layout(phone)
                    expect(phone.locator("#fontSize")).to_be_focused()
                    visible_bottom = offset_top + visible_height
                    for selector in ["#settingsDialog", "#closeSettingsBtn", "#doneSettingsBtn"]:
                        expect(phone.locator(selector)).to_be_visible()
                        bounds = phone.locator(selector).bounding_box()
                        self.assertGreaterEqual(bounds["y"], offset_top - 1, f"{selector} above visible viewport: {bounds}")
                        self.assertLessEqual(bounds["y"] + bounds["height"], visible_bottom + 1, f"{selector} below visible viewport: {bounds}")
                        self.assertGreaterEqual(bounds["x"], -1, selector)
                        self.assertLessEqual(bounds["x"] + bounds["width"], width + 1, selector)
                    phone.evaluate("""height => {
                        Object.assign(window.testViewport, {height, offsetTop: 0});
                        window.testViewport.dispatchEvent(new Event('resize'));
                    }""", height)
                    phone.wait_for_function("!document.body.classList.contains('keyboard-open')")
                    self.settle_layout(phone)
                    restored_bounds = phone.locator("#settingsDialog").bounding_box()
                    self.assertAlmostEqual(restored_bounds["y"], initial_bounds["y"], delta=2)
                    self.assertAlmostEqual(restored_bounds["height"], initial_bounds["height"], delta=2)
                    for selector in ["#settingsDialog", "#closeSettingsBtn", "#doneSettingsBtn"]:
                        self.assert_fits_viewport(selector, phone)
                    phone.locator("#doneSettingsBtn").click()
                    expect(phone.locator("#settingsDialog")).to_be_hidden()
                    expect(phone.locator("#openSettingsBtn")).to_be_focused()
                    self.assert_fits_viewport("#startBtn", phone, minimum_target=True)

    def test_settings_close_actions_survive_keyboard_blur_with_short_viewport(self):
        for width, height, visible_height, offset_top in [(390, 844, 490, 40), (844, 390, 230, 20)]:
            for button in ["#doneSettingsBtn", "#closeSettingsBtn"]:
                for interaction in ["mouse", "touch"]:
                    with self.subTest(viewport=(width, height), button=button, interaction=interaction):
                        init_script = NO_FULLSCREEN + f"""
                            window.testViewport = new EventTarget();
                            Object.assign(window.testViewport, {{height: {height}, width: {width}, offsetTop: 0, offsetLeft: 0, scale: 1}});
                            Object.defineProperty(window, 'visualViewport', {{value: window.testViewport}});
                        """
                        with self.phone(width, height, init_script) as phone:
                            self.open_settings(phone)
                            initial_bounds = phone.locator("#settingsDialog").bounding_box()
                            phone.locator("#fontSize").fill("72")
                            self.resize_mock_visual_viewport(phone, visible_height, offset_top)
                            expect(phone.locator("#fontSize")).to_be_focused()
                            bounds = phone.locator(button).bounding_box()
                            self.assertGreaterEqual(bounds["y"], offset_top - 1)
                            self.assertLessEqual(bounds["y"] + bounds["height"], offset_top + visible_height + 1)

                            # Keep the keyboard viewport unchanged through pointerdown, blur, and click.
                            self.activate_at_current_position(phone, button, interaction)
                            expect(phone.locator("#settingsDialog")).to_be_hidden()
                            expect(phone.locator("#openSettingsBtn")).to_be_focused()
                            self.assertEqual(phone.evaluate("visualViewport.height"), visible_height)
                            self.assertEqual(phone.evaluate("visualViewport.offsetTop"), offset_top)
                            self.assertEqual(phone.evaluate(f"JSON.parse(localStorage.getItem('{SETTINGS_KEY}')).fontSize"), 72)

                            self.resize_mock_visual_viewport(phone, height)
                            phone.wait_for_function("!document.body.classList.contains('keyboard-open')")
                            self.assert_fits_viewport("#startBtn", phone, minimum_target=True)
                            self.open_settings(phone)
                            restored_bounds = phone.locator("#settingsDialog").bounding_box()
                            self.assertAlmostEqual(restored_bounds["y"], initial_bounds["y"], delta=2)
                            self.assertAlmostEqual(restored_bounds["height"], initial_bounds["height"], delta=2)
                            expect(phone.locator("#fontSize")).to_have_value("72")
                            self.assert_fits_viewport("#doneSettingsBtn", phone, minimum_target=True)
                            self.activate_at_current_position(phone, "#closeSettingsBtn", interaction)
                            expect(phone.locator("#settingsDialog")).to_be_hidden()

    def test_settings_reset_survives_keyboard_blur_with_short_viewport(self):
        draft = "键盘收起期间恢复默认，也应保留这份文稿。"
        for width, height, visible_height, offset_top in [(390, 844, 490, 40), (844, 390, 230, 20)]:
            for interaction in ["mouse", "touch"]:
                with self.subTest(viewport=(width, height), interaction=interaction):
                    init_script = NO_FULLSCREEN + f"""
                        window.testViewport = new EventTarget();
                        Object.assign(window.testViewport, {{height: {height}, width: {width}, offsetTop: 0, offsetLeft: 0, scale: 1}});
                        Object.defineProperty(window, 'visualViewport', {{value: window.testViewport}});
                    """
                    with self.phone(width, height, init_script) as phone:
                        phone.locator("#inputText").fill(draft)
                        self.open_settings(phone)
                        default_font = phone.locator("#fontSize").input_value()
                        default_speed = phone.locator("#speed").input_value()
                        phone.locator("#speed").fill("77")
                        phone.locator("#fontSize").fill("72")
                        self.resize_mock_visual_viewport(phone, visible_height, offset_top)
                        expect(phone.locator("#fontSize")).to_be_focused()
                        self.activate_at_current_position(phone, "#resetSettingsBtn", interaction)
                        expect(phone.locator("#settingsDialog")).to_be_visible()
                        expect(phone.locator("#fontSize")).to_have_value(default_font)
                        expect(phone.locator("#speed")).to_have_value(default_speed)
                        expect(phone.locator("#inputText")).to_have_value(draft)
                        self.assertEqual(phone.evaluate("visualViewport.height"), visible_height)
                        for selector in ["#settingsDialog", "#resetSettingsBtn", "#doneSettingsBtn"]:
                            bounds = phone.locator(selector).bounding_box()
                            self.assertGreaterEqual(bounds["y"], offset_top - 1, selector)
                            self.assertLessEqual(bounds["y"] + bounds["height"], offset_top + visible_height + 1, selector)
                        self.resize_mock_visual_viewport(phone, height)
                        phone.wait_for_function("!document.body.classList.contains('keyboard-open')")
                        self.assert_fits_viewport("#settingsDialog", phone)
                        self.activate_at_current_position(phone, "#doneSettingsBtn", interaction)
                        expect(phone.locator("#settingsDialog")).to_be_hidden()
                        self.assert_fits_viewport("#startBtn", phone, minimum_target=True)
                        expect(phone.locator("#inputText")).to_have_value(draft)


class ArtifactResult(unittest.TextTestResult):
    def startTestRun(self):
        self.started_at = time.monotonic()
        super().startTestRun()

    def stopTestRun(self):
        super().stopTestRun()
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        payload = {
            "browser": BROWSER,
            "url": BASE_URL,
            "tests_run": self.testsRun,
            "elapsed_seconds": round(time.monotonic() - self.started_at, 2),
            "successful": self.wasSuccessful(),
            "failures": [{"test": str(test), "detail": detail} for test, detail in self.failures],
            "errors": [{"test": str(test), "detail": detail} for test, detail in self.errors],
            "skipped": [{"test": str(test), "reason": reason} for test, reason in self.skipped],
            "browser_logs": TeleprompterTests.browser_logs,
        }
        (ARTIFACTS / f"results-{BROWSER}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2, resultclass=ArtifactResult))
