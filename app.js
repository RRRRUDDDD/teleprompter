(() => {
    'use strict';

    const $ = (id) => document.getElementById(id);
    const SETTINGS_KEY = 'flow.teleprompter.settings.v1';
    const mobileLayout = window.matchMedia('(max-width: 900px)');
    const themeColor = document.querySelector('meta[name="theme-color"]');
    const editorThemeColor = themeColor?.content;
    const defaults = {
        fontFamily: $('fontFamily').options[0].value,
        fontSize: mobileLayout.matches ? 36 : 48,
        speed: 40,
        fontColor: '#f1f5f2',
        bgColor: '#17201c',
        refLineColor: '#79bc9c',
        refLineWidth: 1,
        mirror: false,
        showTimer: true,
        countdownSetting: 5,
    };
    const numericBounds = { fontSize: [10, 100], speed: [10, 100], refLineWidth: [0, 7] };
    const fontOptions = Array.from($('fontFamily').options, (option) => option.value);
    let settings = { ...defaults };
    let mode = 'editor';
    let sessionToken = 0;
    let toastTimeout = 0;
    let wakeLock = null;
    let wakeRequestPending = false;
    let fullscreenExit = null;
    let resizeFrame = 0;
    let draftRevision = 0;
    let importToken = 0;
    let importBusy = false;
    let settingsBackdropDown = false;
    let library = null;
    let libraryBusy = false;
    let libraryReady = false;
    let deletedDraft = null;
    let libraryFocusTarget = 'openLibraryBtn';
    let libraryFocusPending = false;
    const viewportState = { width: window.innerWidth, height: window.innerHeight, keyboardClosing: false };
    const session = {
        frame: 0, countdownInterval: 0, remaining: 0, elapsed: 0,
        y: 0, startY: 0, lastTimestamp: 0, textHeight: 0, viewportHeight: 0, travel: 1,
        drag: null, nativeFullscreen: false, previousScroll: 0,
        previousButtons: [], nextGamepadMove: 0, nextGamepadSpeed: 0,
    };
    const active = () => mode !== 'editor';
    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    const formatTime = (seconds) => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;

    function readStorage(key) {
        try { return localStorage.getItem(key); } catch { return null; }
    }

    function writeStorage(key, value) {
        try {
            localStorage.setItem(key, value);
            return true;
        } catch {
            showToast('设置未能保存，当前会话仍可使用');
            return false;
        }
    }

    function normalizeSetting(name, value, fallback = defaults[name]) {
        const number = typeof value === 'number' || (typeof value === 'string' && value.trim() !== '')
            ? Number(value) : NaN;
        if (name in numericBounds) {
            return Number.isFinite(number) ? clamp(Math.round(number), ...numericBounds[name]) : fallback;
        }
        if (name === 'countdownSetting') return [0, 3, 5, 10].includes(number) ? number : fallback;
        if (name === 'fontFamily') return fontOptions.includes(value) ? value : fallback;
        if (name === 'mirror' || name === 'showTimer') return typeof value === 'boolean' ? value : fallback;
        return typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : fallback;
    }

    function saveSettings() {
        writeStorage(SETTINGS_KEY, JSON.stringify(settings));
    }

    function updateRange(name, id = `${name}Range`) {
        const range = $(id);
        range.value = settings[name];
        const [min, max] = numericBounds[name];
        range.style.setProperty('--range-progress', `${(settings[name] - min) / (max - min) * 100}%`);
    }

    function applySettings(remeasure = false) {
        for (const name of Object.keys(defaults)) {
            const input = $(name);
            if (typeof defaults[name] === 'boolean') input.checked = settings[name];
            else input.value = settings[name];
        }
        updateRange('fontSize');
        updateRange('speed');
        $('playerFontSizeValue').textContent = settings.fontSize;
        $('smallerFontBtn').disabled = settings.fontSize <= numericBounds.fontSize[0];
        $('largerFontBtn').disabled = settings.fontSize >= numericBounds.fontSize[1];
        $('fontColorValue').textContent = settings.fontColor.toUpperCase();
        $('bgColorValue').textContent = settings.bgColor.toUpperCase();
        $('display').style.setProperty('--stage-bg', settings.bgColor);
        $('text').style.fontFamily = settings.fontFamily;
        $('text').style.fontSize = `${settings.fontSize}px`;
        $('text').style.color = settings.fontColor;
        $('readerMirror').style.transform = settings.mirror ? 'scaleX(-1)' : 'none';
        $('referenceLine').style.setProperty('--guide-color', settings.refLineColor);
        $('referenceLine').style.borderTopWidth = `${settings.refLineWidth}px`;
        $('referenceLine').hidden = settings.refLineWidth === 0 || !$('inputText').value.trim();
        $('timer').hidden = !settings.showTimer;
        $('playbackSpeed').textContent = settings.speed;
        if (active()) {
            if (themeColor) themeColor.content = settings.bgColor;
            if (remeasure) measureReader();
        }
    }

    function changeSetting(name, value) {
        settings[name] = normalizeSetting(name, value, settings[name]);
        applySettings(name === 'fontSize' || name === 'fontFamily');
        saveSettings();
    }

    function updateDraftControls() {
        $('startBtn').disabled = !libraryReady || libraryBusy || importBusy || !$('inputText').value.trim();
        $('clearBtn').disabled = !libraryReady || libraryBusy || !$('inputText').value;
        $('importBtn').disabled = !libraryReady || libraryBusy || importBusy;
        $('openLibraryBtn').disabled = !libraryReady || libraryBusy;
        $('inputText').disabled = !libraryReady || libraryBusy;
        $('draftTitle').disabled = !libraryReady || libraryBusy;
    }

    function updateDocument(save = true) {
        const value = $('inputText').value;
        const count = Array.from(value.replace(/\s/g, '')).length;
        $('wordCount').textContent = count;
        $('readTime').textContent = formatTime(Math.ceil(count / 4));
        updateDraftControls();
        if (save && library) library.update({ title: $('draftTitle').value, text: value });
        if (library) $('draftCount').textContent = library.list().length;
        applySettings();
    }

    function showToast(message, undo) {
        clearTimeout(toastTimeout);
        $('toastMessage').textContent = message;
        $('toastAction').hidden = !undo;
        $('toastAction').onclick = undo ? () => {
            clearTimeout(toastTimeout);
            $('toast').hidden = true;
            $('toastAction').onclick = null;
            undo();
        } : null;
        $('toast').hidden = false;
        const dismiss = () => {
            if ($('toast').contains(document.activeElement)) toastTimeout = setTimeout(dismiss, 2000);
            else $('toast').hidden = true;
        };
        toastTimeout = setTimeout(dismiss, 6500);
    }

    function replaceDraft(value, message, title = $('draftTitle').value) {
        const previous = $('inputText').value;
        const previousTitle = $('draftTitle').value;
        const draftId = library?.active?.id;
        const revision = ++draftRevision;
        $('inputText').value = value;
        $('draftTitle').value = title;
        updateDocument();
        showToast(message, () => {
            if (draftRevision !== revision || library?.active?.id !== draftId) return showToast('已保留当前文稿，未覆盖后续修改');
            ++draftRevision;
            $('inputText').value = previous;
            $('draftTitle').value = previousTitle;
            updateDocument();
            $('inputText').focus({ preventScroll: true });
        });
    }

    function setImportBusy(busy) {
        importBusy = busy;
        $('importBtn').setAttribute('aria-busy', String(busy));
        $('importBtn').setAttribute('aria-label', busy ? '正在导入文件' : '导入文件');
        $('importBtn').title = busy ? '正在导入文件…' : '导入 TXT / DOCX 文件';
        updateDraftControls();
    }

    function updateLibraryStatus({ state, reason }) {
        const labels = { saving: '正在保存…', saved: '已自动保存', unavailable: '未能保存，请保留文稿' };
        $('saveLabel').textContent = reason === 'conflict' ? '其他窗口已修改，当前内容未保存' : labels[state] || labels.unavailable;
        $('saveStatus').classList.toggle('unsaved', state === 'unavailable');
        $('libraryStorageStatus').textContent = reason === 'conflict' ? '请先复制当前内容，再刷新读取其他窗口的版本' : state === 'unavailable' ? '当前仅保留在此会话，请勿关闭页面' : '仅保存在此设备';
    }

    async function initializeLibrary(legacyText) {
        library = await window.FlowScriptLibrary.open({ legacyText, onStatus: updateLibraryStatus });
        libraryReady = true;
        loadActiveDraft();
        document.body.dataset.libraryReady = 'true';
    }

    function loadActiveDraft() {
        const draft = library.active;
        $('draftTitle').value = draft?.title || '';
        $('inputText').value = draft?.text || '';
        updateDocument(false);
    }

    function createIcon(name) {
        const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
        icon.classList.add('icon');
        icon.setAttribute('aria-hidden', 'true');
        use.setAttribute('href', `#${name}`);
        icon.append(use);
        return icon;
    }

    function renderLibrary() {
        if (!library) return;
        const query = $('librarySearch').value.trim().toLocaleLowerCase();
        const drafts = library.list().filter((draft) => !query || `${draft.title}\n${draft.text}`.toLocaleLowerCase().includes(query))
            .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
        const fragment = document.createDocumentFragment();
        for (const draft of drafts) {
            const title = draft.title.trim() || '未命名文稿';
            const row = document.createElement('li');
            row.className = 'draft-item';
            row.dataset.draftId = draft.id;
            const selected = draft.id === library.active?.id;
            row.classList.toggle('is-current', selected);
            const open = document.createElement('button');
            open.type = 'button';
            open.className = 'draft-open';
            open.disabled = libraryBusy;
            open.setAttribute('aria-current', String(selected));
            open.setAttribute('aria-label', `打开文稿：${title}${selected ? '，当前文稿' : ''}`);
            const copy = document.createElement('span');
            copy.className = 'draft-summary';
            const heading = document.createElement('strong');
            heading.textContent = title;
            const excerpt = document.createElement('span');
            excerpt.className = 'draft-excerpt';
            excerpt.textContent = draft.text.slice(0, 180).replace(/\s+/g, ' ').trim() || '还没有正文，写下第一句话吧。';
            const meta = document.createElement('small');
            meta.textContent = `${selected ? '当前文稿 · ' : ''}${new Date(draft.updatedAt).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })}`;
            copy.append(heading, excerpt, meta);
            open.append(createIcon('i-file'), copy);
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'icon-button quiet-danger draft-delete';
            remove.disabled = libraryBusy;
            remove.setAttribute('aria-label', `删除文稿：${title}`);
            remove.title = `删除文稿：${title}`;
            remove.append(createIcon('i-trash'));
            row.append(open, remove);
            fragment.append(row);
        }
        $('draftList').replaceChildren(fragment);
        $('libraryEmpty').hidden = drafts.length > 0;
        $('draftCount').textContent = library.list().length;
        $('newDraftBtn').disabled = libraryBusy;
        $('undoDeleteBtn').disabled = libraryBusy || !deletedDraft;
    }

    async function changeLibrary(operation) {
        if (!libraryReady || libraryBusy || active()) return;
        libraryBusy = true;
        ++draftRevision;
        ++importToken;
        setImportBusy(false);
        renderLibrary();
        try {
            await library.flush();
            await operation();
            loadActiveDraft();
        } finally {
            libraryBusy = false;
            updateDraftControls();
            renderLibrary();
            if (libraryFocusPending) restoreLibraryFocus();
        }
    }

    function restoreLibraryFocus() {
        if (active() || $('libraryDialog').open) return;
        if (libraryBusy) {
            libraryFocusPending = true;
            return;
        }
        libraryFocusPending = false;
        $(libraryFocusTarget).focus({ preventScroll: true });
        libraryFocusTarget = 'openLibraryBtn';
    }

    function renderPlaybackState() {
        const labels = { countdown: '准备开始', playing: '正在提词', paused: '已暂停', finished: '本次已完成' };
        const tips = {
            countdown: '深呼吸，准备开口',
            playing: '轻点画面暂停 · 上下拖动调整位置',
            paused: '轻点画面继续 · 上下拖动调整位置',
            finished: '轻点画面重播 · 或返回编辑文稿',
        };
        $('display').dataset.state = mode;
        $('playbackStatus').textContent = labels[mode] || '';
        $('playerTip').textContent = tips[mode] || '';
        $('restartBtn').disabled = mode === 'countdown';
        $('readerViewport').setAttribute('aria-disabled', String(mode === 'countdown'));
        $('readerViewport').setAttribute('aria-label', mode === 'finished' ? '文稿已完成，轻点重播' :
            mode === 'paused' ? '轻点继续提词，上下拖动调整位置' :
            mode === 'countdown' ? '即将开始提词' : '轻点暂停提词，上下拖动调整位置');
    }

    function readingFraction() {
        return (session.startY - session.y) / session.travel;
    }

    function renderPosition() {
        $('text').style.transform = `translateY(${session.y}px)`;
        const progress = clamp(readingFraction(), 0, 1);
        $('progressFill').style.transform = `scaleX(${progress})`;
        const percent = String(Math.round(progress * 100));
        if ($('readingProgress').getAttribute('aria-valuenow') !== percent) $('readingProgress').setAttribute('aria-valuenow', percent);
    }

    function cancelReaderDrag() {
        const drag = session.drag;
        session.drag = null;
        if (drag && $('readerViewport').hasPointerCapture(drag.id)) $('readerViewport').releasePointerCapture(drag.id);
    }

    function measureReader(preserveProgress = true) {
        // Keep the same fraction of the reading journey even when line wrapping changes.
        const fraction = preserveProgress ? readingFraction() : 0;
        session.viewportHeight = $('display').clientHeight;
        session.textHeight = $('text').offsetHeight;
        session.startY = session.viewportHeight / 2 - settings.fontSize * .85;
        session.travel = Math.max(1, session.textHeight - settings.fontSize * .85);
        session.y = session.startY - fraction * session.travel;
        cancelReaderDrag();
        renderPosition();
    }

    function resetReaderPosition() {
        session.elapsed = 0;
        $('timer').textContent = '00:00';
        measureReader(false);
    }

    function moveTextBy(amount) {
        if (mode === 'countdown' || !active()) return;
        session.y += amount;
        renderPosition();
    }

    function changeSpeedBy(amount) {
        if (!active()) return;
        changeSetting('speed', settings.speed + amount);
    }

    function changeFontSizeBy(amount) {
        if (active()) changeSetting('fontSize', settings.fontSize + amount);
    }

    function togglePause() {
        if (!active() || mode === 'countdown') return;
        if (mode === 'finished') return restartPlayback();
        mode = mode === 'playing' ? 'paused' : 'playing';
        session.lastTimestamp = performance.now();
        renderPlaybackState();
    }

    function restartPlayback() {
        if (!active() || mode === 'countdown') return;
        resetReaderPosition();
        mode = 'playing';
        session.lastTimestamp = performance.now();
        renderPlaybackState();
    }

    function checkGamepad(timestamp, delta) {
        let pad;
        try { pad = Array.from(navigator.getGamepads?.() || []).find(Boolean); } catch { return; }
        if (!pad) {
            session.previousButtons = [];
            return;
        }
        const pressed = (index) => Boolean(pad.buttons[index]?.pressed);
        const previous = session.previousButtons;
        session.previousButtons = Array.from(pad.buttons, (button) => button.pressed);
        if (pressed(1) && !previous[1]) return exitPlayer();
        if (mode === 'countdown') return;
        if (pressed(0) && !previous[0]) togglePause();
        if (timestamp >= session.nextGamepadMove) {
            if (pressed(12) || pressed(5)) moveTextBy(35);
            else if (pressed(13) || pressed(4)) moveTextBy(-35);
            session.nextGamepadMove = timestamp + 120;
        }
        const horizontal = pad.axes[0] || 0;
        const vertical = pad.axes[1] || 0;
        if (timestamp >= session.nextGamepadSpeed) {
            if (pressed(14) || horizontal < -.5) changeSpeedBy(-5);
            else if (pressed(15) || horizontal > .5) changeSpeedBy(5);
            session.nextGamepadSpeed = timestamp + 180;
        }
        if (Math.abs(vertical) > .2) moveTextBy(-vertical * 140 * delta);
    }

    function animateReader(timestamp) {
        if (!active()) return;
        const elapsed = Math.max(0, (timestamp - session.lastTimestamp) / 1000);
        const delta = Math.min(elapsed, .1);
        session.lastTimestamp = timestamp;
        checkGamepad(timestamp, delta);
        if (!active()) return;
        if (mode === 'playing' && !document.hidden) {
            session.elapsed += elapsed;
            if (!session.drag) session.y -= settings.speed * delta;
            renderPosition();
            const timer = formatTime(session.elapsed);
            if ($('timer').textContent !== timer) $('timer').textContent = timer;
            if (!session.drag && session.y + session.textHeight <= session.viewportHeight / 2) {
                mode = 'finished';
                renderPlaybackState();
            }
        }
        session.frame = requestAnimationFrame(animateReader);
    }

    async function acquireWakeLock() {
        if (!active() || document.hidden || wakeLock || wakeRequestPending || !navigator.wakeLock) return;
        const token = sessionToken;
        wakeRequestPending = true;
        try {
            const lock = await navigator.wakeLock.request('screen');
            if (token !== sessionToken || !active() || document.hidden) await lock.release();
            else {
                wakeLock = lock;
                lock.addEventListener('release', () => { if (wakeLock === lock) wakeLock = null; });
            }
        } catch { /* Screen wake lock is optional, including in low-power mode. */ }
        finally {
            wakeRequestPending = false;
            if (token !== sessionToken && active()) acquireWakeLock();
        }
    }

    function releaseWakeLock() {
        const lock = wakeLock;
        wakeLock = null;
        if (lock) Promise.resolve(lock.release()).catch(() => {});
    }

    function leaveNativeFullscreen() {
        const fullscreenElement = document.fullscreenElement || document.webkitFullscreenElement;
        const exit = document.exitFullscreen || document.webkitExitFullscreen;
        if (!fullscreenElement || !exit) return;
        try {
            const pending = Promise.resolve(exit.call(document)).catch(() => {});
            fullscreenExit = pending;
            pending.finally(() => { if (fullscreenExit === pending) fullscreenExit = null; });
        } catch { /* The browser may have already left fullscreen. */ }
    }

    async function enterNativeFullscreen(token) {
        const request = document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen;
        if (!request) return;
        try {
            if (fullscreenExit) await fullscreenExit;
            if (token !== sessionToken || !active()) return;
            await request.call(document.documentElement);
            if (!active()) leaveNativeFullscreen();
            else if (token === sessionToken) session.nativeFullscreen = Boolean(document.fullscreenElement || document.webkitFullscreenElement);
        } catch { /* iPhone and embedded browsers can use the same viewport-filling reader without this API. */ }
    }

    function beginPlayback() {
        clearInterval(session.countdownInterval);
        session.countdownInterval = 0;
        $('countdown').hidden = true;
        mode = 'playing';
        session.lastTimestamp = performance.now();
        renderPlaybackState();
        if (!$('controlButtons').contains(document.activeElement)) $('readerViewport').focus({ preventScroll: true });
    }

    function startPlayer() {
        if (active() || !libraryReady || libraryBusy || importBusy || !$('inputText').value.trim()) return;
        library.flush();
        $('inputText').blur();
        if ($('settingsDialog').open) $('settingsDialog').close();
        const token = ++sessionToken;
        session.previousScroll = window.scrollY;
        session.nativeFullscreen = false;
        session.previousButtons = [];
        session.nextGamepadMove = 0;
        session.nextGamepadSpeed = 0;
        mode = settings.countdownSetting ? 'countdown' : 'playing';
        $('text').textContent = $('inputText').value;
        $('controls').hidden = true;
        $('appHeader').hidden = true;
        $('display').hidden = false;
        $('toast').hidden = true;
        document.body.classList.add('is-presenting');
        updateViewportMetrics(true);
        if (themeColor) themeColor.content = settings.bgColor;
        resetReaderPosition();
        renderPlaybackState();
        session.lastTimestamp = performance.now();
        session.frame = requestAnimationFrame(animateReader);
        enterNativeFullscreen(token);
        acquireWakeLock();
        session.remaining = settings.countdownSetting;
        $('countdown').hidden = session.remaining === 0;
        $('countdownNumber').textContent = session.remaining;
        if (!session.remaining) beginPlayback();
        else {
            $('exitBtn').focus({ preventScroll: true });
            session.countdownInterval = setInterval(() => {
                if (token !== sessionToken || mode !== 'countdown' || document.hidden) return;
                session.remaining -= 1;
                $('countdownNumber').textContent = session.remaining;
                if (session.remaining === 0) beginPlayback();
            }, 1000);
        }
    }

    function exitPlayer(exitNative = true) {
        if (!active()) return;
        ++sessionToken;
        mode = 'editor';
        session.nativeFullscreen = false;
        cancelReaderDrag();
        clearInterval(session.countdownInterval);
        cancelAnimationFrame(session.frame);
        session.countdownInterval = 0;
        session.frame = 0;
        $('countdown').hidden = true;
        $('display').hidden = true;
        $('controls').hidden = false;
        $('appHeader').hidden = false;
        document.body.classList.remove('is-presenting');
        updateViewportMetrics(true);
        if (themeColor) themeColor.content = editorThemeColor;
        releaseWakeLock();
        if (exitNative) leaveNativeFullscreen();
        window.scrollTo(0, session.previousScroll);
        $('startBtn').focus({ preventScroll: true });
    }

    // Settings are read defensively so a stale or edited local value cannot break the UI.
    try {
        const savedSettings = JSON.parse(readStorage(SETTINGS_KEY));
        if (savedSettings && typeof savedSettings === 'object' && !Array.isArray(savedSettings)) {
            for (const name of Object.keys(defaults)) settings[name] = normalizeSetting(name, savedSettings[name]);
        }
    } catch { /* An invalid settings entry falls back to defaults; the draft is a separate key. */ }
    const savedDraft = readStorage('savedText');
    $('inputText').value = savedDraft ?? '';
    setImportBusy(false);
    updateDocument(false);
    updateViewportMetrics();
    initializeLibrary(savedDraft);

    $('inputText').addEventListener('input', () => {
        ++draftRevision;
        updateDocument();
    });
    $('draftTitle').addEventListener('input', () => {
        ++draftRevision;
        updateDocument();
    });
    $('openLibraryBtn').addEventListener('click', () => {
        if (!libraryReady || libraryBusy || active()) return;
        library.flush();
        $('inputText').blur();
        $('draftTitle').blur();
        $('librarySearch').value = '';
        libraryFocusTarget = 'openLibraryBtn';
        renderLibrary();
        $('libraryDialog').showModal();
        $('closeLibraryBtn').focus({ preventScroll: true });
    });
    $('librarySearch').addEventListener('input', renderLibrary);
    $('closeLibraryBtn').addEventListener('click', () => $('libraryDialog').close());
    $('libraryDialog').addEventListener('close', () => {
        restoreLibraryFocus();
        reflow();
    });
    $('newDraftBtn').addEventListener('click', async () => {
        await changeLibrary(async () => {
            await library.create({ title: '', text: '' });
            libraryFocusTarget = 'draftTitle';
            $('libraryDialog').close();
        });
    });
    $('draftList').addEventListener('click', async (event) => {
        const button = event.target.closest('button');
        const id = button?.closest('.draft-item')?.dataset.draftId;
        if (!id || libraryBusy) return;
        if (button.classList.contains('draft-delete')) {
            await changeLibrary(async () => {
                deletedDraft = await library.remove(id);
                $('libraryFeedbackMessage').textContent = '文稿已删除';
                $('libraryFeedback').hidden = !deletedDraft;
            });
            $('undoDeleteBtn').focus({ preventScroll: true });
        } else if (button.classList.contains('draft-open')) {
            await changeLibrary(async () => {
                await library.select(id);
                libraryFocusTarget = 'inputText';
                $('libraryDialog').close();
            });
        }
    });
    $('undoDeleteBtn').addEventListener('click', async () => {
        if (!deletedDraft || libraryBusy) return;
        await changeLibrary(async () => {
            await library.restore(deletedDraft);
            deletedDraft = null;
            $('libraryFeedback').hidden = true;
        });
        $('newDraftBtn').focus({ preventScroll: true });
    });
    $('clearBtn').addEventListener('click', () => replaceDraft('', '文稿已清空'));
    $('importBtn').addEventListener('click', () => $('importFile').click());
    $('importFile').addEventListener('change', async (event) => {
        const input = event.currentTarget;
        const file = input.files[0];
        // Clear immediately so choosing the same file again still emits change.
        input.value = '';
        if (!file || active() || !libraryReady || libraryBusy) return;
        const token = ++importToken;
        const revision = draftRevision;
        const draftId = library.active.id;
        const previous = $('inputText').value;
        setImportBusy(true);
        try {
            if (typeof window.FlowDocumentImport?.read !== 'function') throw new Error('导入功能暂时不可用，请刷新页面后重试');
            const value = await window.FlowDocumentImport.read(file);
            if (token !== importToken) return;
            if (revision !== draftRevision || draftId !== library.active.id || previous !== $('inputText').value || active()) {
                showToast('导入期间文稿已修改，已保留当前文稿');
                return;
            }
            if (typeof value !== 'string' || !value.trim()) throw new Error('文件中没有可导入的文字');
            const title = $('draftTitle').value.trim() ? $('draftTitle').value : file.name.replace(/\.[^.]+$/, '').slice(0, 120);
            replaceDraft(value, `已导入 ${file.name}`, title);
        } catch (error) {
            if (token === importToken) showToast(error instanceof Error && error.message
                ? error.message : '文件读取失败，请重试或直接粘贴文字');
        } finally {
            if (token === importToken) setImportBusy(false);
        }
    });

    for (const name of Object.keys(defaults)) {
        const input = $(name);
        const type = input.getAttribute('type');
        if (type === 'color' && input.type !== 'color') {
            input.classList.add('color-text-fallback');
            input.setAttribute('maxlength', '7');
            input.setAttribute('pattern', '#[0-9a-fA-F]{6}');
            input.setAttribute('spellcheck', 'false');
        }
        input.addEventListener('change', () => changeSetting(name, input.type === 'checkbox' ? input.checked : input.value));
        if (type === 'color' || type === 'number') input.addEventListener('input', () => {
            if (input.value !== '' && input.validity.valid) changeSetting(name, input.value);
        });
    }
    for (const name of ['fontSize', 'speed']) {
        $(`${name}Range`).addEventListener('input', (event) => changeSetting(name, event.target.value));
    }
    $('resetSettingsBtn').addEventListener('click', () => {
        settings = { ...defaults };
        applySettings(true);
        saveSettings();
        showToast('已恢复默认设置，文稿保持不变');
    });
    $('startBtn').addEventListener('click', startPlayer);
    $('restartBtn').addEventListener('click', restartPlayback);
    $('exitBtn').addEventListener('click', () => exitPlayer());
    $('slowerBtn').addEventListener('click', () => changeSpeedBy(-5));
    $('fasterBtn').addEventListener('click', () => changeSpeedBy(5));
    $('smallerFontBtn').addEventListener('click', () => changeFontSizeBy(-2));
    $('largerFontBtn').addEventListener('click', () => changeFontSizeBy(2));

    $('readerViewport').addEventListener('pointerdown', (event) => {
        if (!active() || mode === 'countdown' || session.drag || !event.isPrimary || event.button !== 0) return;
        if (event.target.closest('button, input, select, textarea, a')) return;
        session.drag = { id: event.pointerId, origin: session.y, start: event.clientY, moved: false };
        $('readerViewport').setPointerCapture(event.pointerId);
    });
    $('readerViewport').addEventListener('pointermove', (event) => {
        if (!session.drag || session.drag.id !== event.pointerId) return;
        const distance = event.clientY - session.drag.start;
        if (Math.abs(distance) > 6) session.drag.moved = true;
        if (session.drag.moved) {
            session.y = session.drag.origin + distance;
            renderPosition();
        }
    });
    const endDrag = (event) => {
        if (!session.drag || session.drag.id !== event.pointerId) return;
        const tapped = !session.drag.moved && event.type === 'pointerup';
        session.drag = null;
        if ($('readerViewport').hasPointerCapture(event.pointerId)) $('readerViewport').releasePointerCapture(event.pointerId);
        session.lastTimestamp = performance.now();
        if (tapped) togglePause();
    };
    $('readerViewport').addEventListener('pointerup', endDrag);
    $('readerViewport').addEventListener('pointercancel', endDrag);
    $('readerViewport').addEventListener('lostpointercapture', endDrag);
    $('readerViewport').addEventListener('click', (event) => {
        // Assistive technology may activate the reading surface without pointer events.
        if (event.detail === 0 && !event.target.closest('button, input, select, textarea, a')) togglePause();
    });

    document.addEventListener('keydown', (event) => {
        if (!active() || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return;
        if (event.code === 'Escape') {
            event.preventDefault();
            exitPlayer();
            return;
        }
        if (event.target.closest('button, input, select, textarea, a, [contenteditable="true"], [role="slider"]')) return;
        if (mode === 'countdown') return;
        if (['Space', 'Enter', 'NumpadEnter'].includes(event.code)) {
            event.preventDefault();
            if (!event.repeat) togglePause();
            return;
        }
        const actions = {
            ArrowUp: () => moveTextBy(35), PageUp: () => moveTextBy(100),
            ArrowDown: () => moveTextBy(-35), PageDown: () => moveTextBy(-100),
            ArrowLeft: () => changeSpeedBy(-5), ArrowRight: () => changeSpeedBy(5),
        };
        if (actions[event.code]) {
            event.preventDefault();
            actions[event.code]();
        }
    });

    const handleFullscreenChange = () => {
        if (active() && session.nativeFullscreen && !document.fullscreenElement && !document.webkitFullscreenElement) {
            session.nativeFullscreen = false;
            exitPlayer(false);
        }
        reflow(true);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            library?.flush();
            if (mode === 'playing') togglePause();
            releaseWakeLock();
        } else if (active()) acquireWakeLock();
    });
    window.addEventListener('pagehide', () => {
        library?.flush();
        if (active()) exitPlayer();
    });

    function updateViewportMetrics(reset = false) {
        const viewport = window.visualViewport;
        const height = viewport?.height || window.innerHeight;
        const fullHeight = Math.max(window.innerHeight, height);
        const editing = mobileLayout.matches && !active()
            && document.activeElement?.matches('textarea, input[type="number"], input[type="text"], input[type="search"]');
        if (reset || Math.abs(window.innerWidth - viewportState.width) > 40) {
            viewportState.width = window.innerWidth;
            viewportState.height = fullHeight;
            viewportState.keyboardClosing = false;
        }
        const threshold = Math.max(120, viewportState.height * .18);
        const shortened = viewportState.height - height > threshold;
        // Retain the height before focus when Android also resizes the layout viewport.
        // After blur, keep it until the closing keyboard has restored the visible height.
        if (!editing && (!viewportState.keyboardClosing || !shortened)) {
            viewportState.height = fullHeight;
            viewportState.keyboardClosing = false;
        } else viewportState.height = Math.max(viewportState.height, fullHeight);
        const keyboardDetected = Boolean(editing && (!viewport || Math.abs(viewport.scale - 1) < .05)
            && viewportState.height - height > Math.max(120, viewportState.height * .18));
        if (keyboardDetected) viewportState.keyboardClosing = true;
        else if (!shortened || active() || !mobileLayout.matches) viewportState.keyboardClosing = false;
        document.documentElement.style.setProperty('--app-height', `${height}px`);
        document.documentElement.style.setProperty('--viewport-offset-top', `${viewport?.offsetTop || 0}px`);
        // Keep controls still between pointerdown (which blurs the field) and click.
        document.body.classList.toggle('keyboard-open', keyboardDetected || viewportState.keyboardClosing);
    }

    function reflow(reset = false) {
        updateViewportMetrics(reset);
        cancelAnimationFrame(resizeFrame);
        resizeFrame = requestAnimationFrame(() => {
            resizeFrame = 0;
            if (active()) measureReader();
        });
    }
    window.addEventListener('resize', () => reflow());
    window.addEventListener('orientationchange', () => reflow(true));
    window.visualViewport?.addEventListener('resize', () => reflow());
    window.visualViewport?.addEventListener('scroll', () => updateViewportMetrics());
    document.addEventListener('focusin', () => updateViewportMetrics());
    document.addEventListener('focusout', () => requestAnimationFrame(() => updateViewportMetrics()));
    mobileLayout.addEventListener('change', () => reflow(true));
    document.fonts?.addEventListener('loadingdone', () => reflow());

    $('openSettingsBtn').addEventListener('click', () => {
        if (active() || $('settingsDialog').open) return;
        $('inputText').blur();
        $('settingsDialog').showModal();
        $('closeSettingsBtn').focus({ preventScroll: true });
    });
    $('closeSettingsBtn').addEventListener('click', () => $('settingsDialog').close());
    $('doneSettingsBtn').addEventListener('click', () => $('settingsDialog').close());
    $('settingsDialog').addEventListener('cancel', (event) => {
        event.preventDefault();
        $('settingsDialog').close();
    });
    $('settingsDialog').addEventListener('close', () => {
        settingsBackdropDown = false;
        if (!active()) $('openSettingsBtn').focus({ preventScroll: true });
        reflow();
    });
    const outsideSettings = (event) => {
        const bounds = $('settingsDialog').getBoundingClientRect();
        return event.target === $('settingsDialog') && (event.clientX < bounds.left || event.clientX > bounds.right
            || event.clientY < bounds.top || event.clientY > bounds.bottom);
    };
    $('settingsDialog').addEventListener('pointerdown', (event) => { settingsBackdropDown = outsideSettings(event); });
    $('settingsDialog').addEventListener('click', (event) => {
        if (settingsBackdropDown && outsideSettings(event)) $('settingsDialog').close();
        settingsBackdropDown = false;
    });
})();
