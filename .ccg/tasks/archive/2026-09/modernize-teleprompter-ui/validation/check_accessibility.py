"""Check WCAG A/AA rules in the main mobile and desktop states with axe-core."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

output = Path(__file__).resolve().parent
axe_path = Path(os.environ.get("AXE_CORE_PATH", str(Path(os.environ["TEMP"]) / "teleprompter-ui-validation/node_modules/axe-core/axe.min.js")))
url = os.environ.get("TELEPROMPTER_TEST_URL", "http://127.0.0.1:4173")
reports = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for width, height in [(390, 844), (1440, 1080)]:
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        page.add_script_tag(path=str(axe_path))
        states = ["editor", "preview", "settings", "help"] if width < 901 else ["workspace", "help"]
        for state in states:
            if state == "help":
                page.locator("#openModalBtn").click()
            elif width < 901:
                page.locator(f'.mobile-tabs [data-panel="{state}"]').click()
            page.wait_for_timeout(220)
            result = page.evaluate("""async () => {
                const result = await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}});
                return {violations: result.violations, incomplete: result.incomplete.map(item => item.id)};
            }""")
            reports.append({"width": width, "state": state, **result})
        context.close()
    browser.close()
(output / "accessibility-report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
for report in reports:
    for violation in report["violations"]:
        print(f'{report["width"]} {report["state"]}: {violation["id"]} ({violation["impact"]})')
        for node in violation["nodes"]:
            print(json.dumps({"target": node["target"], "summary": node.get("failureSummary", "")}, ensure_ascii=False))
print(f'{len(reports)} states checked; {sum(len(report["violations"]) for report in reports)} rule violations.')
raise SystemExit(1 if any(report["violations"] for report in reports) else 0)
