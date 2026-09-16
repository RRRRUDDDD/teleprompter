import base64, io, json, struct, warnings, zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = "http://127.0.0.1:4175"
WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
STRICT = "http://purl.oclc.org/ooxml/wordprocessingml/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"

def xml(body, namespace=WORD):
    return ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="' + namespace + '" xmlns:mc="' + MC + '"><w:body>' + body + '</w:body></w:document>').encode()

def docx(content, compression=zipfile.ZIP_DEFLATED, extras=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression) as archive:
        archive.writestr("word/document.xml", content)
        for name, payload in extras or []:
            archive.writestr(name, payload)
    return stream.getvalue()

def p(text):
    return '<w:p><w:r><w:t>' + text + '</w:t></w:r></w:p>'

READ = """async ({name, data}) => {
    try {
        const bytes = Uint8Array.from(atob(data), char => char.charCodeAt(0));
        return {text: await FlowDocumentImport.read(new File([bytes], name))};
    } catch (error) { return {error: error.message}; }
}"""
checks = []
def check(page, label, data, name="sample.docx", expected=None, error=None):
    result = page.evaluate(READ, {"name": name, "data": base64.b64encode(data).decode()})
    if expected is not None:
        assert result == {"text": expected}, (label, result, expected[:100])
    else:
        assert "error" in result and error in result["error"], (label, result, error)
        assert "Error" not in result["error"] and "undefined" not in result["error"], result
    checks.append(label)

def bootstrap(browser, file_mode=False):
    page = browser.new_page()
    base = "file:///E:/Downloads/44456654/teleprompter" if file_mode else ROOT
    page.goto(base + "/index.html")
    page.add_script_tag(url=base + "/document-import.js")
    assert page.evaluate("document.characterSet") == "UTF-8"
    return page

