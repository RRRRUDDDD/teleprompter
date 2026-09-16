import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.webkit.launch(headless=True)
    page = browser.new_page()
    page.goto('http://127.0.0.1:4173', wait_until='networkidle')
    probe = "el => ({type: el.type, attribute: el.getAttribute('type'), value: el.value, valid: el.validity.valid})"
    print('before:', json.dumps(page.locator('#fontColor').evaluate(probe)))
    page.locator('#fontColor').evaluate("el => {el.value = '#ffee00'; el.dispatchEvent(new Event('input', {bubbles: true}));}")
    print('after input:', json.dumps(page.locator('#fontColor').evaluate(probe)))
    print('preview:', page.locator('#previewText').evaluate('el => el.style.color'))
    page.locator('#fontColor').evaluate("el => el.dispatchEvent(new Event('change', {bubbles: true}))")
    print('after change:', json.dumps(page.locator('#fontColor').evaluate(probe)))
    print('preview:', page.locator('#previewText').evaluate('el => el.style.color'))
    browser.close()
