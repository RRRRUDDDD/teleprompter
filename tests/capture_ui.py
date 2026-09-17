"""Capture review evidence under tests/artifacts; uses verify_ui.py's URL/browser overrides."""

import json

from playwright.sync_api import expect, sync_playwright

from verify_ui import ARTIFACTS, BASE_URL, BROWSER, NO_FULLSCREEN


def main():
    output = ARTIFACTS / BROWSER
    output.mkdir(parents=True, exist_ok=True)
    report = {"browser": BROWSER, "url": BASE_URL, "screenshots": [], "browser_errors": []}

    def attach(page):
        page.on("pageerror", lambda error: report["browser_errors"].append(str(error)))
        page.on("console", lambda message: report["browser_errors"].append(message.text) if message.type == "error" else None)

    def capture(page, name, full_page=False):
        page.screenshot(path=str(output / f"{name}.png"), full_page=full_page, animations="disabled")
        report["screenshots"].append({
            "file": f"{name}.png",
            "viewport": page.viewport_size,
            "scroll_width": page.evaluate("document.documentElement.scrollWidth"),
            "state": page.locator("#display").get_attribute("data-state"),
        })

    with sync_playwright() as playwright:
        browser = getattr(playwright, BROWSER).launch(headless=True)
        with browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1) as desktop:
            desktop.add_init_script(NO_FULLSCREEN)
            page = desktop.new_page()
            attach(page)
            page.goto(BASE_URL, wait_until="networkidle")
            capture(page, "desktop", full_page=True)
            page.locator("#openSettingsBtn").click()
            capture(page, "desktop-settings")

        with browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2) as mobile:
            mobile.add_init_script(NO_FULLSCREEN)
            phone = mobile.new_page()
            attach(phone)
            phone.goto(BASE_URL, wait_until="networkidle")
            capture(phone, "mobile-editor")
            phone.locator("#openSettingsBtn").click()
            capture(phone, "mobile-settings")
            phone.locator("#refLineWidth").scroll_into_view_if_needed()
            capture(phone, "mobile-settings-bottom")
            phone.locator("#countdownSetting").select_option("0")
            phone.locator("#doneSettingsBtn").click()
            phone.clock.install()
            phone.locator("#startBtn").click()
            phone.clock.run_for(1800)
            phone.touchscreen.tap(175, 245)
            expect(phone.locator("#display")).to_have_attribute("data-state", "paused")
            capture(phone, "mobile-player")
            phone.locator("#fontSizeBtn").click()
            capture(phone, "mobile-font-controls")
            phone.set_viewport_size({"width": 844, "height": 390})
            phone.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            capture(phone, "mobile-font-controls-landscape")
            phone.locator("#closeFontSizeBtn").click()
            capture(phone, "mobile-player-landscape")
            phone.locator("#exitBtn").click()
            phone.locator("#openSettingsBtn").click()
            capture(phone, "mobile-settings-landscape")
            phone.locator("#doneSettingsBtn").click()
            phone.set_viewport_size({"width": 320, "height": 568})
            phone.reload(wait_until="networkidle")
            capture(phone, "narrow-editor")
            phone.locator("#openSettingsBtn").click()
            capture(phone, "narrow-settings")
            phone.locator("#doneSettingsBtn").click()
            phone.locator("#startBtn").click()
            phone.touchscreen.tap(145, 170)
            phone.locator("#fontSizeBtn").click()
            capture(phone, "narrow-font-controls")
        browser.close()

    (output / "capture-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"browser": BROWSER, "screenshots": len(report["screenshots"]), "browser_errors": report["browser_errors"]}, ensure_ascii=False))
    if report["browser_errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
