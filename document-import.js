(() => {
    'use strict';

    const MAX_TXT_BYTES = 1024 * 1024;
    const MAX_DOCX_BYTES = 10 * 1024 * 1024;
    const MAX_XML_BYTES = 8 * 1024 * 1024;
    const MAX_TEXT_LENGTH = 1000000;
    const DOCUMENT_PATH = 'word/document.xml';
    const WORD_NAMESPACES = new Set([
        'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'http://purl.oclc.org/ooxml/wordprocessingml/main',
    ]);
    const COMPATIBILITY_NAMESPACE = 'http://schemas.openxmlformats.org/markup-compatibility/2006';
    const libraryUrl = new URL('vendor/fflate-0.8.3.min.js', document.currentScript?.src || document.baseURI).href;
    const messages = {
        unsupported: '请选择 TXT 或 DOCX 文件。',
        legacy: '暂不支持旧版 DOC，请在 Word 中另存为 DOCX 后导入。',
        txtSize: 'TXT 文件不能超过 1 MiB。',
        docxSize: 'DOCX 文件不能超过 10 MiB。',
        xmlSize: 'DOCX 正文不能超过 8 MiB，请拆分后导入。',
        textSize: '文稿超过 100 万字符，请拆分后导入。',
        empty: '文件中没有可导入的文字。',
        read: '无法读取文件，请重新选择后重试。',
        encoding: 'TXT 编码无法识别，请另存为 UTF-8 后导入。',
        zip: 'DOCX 文件已损坏，请重新保存后导入。',
        format: '此 DOCX 格式暂不支持，请另存为未加密的 DOCX 后导入。',
        xml: 'DOCX 正文无法解析，请重新保存后导入。',
        missing: '未找到 DOCX 正文，请确认文件有效。',
        library: '导入组件加载失败，请重试。',
        failed: '文件导入失败，请检查文件后重试。',
    };
    let libraryPromise = null;
    let crcTable = null;

    class ImportError extends Error {}

    function fail(reason) {
        throw new ImportError(messages[reason]);
    }

    function loadZipLibrary() {
        if (!libraryPromise) {
            libraryPromise = new Promise((resolve, reject) => {
                const script = document.createElement('script');
                const finish = (success) => {
                    clearTimeout(timeout);
                    script.onload = null;
                    script.onerror = null;
                    if (success && typeof window.fflate?.Inflate === 'function') {
                        resolve(window.fflate);
                    } else {
                        script.remove();
                        reject(new ImportError(messages.library));
                    }
                };
                const timeout = setTimeout(() => finish(false), 15000);
                script.src = libraryUrl;
                script.async = true;
                script.onload = () => finish(true);
                script.onerror = () => finish(false);
                document.head.appendChild(script);
            }).catch(() => {
                libraryPromise = null;
                fail('library');
            });
        }
        return libraryPromise;
    }

    function normalizeText(value) {
        const text = value.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
        if (text.length > MAX_TEXT_LENGTH) fail('textSize');
        if (!text.trim()) fail('empty');
        return text;
    }

    function decode(bytes, encoding, error) {
        try {
            return new TextDecoder(encoding, { fatal: true }).decode(bytes);
        } catch {
            fail(error);
        }
    }

    // Check ZIP metadata before inflating. Only the main document is ever expanded.
    function inspectArchive(bytes) {
        const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        const u16 = (offset) => view.getUint16(offset, true);
        const u32 = (offset) => view.getUint32(offset, true);
        const matchesName = (offset, length) => length === DOCUMENT_PATH.length &&
            [...DOCUMENT_PATH].every((char, index) => bytes[offset + index] === char.charCodeAt(0));
        let end = bytes.length - 22;
        const earliestEnd = Math.max(0, end - 65535);
        for (; end >= earliestEnd; end--) {
            if (u32(end) === 0x06054b50 && end + 22 + u16(end + 20) === bytes.length) break;
        }
        if (end < earliestEnd) fail('zip');
        const count = u16(end + 10);
        const directorySize = u32(end + 12);
        const directoryOffset = u32(end + 16);
        if (u16(end + 4) || u16(end + 6) || u16(end + 8) !== count || count === 0xffff ||
            directorySize === 0xffffffff || directoryOffset === 0xffffffff ||
            (end >= 20 && u32(end - 20) === 0x07064b50)) fail('format');
        if (directoryOffset + directorySize !== end) fail('zip');

        let offset = directoryOffset;
        let entry = null;
        for (let index = 0; index < count; index++) {
            if (offset + 46 > end || u32(offset) !== 0x02014b50) fail('zip');
            const nameLength = u16(offset + 28);
            const next = offset + 46 + nameLength + u16(offset + 30) + u16(offset + 32);
            if (next > end) fail('zip');
            if (matchesName(offset + 46, nameLength)) {
                if (entry) fail('zip');
                const flags = u16(offset + 8);
                const method = u16(offset + 10);
                const size = u32(offset + 20);
                const originalSize = u32(offset + 24);
                const localOffset = u32(offset + 42);
                if ((flags & 0x41) || u16(offset + 34) || ![0, 8].includes(method) ||
                    size === 0xffffffff || originalSize === 0xffffffff || localOffset === 0xffffffff) fail('format');
                if (originalSize > MAX_XML_BYTES) fail('xmlSize');
                if (localOffset + 30 > directoryOffset || u32(localOffset) !== 0x04034b50) fail('zip');
                const localNameLength = u16(localOffset + 26);
                const dataOffset = localOffset + 30 + localNameLength + u16(localOffset + 28);
                if (dataOffset + size > directoryOffset || !matchesName(localOffset + 30, localNameLength) ||
                    u16(localOffset + 6) !== flags || u16(localOffset + 8) !== method ||
                    (method === 0 && size !== originalSize)) fail('zip');
                const crc = u32(offset + 16);
                if (!(flags & 8) && (u32(localOffset + 14) !== crc ||
                    ![size, 0xffffffff].includes(u32(localOffset + 18)) ||
                    ![originalSize, 0xffffffff].includes(u32(localOffset + 22)))) fail('zip');
                entry = { dataOffset, size, originalSize, method, crc };
            }
            offset = next;
        }
        if (offset !== end) fail('zip');
        if (!entry) fail('missing');
        return entry;
    }

    function checksum(bytes) {
        if (!crcTable) {
            crcTable = Uint32Array.from({ length: 256 }, (_, value) => {
                for (let bit = 0; bit < 8; bit++) value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);
                return value >>> 0;
            });
        }
        let crc = 0xffffffff;
        for (const byte of bytes) crc = (crc >>> 8) ^ crcTable[(crc ^ byte) & 255];
        return (crc ^ 0xffffffff) >>> 0;
    }

    async function extractXml(bytes, entry, library) {
        const compressed = bytes.subarray(entry.dataOffset, entry.dataOffset + entry.size);
        let result = compressed;
        if (entry.method === 8) {
            const chunks = [];
            let length = 0;
            const inflater = new library.Inflate((chunk) => {
                length += chunk.length;
                if (length > MAX_XML_BYTES) fail('xmlSize');
                if (length > entry.originalSize) fail('zip');
                chunks.push(chunk);
            });
            try {
                // Small compressed chunks bound temporary expansion even for forged ZIP sizes.
                for (let offset = 0; offset < compressed.length; offset += 4096) {
                    const end = Math.min(offset + 4096, compressed.length);
                    inflater.push(compressed.subarray(offset, end), end === compressed.length);
                    if (end < compressed.length) await new Promise((resolve) => setTimeout(resolve, 0));
                }
            } catch (error) {
                if (error instanceof ImportError) throw error;
                fail('zip');
            }
            if (length !== entry.originalSize) fail('zip');
            result = new Uint8Array(length);
            let offset = 0;
            for (const chunk of chunks) {
                result.set(chunk, offset);
                offset += chunk.length;
            }
        }
        if (result.length !== entry.originalSize || checksum(result) !== entry.crc) fail('zip');
        return result;
    }

    function extractText(bytes) {
        let encoding = 'utf-8';
        if ((bytes[0] === 0xff && bytes[1] === 0xfe) || (bytes[0] === 0x3c && bytes[1] === 0)) encoding = 'utf-16le';
        if ((bytes[0] === 0xfe && bytes[1] === 0xff) || (bytes[0] === 0 && bytes[1] === 0x3c)) encoding = 'utf-16be';
        const xml = decode(bytes, encoding, 'xml');
        if (/<!DOCTYPE|<!ENTITY/i.test(xml)) fail('xml');
        const parsed = new DOMParser().parseFromString(xml, 'application/xml');
        const root = parsed.documentElement;
        if (!root || root.localName !== 'document' || !WORD_NAMESPACES.has(root.namespaceURI) ||
            parsed.getElementsByTagNameNS('*', 'parsererror').length) fail('xml');
        const namespace = root.namespaceURI;
        const bodies = Array.from(root.children).filter((node) => node.namespaceURI === namespace && node.localName === 'body');
        if (bodies.length !== 1) fail('xml');

        const parts = [];
        const paragraphs = [];
        const skipped = new Set(['del', 'moveFrom', 'instrText', 'delInstrText', 'delText', 'pPr', 'rPr', 'tblPr', 'trPr', 'tcPr', 'sectPr']);
        let length = 0;
        const last = () => parts[parts.length - 1];
        const append = (value, kind = 'text') => {
            if (!value) return;
            length += value.length;
            // One final structural separator is removed before returning the text.
            if (length > MAX_TEXT_LENGTH + 1) fail('textSize');
            parts.push({ value, kind });
        };
        const removeSeparator = (kinds) => {
            if (last() && kinds.includes(last().kind)) length -= parts.pop().value.length;
        };
        function walk(node) {
            const name = node.namespaceURI === namespace ? node.localName : '';
            if (skipped.has(name)) return;
            if (name === 't') { append(node.textContent); return; }
            if (name === 'noBreakHyphen') { append('\u2011'); return; }
            if (name === 'br' || name === 'cr') { append('\n'); return; }
            if (name === 'tab') { append('\t'); return; }
            if (node.namespaceURI === COMPATIBILITY_NAMESPACE && node.localName === 'AlternateContent') {
                // Word often repeats text boxes in Choice and Fallback representations.
                const branches = Array.from(node.children).filter((child) => child.namespaceURI === COMPATIBILITY_NAMESPACE);
                const branch = branches.find((child) => child.localName === 'Choice') || branches.find((child) => child.localName === 'Fallback');
                if (branch) walk(branch);
                return;
            }
            if (name === 'p') {
                if (paragraphs.length) {
                    paragraphs[paragraphs.length - 1].nested = true;
                    if (last()?.kind === 'text' && !last().value.endsWith('\n')) append('\n', 'paragraph');
                }
                paragraphs.push({ nested: false });
            }
            for (let child = node.firstElementChild; child; child = child.nextElementSibling) walk(child);
            if (name === 'p') {
                const paragraph = paragraphs.pop();
                if (!paragraph.nested || !last() || last().kind === 'text') append('\n', 'paragraph');
            } else if (name === 'tc') {
                removeSeparator(['paragraph', 'row']);
                append('\t', 'cell');
            } else if (name === 'tr') {
                removeSeparator(['cell']);
                append('\n', 'row');
            }
        }
        walk(bodies[0]);
        removeSeparator(['paragraph', 'row']);
        return normalizeText(parts.map((part) => part.value).join(''));
    }

    async function read(file) {
        try {
            if (!file || typeof file.name !== 'string' || typeof file.arrayBuffer !== 'function' ||
                !Number.isSafeInteger(file.size) || file.size < 0) fail('read');
            const extension = file.name.match(/\.([^.]+)$/)?.[1].toLowerCase();
            if (extension === 'doc') fail('legacy');
            if (!['txt', 'docx'].includes(extension)) fail('unsupported');
            if (file.size > (extension === 'txt' ? MAX_TXT_BYTES : MAX_DOCX_BYTES)) fail(extension === 'txt' ? 'txtSize' : 'docxSize');
            if (!file.size) fail('empty');
            let bytes;
            try {
                bytes = new Uint8Array(await file.arrayBuffer());
            } catch {
                fail('read');
            }
            if (bytes.length !== file.size) fail('read');
            if (extension === 'txt') return normalizeText(decode(bytes, 'utf-8', 'encoding'));
            const entry = inspectArchive(bytes);
            const library = await loadZipLibrary();
            return extractText(await extractXml(bytes, entry, library));
        } catch (error) {
            throw new Error(error instanceof ImportError ? error.message : messages.failed);
        }
    }

    window.FlowDocumentImport = Object.freeze({ read });
})();