with sync_playwright() as playwright:
    for browser_name in ["chromium", "webkit"]:
        browser = getattr(playwright, browser_name).launch()
        page = bootstrap(browser)
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        check(page, browser_name + ": TXT BOM/CRLF", b"\xef\xbb\xbfA\r\nB\rC", "notes.TXT", "A\nB\nC")
        assert not any("/vendor/" in url for url in requests), requests
        check(page, browser_name + ": empty TXT", b" \r\n\t", "empty.txt", error="没有")
        check(page, browser_name + ": invalid UTF8", b"\xff\xff", "bad.txt", error="UTF-8")
        check(page, browser_name + ": old DOC", b"old", "old.DOC", error="另存为 DOCX")
        check(page, browser_name + ": missing extension", b"text", "txt", error="请选择")
        check(page, browser_name + ": TXT 1M characters", b"a" * 1000000, "exact.txt", "a" * 1000000)
        check(page, browser_name + ": TXT result cap", b"a" * 1000001, "large.txt", error="100 万")
        for name, length, needle in [("large.txt", 1024*1024+1, "1 MiB"), ("large.docx", 10*1024*1024+1, "10 MiB")]:
            result = page.evaluate("""async ({name, length}) => {
                try { await FlowDocumentImport.read(new File([new Uint8Array(length)], name)); return 'accepted'; }
                catch (error) { return error.message; }
            }""", {"name": name, "length": length})
            assert needle in result, result
            checks.append(browser_name + ": " + needle + " input cap")
        sample = xml('<w:p><w:r><w:t>第一</w:t><w:br/><w:t>第二</w:t><w:cr/><w:t>第三</w:t><w:tab/><w:t>尾</w:t></w:r></w:p>' +
                     '<w:p><w:hyperlink><w:r><w:t>链接</w:t></w:r></w:hyperlink><w:r><w:instrText>HYPERLINK https://example.invalid</w:instrText></w:r>' +
                     '<w:del><w:r><w:t>删除</w:t></w:r></w:del><w:moveFrom><w:r><w:t>旧位置</w:t></w:r></w:moveFrom>' +
                     '<w:fldSimple w:instr="PAGE"><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p>' +
                     '<w:tbl><w:tr><w:tc>' + p('A1') + p('A2') + '</w:tc><w:tc>' + p('B') + '</w:tc></w:tr>' +
                     '<w:tr><w:tc>' + p('C') + '</w:tc><w:tc>' + p('D') + '</w:tc></w:tr></w:tbl>')
        check(page, browser_name + ": paragraphs/breaks/tables/fields", docx(sample), "sample.DOCX", "第一\n第二\n第三\t尾\n链接1\nA1\nA2\tB\nC\tD")
        assert sum("/vendor/fflate-0.8.3.min.js" in url for url in requests) == 1, requests
        check(page, browser_name + ": strict Word namespace", docx(xml(p("严格"), STRICT)), expected="严格")
        check(page, browser_name + ": stored XML", docx(xml(p("stored")), zipfile.ZIP_STORED), expected="stored")
        check(page, browser_name + ": UTF16 XML", docx(xml(p("Unicode")).decode().replace('encoding="UTF-8"', 'encoding="UTF-16"').encode("utf-16")), expected="Unicode")
        nested = '<w:p><w:r><w:t>Before</w:t></w:r><w:r><w:drawing><w:txbxContent>' + p("Box") + '</w:txbxContent></w:drawing></w:r><w:r><w:t>After</w:t></w:r></w:p>'
        check(page, browser_name + ": nested text box", docx(xml(nested)), expected="Before\nBox\nAfter")
        alternate = '<w:p><mc:AlternateContent><mc:Choice Requires="wps"><w:txbxContent>' + p("Only once") + '</w:txbxContent></mc:Choice><mc:Fallback><w:txbxContent>' + p("Only once") + '</w:txbxContent></mc:Fallback></mc:AlternateContent></w:p>'
        check(page, browser_name + ": alternate text box", docx(xml(alternate)), expected="Only once")
        check(page, browser_name + ": explicit final break", docx(xml('<w:p><w:r><w:t>A</w:t><w:br/></w:r></w:p>')), expected="A\n")
        check(page, browser_name + ": empty paragraphs", docx(xml(p("") + p("A") + p("") + p("B") + p(""))), expected="\nA\n\nB\n")
        check(page, browser_name + ": empty DOCX", docx(xml('<w:p><w:r><w:drawing/></w:r></w:p>')), error="没有")
        check(page, browser_name + ": broken ZIP", b"not a zip", error="损坏")
        check(page, browser_name + ": malformed XML", docx(b"<w:document>"), error="无法解析")
        check(page, browser_name + ": wrong XML root", docx(b"<html><body>not Word</body></html>"), error="无法解析")
        check(page, browser_name + ": nested body invalid", docx(b'<w:document xmlns:w="' + WORD.encode() + b'"><w:p><w:body/></w:p></w:document>'), error="无法解析")
        dtd = b'<!DOCTYPE document [<!ENTITY external SYSTEM "https://example.invalid/private">]>' + xml(p("&external;"))
        check(page, browser_name + ": DTD rejected", docx(dtd), error="无法解析")
        check(page, browser_name + ": markup remains text", docx(xml(p("&lt;script&gt;window.BAD=true&lt;/script&gt;"))), expected="<script>window.BAD=true</script>")
        assert page.evaluate("window.BAD === undefined")
        check(page, browser_name + ": unrelated ZIP member ignored", docx(xml(p("safe")), extras=[("word/media/unused", b"x" * (12*1024*1024))]), expected="safe")
        check(page, browser_name + ": XML pre-expansion cap", docx(xml(p("a" * (8*1024*1024)))), error="8 MiB")
        check(page, browser_name + ": DOCX 1M characters", docx(xml(p("a" * 1000000))), expected="a" * 1000000)
        check(page, browser_name + ": DOCX text cap", docx(xml(p("a" * 1000001))), error="100 万")
        corrupted = bytearray(docx(xml(p("CRC"))))
        central = corrupted.index(b"PK\x01\x02")
        struct.pack_into("<I", corrupted, 14, 123)
        struct.pack_into("<I", corrupted, central + 16, 123)
        check(page, browser_name + ": CRC mismatch", corrupted, error="损坏")
        forged = bytearray(docx(xml(p("x" * (9*1024*1024)))))
        central = forged.index(b"PK\x01\x02")
        struct.pack_into("<I", forged, 22, 64)
        struct.pack_into("<I", forged, central + 24, 64)
        check(page, browser_name + ": forged expansion size", forged, error="损坏")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            duplicate = docx(xml(p("A")), extras=[("word/document.xml", xml(p("B")))])
        check(page, browser_name + ": duplicate document rejected", duplicate, error="损坏")
        encrypted = bytearray(docx(xml(p("locked"))))
        central = encrypted.index(b"PK\x01\x02")
        struct.pack_into("<H", encrypted, 6, 1)
        struct.pack_into("<H", encrypted, central + 8, 1)
        check(page, browser_name + ": encrypted DOCX", encrypted, error="未加密")
        assert not any(url.startswith("https:") for url in requests), requests
        page.close()
        retry = bootstrap(browser)
        retry.route("**/vendor/fflate-0.8.3.min.js", lambda route: route.abort())
        check(retry, browser_name + ": library load failure", docx(xml(p("retry"))), error="加载失败")
        retry.unroute("**/vendor/fflate-0.8.3.min.js")
        check(retry, browser_name + ": library retry", docx(xml(p("retry"))), expected="retry")
        retry.close()
        local = bootstrap(browser, True)
        check(local, browser_name + ": file URL import", docx(xml(p("local"))), expected="local")
        local.close()
        scoped = bootstrap(browser)
        scoped.route("**/preview/nested/document-import.js", lambda route: route.fulfill(path=str(Path("document-import.js").resolve()), content_type="application/javascript; charset=utf-8"))
        scoped.route("**/preview/nested/vendor/fflate-0.8.3.min.js", lambda route: route.fulfill(path=str(Path("vendor/fflate-0.8.3.min.js").resolve()), content_type="application/javascript; charset=utf-8"))
        scoped.add_script_tag(url=ROOT + "/preview/nested/document-import.js")
        scoped.evaluate("""() => { const base = document.createElement('base'); base.href = '/different/base/'; document.head.prepend(base); }""")
        scoped_requests = []
        scoped.on("request", lambda request: scoped_requests.append(request.url))
        check(scoped, browser_name + ": captured Pages subpath", docx(xml(p("subpath"))), expected="subpath")
        assert any("/preview/nested/vendor/" in url for url in scoped_requests), scoped_requests
        scoped.close()
        browser.close()
print(json.dumps({"passed": len(checks), "checks": checks}, ensure_ascii=False))
