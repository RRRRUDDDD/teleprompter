"""Verify the deployed app and its offline behavior in a fresh browser context."""
import json
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

site = 'https://teleprompter.yoshinagakoi.eu.org/'
result = {'url': site, 'checks': []}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.set_default_timeout(20000)
    response = page.goto(site, wait_until='networkidle', timeout=45000)
    result['http'] = response.status
    assert response.status == 200
    page.wait_for_selector('body[data-library-ready="true"]')
    expect(page.locator('#inputText')).to_have_value('')
    expect(page.locator('#sampleBtn, #startHint, #fontSizePanel')).to_have_count(0)
    result['checks'].append('new mobile UI and blank first draft')
    page.locator('#draftTitle').fill('Deployment verification')
    page.locator('#inputText').fill('Offline draft persistence check.')
    page.wait_for_function("document.getElementById('saveLabel').textContent.includes('已自动保存')")
    page.wait_for_function("document.getElementById('offlineStatus').dataset.state === 'ready'", timeout=45000)
    result['checks'].append('service worker cache ready')
    context.set_offline(True)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_selector('body[data-library-ready="true"]')
    expect(page.locator('#draftTitle')).to_have_value('Deployment verification')
    expect(page.locator('#inputText')).to_have_value('Offline draft persistence check.')
    page.locator('#openLibraryBtn').click()
    expect(page.locator('.draft-item')).to_have_count(1)
    expect(page.locator('.draft-open')).to_contain_text('Deployment verification')
    page.locator('#closeLibraryBtn').click()
    result['checks'].append('offline reload retains and opens draft library')
    page.locator('#openSettingsBtn').click()
    page.locator('#countdownSetting').select_option('0')
    page.locator('#doneSettingsBtn').click()
    page.locator('#startBtn').click()
    expect(page.locator('#display')).to_have_attribute('data-state', 'playing')
    expect(page.locator('#largerFontBtn')).to_be_visible()
    page.locator('#exitBtn').click()
    result['checks'].append('offline playback and direct font controls')
    browser.close()
Path(__file__).with_name('live-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
