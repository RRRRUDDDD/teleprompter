"""Check the editor, settings dialog, reader and font panel with local axe-core."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


OUTPUT = Path(__file__).resolve().parent
AXE_PATH = Path(os.environ.get("AXE_CORE_PATH", str(Path(os.environ["TEMP"]) / "teleprompter-ui-validation/node_modules/axe-core/axe.min.js")))
URL = os.environ.get("TELEPROMPTER_TEST_URL", "http://127.0.0.1:4175")
reports = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for width, height in [(320, 568), (390, 844), (1440, 1000)]:
        context = browser.new_context(viewport={"width": width, "height": height})
        context.add_init_script("Element.prototype.requestFullscreen = undefined; Element.prototype.webkitRequestFullscreen = undefined;")
        page = context.new_page()
        page.goto(URL, wait_until="networkidle")
        page.add_script_tag(path=str(AXE_PATH))
        for state in ["editor", "settings", "reader", "font-panel"]:
            if state == "settings":
                page.locator("#openSettingsBtn").click()
            elif state == "reader":
                page.locator("#countdownSetting").select_option("0")
                page.locator("#doneSettingsBtn").click()
                page.locator("#startBtn").click()
                page.locator("#readerViewport").click(position={"x": width / 2, "y": height / 3})
            elif state == "font-panel":
                page.locator("#fontSizeBtn").click()
            result = page.evaluate("""async () => {
                const result = await axe.run(document, {
                    runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}
                });
                return {violations: result.violations, incomplete: result.incomplete.map(item => item.id)};
            }""")
            reports.append({"width": width, "height": height, "state": state, **result})
        context.close()
    browser.close()

(OUTPUT / "accessibility-report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
for report in reports:
    for violation in report["violations"]:
        print(f'{report["width"]} {report["state"]}: {violation["id"]} ({violation["impact"]})')
        for node in violation["nodes"]:
            print(json.dumps({"target": node["target"], "summary": node.get("failureSummary", "")}, ensure_ascii=False))
print(f'{len(reports)} states checked; {sum(len(report["violations"]) for report in reports)} rule violations.')
raise SystemExit(1 if any(report["violations"] for report in reports) else 0)
