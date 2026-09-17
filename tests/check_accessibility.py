"""Verify accessible names, semantics and contrast for mobile/desktop UI states."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

url = os.environ.get('TELEPROMPTER_TEST_URL', 'http://127.0.0.1:4175')
axe_path = Path(os.environ.get('AXE_CORE_PATH', str(Path(os.environ.get('TEMP', '/tmp')) / 'teleprompter-ui-validation/node_modules/axe-core/axe.min.js')))
results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for width, height in [(390, 844), (1440, 1000)]:
        context = browser.new_context(viewport={'width': width, 'height': height}, service_workers='block')
        page = context.new_page()
        page.goto(url, wait_until='networkidle')
        page.wait_for_selector('body[data-library-ready="true"]')
        page.add_script_tag(path=str(axe_path))
        page.locator('#draftTitle').fill('周末分享')
        page.locator('#inputText').fill('从准备好的一份文稿，开始下一次分享。')
        for state in ['editor', 'library', 'library-delete', 'settings']:
            if state == 'library':
                page.locator('#openLibraryBtn').click()
            elif state == 'library-delete':
                page.locator('.draft-delete').first.click()
                page.locator('#undoDeleteBtn').wait_for()
            elif state == 'settings':
                page.locator('#closeLibraryBtn').click()
                page.locator('#openSettingsBtn').click()
            report = page.evaluate('''async () => {
                const report = await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}});
                return {violations: report.violations, incomplete: report.incomplete.map(item => item.id)};
            }''')
            results.append({'width': width, 'state': state, **report})
        context.close()
    browser.close()
output = Path(__file__).resolve().parent / 'artifacts/accessibility-report.json'
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
for result in results:
    for violation in result['violations']:
        print(result['width'], result['state'], violation['id'])
        for node in violation['nodes']:
            print(node['target'], node.get('failureSummary', ''))
print(f"{len(results)} states; {sum(len(item['violations']) for item in results)} rule violations")
raise SystemExit(1 if any(result['violations'] for result in results) else 0)
