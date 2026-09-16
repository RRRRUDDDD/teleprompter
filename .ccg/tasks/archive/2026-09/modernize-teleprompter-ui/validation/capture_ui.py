"""Capture desktop and mobile proof of the responsive UI."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

output = Path(__file__).resolve().parent
url = os.environ.get("TELEPROMPTER_TEST_URL", "http://127.0.0.1:4173")
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.goto(url, wait_until="networkidle")
    page.screenshot(path=str(output / "desktop.png"), full_page=True)
    mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
    phone = mobile.new_page()
    phone.add_init_script("Element.prototype.requestFullscreen = undefined; Element.prototype.webkitRequestFullscreen = undefined;")
    phone.on("pageerror", lambda error: errors.append(str(error)))
    phone.goto(url, wait_until="networkidle")
    for panel in ["editor", "preview", "settings"]:
        phone.locator(f'.mobile-tabs [data-panel="{panel}"]').click()
        phone.screenshot(path=str(output / f"mobile-{panel}.png"), animations="disabled")
        if panel == "settings":
            phone.locator("#refLineWidth").scroll_into_view_if_needed()
            phone.screenshot(path=str(output / "mobile-settings-bottom.png"), animations="disabled")
            phone.evaluate("window.scrollTo(0, 0)")
    phone.locator("#countdownSetting").select_option("0")
    phone.locator("#startBtn").click()
    phone.locator("#pauseBtn").click()
    phone.screenshot(path=str(output / "mobile-player.png"))
    phone.set_viewport_size({"width": 844, "height": 390})
    phone.screenshot(path=str(output / "mobile-player-landscape.png"))
    (output / "browser-errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"screenshots": 7, "browser_errors": errors}, ensure_ascii=False))
    browser.close()
