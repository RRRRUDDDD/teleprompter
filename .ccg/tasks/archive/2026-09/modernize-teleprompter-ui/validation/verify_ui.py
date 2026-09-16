"""Browser regression checks. Run with Python and the Playwright package installed."""
import os
import re
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


BASE_URL = os.environ.get("TELEPROMPTER_TEST_URL", "http://127.0.0.1:4173")
ARTIFACTS = Path(__file__).resolve().parent


class TeleprompterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser_name = os.environ.get("TELEPROMPTER_TEST_BROWSER", "chromium")
        cls.browser = getattr(cls.playwright, cls.browser_name).launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto(BASE_URL, wait_until="networkidle")

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [], "Uncaught browser errors")

    def start_without_countdown(self):
        self.page.locator("#countdownSetting").select_option("0")
        self.page.locator("#startBtn").click()
        expect(self.page.locator("#display")).to_be_visible()

    def test_editor_persistence_and_plain_text_rendering(self):
        draft = "你好，鏡頭。\nKeep your own pace.\n<script>window.injected = true</script>"
        self.page.locator("#inputText").fill(draft)
        expect(self.page.locator("#previewText")).to_have_text(draft)
        self.assertIsNone(self.page.evaluate("window.injected"))
        self.page.reload()
        expect(self.page.locator("#inputText")).to_have_value(draft)
        expect(self.page.locator("#wordCount")).to_have_text(str(len(re.sub(r"\s", "", draft))))

    def test_clear_undo_and_intentionally_empty_draft(self):
        draft = "這段文字應該可以復原。"
        self.page.locator("#inputText").fill(draft)
        self.page.locator("#clearBtn").click()
        expect(self.page.locator("#inputText")).to_have_value("")
        expect(self.page.locator("#startBtn")).to_be_disabled()
        self.page.locator("#toastAction").click()
        expect(self.page.locator("#inputText")).to_have_value(draft)
        self.page.locator("#clearBtn").click()
        self.page.reload()
        expect(self.page.locator("#inputText")).to_have_value("")
        expect(self.page.locator("#startBtn")).to_be_disabled()

    def test_text_import(self):
        self.page.locator("#importFile").set_input_files({
            "name": "訪談稿.txt", "mimeType": "text/plain",
            "buffer": "第一個問題。\n第二個問題。".encode("utf-8"),
        })
        expect(self.page.locator("#inputText")).to_have_value("第一個問題。\n第二個問題。")

    def test_editor_keyboard_does_not_control_playback(self):
        editor = self.page.locator("#inputText")
        editor.fill("Hello")
        editor.press("End")
        editor.press("Space")
        editor.type("world")
        editor.press("ArrowLeft")
        editor.press("Escape")
        expect(editor).to_have_value("Hello world")
        expect(self.page.locator("#display")).to_be_hidden()

    def test_settings_preview_and_persistence(self):
        self.page.locator("#fontSize").fill("64")
        self.page.locator("#fontSize").press("Tab")
        self.page.locator("#speed").fill("70")
        self.page.locator("#speed").press("Tab")
        self.page.locator("#mirror").check()
        self.page.locator("#showTimer").uncheck()
        self.page.locator("#refLineWidth").select_option("0")
        expect(self.page.locator("#fontSizeRange")).to_have_value("64")
        expect(self.page.locator("#previewTimer")).to_be_hidden()
        expect(self.page.locator("#previewReferenceLine")).to_be_hidden()
        self.page.reload()
        expect(self.page.locator("#fontSize")).to_have_value("64")
        expect(self.page.locator("#speed")).to_have_value("70")
        expect(self.page.locator("#mirror")).to_be_checked()
        self.start_without_countdown()
        expect(self.page.locator("#text")).to_have_css("font-size", "64px")
        expect(self.page.locator("#timer")).to_be_hidden()

    def test_countdown_pause_timer_and_exit(self):
        self.page.clock.install()
        self.page.locator("#startBtn").click()
        expect(self.page.locator("#countdownNumber")).to_have_text("5")
        self.page.clock.run_for(5200)
        expect(self.page.locator("#countdown")).to_be_hidden()
        self.page.clock.run_for(2000)
        self.page.keyboard.press("Space")
        expect(self.page.locator("#pauseLabel")).to_have_text("继续")
        timer = self.page.locator("#timer").inner_text()
        self.page.clock.run_for(3000)
        expect(self.page.locator("#timer")).to_have_text(timer)
        self.page.keyboard.press("Space")
        self.page.clock.run_for(1200)
        self.assertNotEqual(self.page.locator("#timer").inner_text(), timer)
        self.page.keyboard.press("Escape")
        expect(self.page.locator("#controls")).to_be_visible()
        expect(self.page.locator("#display")).to_be_hidden()

    def test_exit_during_countdown_and_repeated_start(self):
        self.page.clock.install()
        for _ in range(2):
            self.page.locator("#startBtn").click()
            self.page.locator("#exitBtn").click()
            self.page.clock.run_for(6000)
            expect(self.page.locator("#display")).to_be_hidden()
            expect(self.page.locator("#controls")).to_be_visible()
        self.start_without_countdown()
        expect(self.page.locator("#countdown")).to_be_hidden()

    def test_mobile_panels_and_fixed_start_button(self):
        for width, height in [(390, 844), (320, 740), (844, 390)]:
            self.page.set_viewport_size({"width": width, "height": height})
            self.page.reload()
            for panel in ["editor", "preview", "settings"]:
                self.page.locator(f'.mobile-tabs [data-panel="{panel}"]').click()
                expect(self.page.locator(f'[data-mobile-panel="{panel}"]')).to_be_visible()
                self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)
                bounds = self.page.locator("#startBtn").bounding_box()
                self.assertGreaterEqual(bounds["x"], 0)
                self.assertLessEqual(bounds["y"] + bounds["height"], height)
            self.page.locator('.mobile-tabs [data-panel="editor"]').click()

    def test_help_dialog_keyboard_focus(self):
        self.page.locator("#openModalBtn").click()
        expect(self.page.locator("#myModal")).to_be_visible()
        self.page.keyboard.press("Escape")
        expect(self.page.locator("#myModal")).to_be_hidden()
        expect(self.page.locator("#openModalBtn")).to_be_focused()

    def test_dragging_paused_script_does_not_resume(self):
        self.start_without_countdown()
        self.page.locator("#pauseBtn").click()
        before = self.page.locator("#text").evaluate("el => new DOMMatrix(getComputedStyle(el).transform).m42")
        self.page.mouse.move(700, 500)
        self.page.mouse.down()
        self.page.mouse.move(700, 620, steps=5)
        self.page.mouse.up()
        after = self.page.locator("#text").evaluate("el => new DOMMatrix(getComputedStyle(el).transform).m42")
        self.assertGreater(after, before + 80)
        expect(self.page.locator("#pauseLabel")).to_have_text("继续")

    def test_unavailable_browser_apis_are_nonfatal(self):
        self.page.add_init_script("""
            Storage.prototype.getItem = () => { throw new DOMException('blocked', 'SecurityError'); };
            Storage.prototype.setItem = () => { throw new DOMException('blocked', 'SecurityError'); };
            Element.prototype.requestFullscreen = () => Promise.reject(new Error('blocked'));
            Object.defineProperty(navigator, 'wakeLock', { value: {
                request: () => Promise.reject(new Error('blocked'))
            }});
        """)
        self.page.reload()
        self.page.locator("#inputText").fill("儲存不可用，依然可以提詞。")
        self.start_without_countdown()
        self.page.locator("#exitBtn").click()
        expect(self.page.locator("#inputText")).to_have_value("儲存不可用，依然可以提詞。")

    def test_native_fullscreen_exit_returns_to_editor(self):
        self.start_without_countdown()
        if not self.page.evaluate("Boolean(document.fullscreenElement)"):
            self.skipTest("This browser uses the in-page fullscreen fallback")
        self.page.evaluate("document.exitFullscreen()")
        expect(self.page.locator("#display")).to_be_hidden()
        expect(self.page.locator("#controls")).to_be_visible()

    def test_preview_playback_and_colors(self):
        self.page.clock.install()
        before = self.page.locator("#previewText").evaluate("el => new DOMMatrix(getComputedStyle(el).transform).m42")
        self.page.locator("#previewPlayBtn").click()
        self.page.clock.run_for(1200)
        after = self.page.locator("#previewText").evaluate("el => new DOMMatrix(getComputedStyle(el).transform).m42")
        self.assertLess(after, before - 10)
        self.page.locator("#previewPlayBtn").click()
        self.page.clock.run_for(800)
        expect(self.page.locator("#previewPlayLabel")).to_have_text("播放预览")
        self.page.locator("#fontColor").evaluate("el => {el.value = '#ffee00'; el.dispatchEvent(new Event('input', {bubbles: true}));}")
        self.page.locator("#bgColor").evaluate("el => {el.value = '#102030'; el.dispatchEvent(new Event('input', {bubbles: true}));}")
        expect(self.page.locator("#previewText")).to_have_css("color", "rgb(255, 238, 0)")
        expect(self.page.locator("#previewStage")).to_have_css("background-color", "rgb(16, 32, 48)")
        self.page.locator("#mirror").check()
        self.assertEqual(self.page.locator("#previewMirror").evaluate("el => new DOMMatrix(getComputedStyle(el).transform).m11"), -1)

    def test_gamepad_edges_and_return(self):
        self.page.evaluate("""() => {
            window.testPad = {buttons: Array.from({length: 16}, () => ({pressed: false})), axes: [0, 0]};
            Object.defineProperty(navigator, 'getGamepads', {value: () => [window.testPad]});
        }""")
        self.page.clock.install()
        self.start_without_countdown()
        self.page.evaluate("window.testPad.buttons[0].pressed = true")
        self.page.clock.run_for(100)
        expect(self.page.locator("#pauseLabel")).to_have_text("继续")
        self.page.clock.run_for(400)
        expect(self.page.locator("#pauseLabel")).to_have_text("继续")
        self.page.evaluate("window.testPad.buttons[0].pressed = false")
        self.page.clock.run_for(100)
        self.page.evaluate("window.testPad.buttons[0].pressed = true")
        self.page.clock.run_for(100)
        expect(self.page.locator("#pauseLabel")).to_have_text("暂停")
        self.page.evaluate("window.testPad.buttons[1].pressed = true")
        self.page.clock.run_for(100)
        expect(self.page.locator("#display")).to_be_hidden()

    def test_completion_restart_and_speed_bounds(self):
        self.page.locator("#inputText").fill("你好。")
        self.page.clock.install()
        self.start_without_countdown()
        self.page.clock.run_for(5000)
        expect(self.page.locator("#pauseLabel")).to_have_text("重播")
        stopped_timer = self.page.locator("#timer").inner_text()
        self.page.clock.run_for(2000)
        expect(self.page.locator("#timer")).to_have_text(stopped_timer)
        self.page.locator("#pauseBtn").click()
        expect(self.page.locator("#pauseLabel")).to_have_text("暂停")
        self.page.locator("#pauseBtn").click()
        for _ in range(20):
            self.page.locator("#fasterBtn").click()
        expect(self.page.locator("#playbackSpeed")).to_have_text("100")
        for _ in range(25):
            self.page.locator("#slowerBtn").click()
        expect(self.page.locator("#playbackSpeed")).to_have_text("10")

    def test_touch_and_orientation_preserve_reading_point(self):
        touch_context = self.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        phone = touch_context.new_page()
        phone.on("pageerror", lambda error: self.errors.append(str(error)))
        phone.add_init_script("Element.prototype.requestFullscreen = undefined; Element.prototype.webkitRequestFullscreen = undefined;")
        try:
            phone.goto(BASE_URL, wait_until="networkidle")
            phone.locator('.mobile-tabs [data-panel="settings"]').click()
            phone.locator("#countdownSetting").select_option("0")
            phone.locator("#startBtn").click()
            phone.touchscreen.tap(180, 300)
            expect(phone.locator("#pauseLabel")).to_have_text("继续")
            fraction = """() => {const text = document.getElementById('text'); return (innerHeight / 2 - new DOMMatrix(getComputedStyle(text).transform).m42) / text.offsetHeight;}"""
            before = phone.evaluate(fraction)
            phone.set_viewport_size({"width": 844, "height": 390})
            phone.wait_for_timeout(80)
            after = phone.evaluate(fraction)
            self.assertAlmostEqual(after, before, delta=0.015)
            self.assertLessEqual(phone.evaluate("document.documentElement.scrollWidth"), 844)
            bounds = phone.locator("#controlButtons").bounding_box()
            self.assertGreaterEqual(bounds["x"], 0)
            self.assertLessEqual(bounds["x"] + bounds["width"], 844)
            self.assertLessEqual(bounds["y"] + bounds["height"], 390)
            phone.locator("#exitBtn").click()
            expect(phone.locator("#controls")).to_be_visible()
        finally:
            touch_context.close()

    def test_corrupt_settings_preserve_draft_and_valid_ranges(self):
        self.page.evaluate("""() => {
            localStorage.setItem('savedText', '旧文稿仍然在。');
            localStorage.setItem('flow.teleprompter.settings.v1', JSON.stringify({fontSize: 900, speed: -100, fontFamily: '<script>', mirror: 'true', fontColor: 'broken'}));
        }""")
        self.page.reload()
        expect(self.page.locator("#inputText")).to_have_value("旧文稿仍然在。")
        expect(self.page.locator("#fontSize")).to_have_value("100")
        expect(self.page.locator("#speed")).to_have_value("10")
        expect(self.page.locator("#mirror")).not_to_be_checked()
        expect(self.page.locator("#fontColor")).to_have_value("#f1f5f2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
