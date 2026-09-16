(() => {
    'use strict';

    const $ = (id) => document.getElementById(id);
    const SETTINGS_KEY = 'flow.teleprompter.settings.v1';
    const mobileLayout = window.matchMedia('(max-width: 900px)');
    const SAMPLE_TEXT = '每一个精彩的故事，\n都值得被好好说出来。\n\n嗨，很高兴在这里见到你。\n\n也许你正在准备一次分享，录制一段视频，\n或是想把心里的想法，认真地说给世界听。\n\n不必着急，也不用担心忘词。\n调整到舒服的速度，深呼吸，看看镜头。\n\n让文字跟上你的节奏，\n把注意力留给真正重要的表达。\n\n准备好了吗？\n接下来的舞台，是你的。';
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
    const session = {
        frame: 0, countdownInterval: 0, remaining: 0, elapsed: 0,
        y: 0, startY: 0, lastTimestamp: 0, textHeight: 0, viewportHeight: 0,
        drag: null, nativeFullscreen: false, previousScroll: 0,
        previousButtons: [], nextGamepadMove: 0, nextGamepadSpeed: 0,
    };
    const preview = { frame: 0, playing: false, finished: false, scale: .57, y: 0, elapsed: 0, lastTimestamp: 0 };
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
            $('saveLabel').textContent = '未能保存，请保留文稿';
            $('saveStatus').classList.add('unsaved');
            return false;
        }
    }

    function normalizeSetting(name, value, fallback = defaults[name]) {
        if (name in numericBounds) {
            const number = Number(value);
            return value === '' || value === null || !Number.isFinite(number)
                ? fallback : clamp(Math.round(number), ...numericBounds[name]);
        }
        if (name === 'countdownSetting') return [0, 3, 5, 10].includes(Number(value)) ? Number(value) : fallback;
        if (name === 'fontFamily') return fontOptions.includes(value) ? value : fallback;
        if (name === 'mirror' || name === 'showTimer') return typeof value === 'boolean' ? value : fallback;
        return typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : fallback;
    }

    function saveSettings() {
        writeStorage(SETTINGS_KEY, JSON.stringify(settings));
    }

    function updateRange(name) {
        const range = $(`${name}Range`);
        range.value = settings[name];
        const [min, max] = numericBounds[name];
        range.style.setProperty('--range-progress', `${(settings[name] - min) / (max - min) * 100}%`);
    }

    function applySettings() {
        for (const name of Object.keys(defaults)) {
            const input = $(name);
            if (typeof defaults[name] === 'boolean') input.checked = settings[name];
            else input.value = settings[name];
        }
        updateRange('fontSize');
        updateRange('speed');
        $('fontColorValue').textContent = settings.fontColor.toUpperCase();
        $('bgColorValue').textContent = settings.bgColor.toUpperCase();
        $('previewStage').style.setProperty('--stage-bg', settings.bgColor);
        $('display').style.setProperty('--stage-bg', settings.bgColor);
        $('previewText').style.fontFamily = settings.fontFamily;
        $('previewText').style.color = settings.fontColor;
        $('text').style.fontFamily = settings.fontFamily;
        $('text').style.fontSize = `${settings.fontSize}px`;
        $('text').style.color = settings.fontColor;
        for (const id of ['previewMirror', 'readerMirror']) {
            $(id).style.transform = settings.mirror ? 'scaleX(-1)' : 'none';
        }
        for (const id of ['previewReferenceLine', 'referenceLine']) {
            $(id).style.setProperty('--guide-color', settings.refLineColor);
            $(id).style.borderTopWidth = `${settings.refLineWidth}px`;
            $(id).hidden = settings.refLineWidth === 0 || !$('inputText').value.trim();
        }
        $('previewTimer').hidden = !settings.showTimer;
        $('timer').hidden = !settings.showTimer;
        $('playbackSpeed').textContent = settings.speed;
        $('startHint').textContent = !$('inputText').value.trim() ? '先写下你想说的话' :
            settings.countdownSetting ? `${settings.countdownSetting} 秒倒计时，从容开始` : '准备好，随时开始';
        if (active()) document.querySelector('meta[name="theme-color"]').content = settings.bgColor;
        stopPreview(true);
    }

    function changeSetting(name, value) {
        settings[name] = normalizeSetting(name, value, settings[name]);
        applySettings();
        saveSettings();
    }

    function updateDocument(save = true) {
        const value = $('inputText').value;
        const count = Array.from(value.replace(/\s/g, '')).length;
        $('wordCount').textContent = count;
        $('readTime').textContent = formatTime(Math.ceil(count / 4));
        $('previewText').textContent = value;
        $('previewEmpty').hidden = Boolean(value.trim());
        for (const id of ['startBtn', 'expandPreviewBtn', 'previewPlayBtn']) $(id).disabled = !value.trim();
        $('clearBtn').disabled = !value;
        if (save && writeStorage('savedText', value)) {
            $('saveLabel').textContent = '已自动保存';
            $('saveStatus').classList.remove('unsaved');
        }
        applySettings();
    }

    function showToast(message, undo) {
        clearTimeout(toastTimeout);
        $('toastMessage').textContent = message;
        $('toastAction').hidden = !undo;
        $('toastAction').onclick = undo ? () => {
            undo();
            clearTimeout(toastTimeout);
            $('toast').hidden = true;
        } : null;
        $('toast').hidden = false;
        const dismiss = () => {
            if ($('toast').contains(document.activeElement)) toastTimeout = setTimeout(dismiss, 2000);
            else $('toast').hidden = true;
        };
        toastTimeout = setTimeout(dismiss, 6500);
    }

    function replaceDraft(value, message) {
        const previous = $('inputText').value;
        $('inputText').value = value;
        updateDocument();
        showToast(message, () => {
            $('inputText').value = previous;
            updateDocument();
            selectPanel('editor');
            $('inputText').focus({ preventScroll: true });
        });
    }

    function selectPanel(panel) {
        if (!['editor', 'preview', 'settings'].includes(panel)) return;
        document.body.dataset.panel = panel;
        document.querySelectorAll('.mobile-tabs button').forEach((button) => {
            button.setAttribute('aria-pressed', String(button.dataset.panel === panel));
        });
        if (mobileLayout.matches) window.scrollTo(0, 0);
        stopPreview(true);
    }

    function resetPreviewPosition() {
        const readerWidth = Math.min(1120, window.innerWidth - (mobileLayout.matches ? 48 : 120));
        const previewWidth = Math.max(1, $('previewStage').clientWidth - (mobileLayout.matches ? 54 : 86));
        preview.scale = previewWidth / Math.max(1, readerWidth);
        $('previewText').style.fontSize = `${settings.fontSize * preview.scale}px`;
        preview.y = $('previewStage').clientHeight / 2 - settings.fontSize * preview.scale * .85;
        preview.elapsed = 0;
        preview.finished = false;
        $('previewText').style.transform = `translateY(${preview.y}px)`;
        $('previewTimer').textContent = '00:00';
    }

    function stopPreview(reset = false) {
        cancelAnimationFrame(preview.frame);
        preview.frame = 0;
        preview.playing = false;
        if (reset) resetPreviewPosition();
        $('previewPlayIcon').setAttribute('href', '#i-play');
        $('previewPlayLabel').textContent = preview.finished ? '重新预览' : '播放预览';
    }

    function animatePreview(timestamp) {
        if (!preview.playing) return;
        const delta = Math.min(.1, Math.max(0, (timestamp - preview.lastTimestamp) / 1000));
        preview.lastTimestamp = timestamp;
        preview.y -= settings.speed * preview.scale * delta;
        preview.elapsed += delta;
        $('previewText').style.transform = `translateY(${preview.y}px)`;
        $('previewTimer').textContent = formatTime(preview.elapsed);
        if (preview.y + $('previewText').offsetHeight <= $('previewStage').clientHeight / 2) {
            preview.finished = true;
            stopPreview();
            return;
        }
        preview.frame = requestAnimationFrame(animatePreview);
    }

    function togglePreview() {
        if (!$('inputText').value.trim()) return;
        if (preview.playing) return stopPreview();
        if (preview.finished) resetPreviewPosition();
        preview.playing = true;
        preview.lastTimestamp = performance.now();
        $('previewPlayIcon').setAttribute('href', '#i-pause');
        $('previewPlayLabel').textContent = '暂停预览';
        preview.frame = requestAnimationFrame(animatePreview);
    }

    function renderPlaybackState() {
        const labels = { countdown: '准备开始', playing: '正在提词', paused: '已暂停', finished: '本次已完成' };
        $('display').dataset.state = mode;
        $('playbackStatus').textContent = labels[mode] || '';
        $('pauseBtn').disabled = mode === 'countdown';
        $('restartBtn').disabled = mode === 'countdown';
        $('pauseLabel').textContent = mode === 'finished' ? '重播' : mode === 'paused' ? '继续' : '暂停';
        $('pauseIcon').setAttribute('href', mode === 'finished' ? '#i-reset' : mode === 'paused' ? '#i-play' : '#i-pause');
    }

    function renderPosition() {
        $('text').style.transform = `translateY(${session.y}px)`;
        const travel = Math.max(1, session.textHeight - settings.fontSize * .85);
        const progress = clamp((session.startY - session.y) / travel, 0, 1);
        $('progressFill').style.transform = `scaleX(${progress})`;
        const percent = String(Math.round(progress * 100));
        if ($('readingProgress').getAttribute('aria-valuenow') !== percent) $('readingProgress').setAttribute('aria-valuenow', percent);
    }

    function resetReaderPosition() {
        session.viewportHeight = $('display').clientHeight;
        session.textHeight = $('text').offsetHeight;
        session.startY = session.viewportHeight / 2 - settings.fontSize * .85;
        session.y = session.startY;
        session.elapsed = 0;
        session.drag = null;
        $('timer').textContent = '00:00';
        renderPosition();
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
        $('pauseBtn').focus({ preventScroll: true });
    }

    function startPlayer() {
        if (active() || !$('inputText').value.trim()) return;
        stopPreview(true);
        $('inputText').blur();
        if ($('myModal').open) $('myModal').close();
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
        document.querySelector('meta[name="theme-color"]').content = settings.bgColor;
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
        session.drag = null;
        clearInterval(session.countdownInterval);
        cancelAnimationFrame(session.frame);
        session.countdownInterval = 0;
        session.frame = 0;
        $('countdown').hidden = true;
        $('display').hidden = true;
        $('controls').hidden = false;
        $('appHeader').hidden = false;
        document.body.classList.remove('is-presenting');
        document.querySelector('meta[name="theme-color"]').content = '#f6f8f6';
        releaseWakeLock();
        if (exitNative) leaveNativeFullscreen();
        stopPreview(true);
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
    $('inputText').value = savedDraft === null ? SAMPLE_TEXT : savedDraft;
    updateDocument();

    $('inputText').addEventListener('input', () => updateDocument());
    $('clearBtn').addEventListener('click', () => replaceDraft('', '文稿已清空'));
    $('sampleBtn').addEventListener('click', () => replaceDraft(SAMPLE_TEXT, '已载入示例文稿'));
    $('importBtn').addEventListener('click', () => $('importFile').click());
    $('importFile').addEventListener('change', async (event) => {
        const file = event.target.files[0];
        if (!file) return;
        try {
            if (!/\.txt$/i.test(file.name)) return showToast('请选择 UTF-8 编码的 .txt 文件');
            if (file.size > 1024 * 1024) return showToast('文稿较长，请选择小于 1 MB 的文字文件');
            const value = await file.text();
            replaceDraft(value.replace(/^\uFEFF/, ''), `已导入 ${file.name}`);
            selectPanel('editor');
        } catch { showToast('文件读取失败，请重试或直接粘贴文字'); }
        finally { event.target.value = ''; }
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
        applySettings();
        saveSettings();
        showToast('已恢复默认设置，文稿保持不变');
    });
    document.querySelectorAll('.mobile-tabs button').forEach((button) => {
        button.addEventListener('click', () => selectPanel(button.dataset.panel));
    });
    $('previewPlayBtn').addEventListener('click', togglePreview);
    $('startBtn').addEventListener('click', startPlayer);
    $('expandPreviewBtn').addEventListener('click', startPlayer);
    $('pauseBtn').addEventListener('click', togglePause);
    $('restartBtn').addEventListener('click', restartPlayback);
    $('exitBtn').addEventListener('click', () => exitPlayer());
    $('slowerBtn').addEventListener('click', () => changeSpeedBy(-5));
    $('fasterBtn').addEventListener('click', () => changeSpeedBy(5));

    $('readerViewport').addEventListener('pointerdown', (event) => {
        if (!active() || mode === 'countdown' || session.drag || !event.isPrimary || event.button !== 0) return;
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

    document.addEventListener('keydown', (event) => {
        if (!active() || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return;
        if (event.code === 'Escape') {
            event.preventDefault();
            exitPlayer();
            return;
        }
        if (mode === 'countdown') return;
        if (event.code === 'Space') {
            if (event.target.closest('button') && event.target.id !== 'pauseBtn') return;
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
        if (active() && session.nativeFullscreen && !document.fullscreenElement && !document.webkitFullscreenElement) exitPlayer(false);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stopPreview();
            if (mode === 'playing') togglePause();
            releaseWakeLock();
        } else if (active()) acquireWakeLock();
    });
    window.addEventListener('pagehide', () => {
        stopPreview();
        if (active()) exitPlayer();
    });

    const updateKeyboardInset = () => {
        const viewport = window.visualViewport;
        const editing = document.activeElement?.matches('textarea, input[type="number"]');
        const inset = viewport && mobileLayout.matches && editing && !active()
            ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop) : 0;
        document.documentElement.style.setProperty('--keyboard-offset', `${inset > 120 ? inset : 0}px`);
    };
    const reflow = () => {
        updateKeyboardInset();
        cancelAnimationFrame(resizeFrame);
        resizeFrame = requestAnimationFrame(() => {
            if (!active()) return stopPreview(true);
            // Preserve the reading point when rotating a phone or resizing the viewport.
            const fraction = session.textHeight ? (session.viewportHeight / 2 - session.y) / session.textHeight : 0;
            session.textHeight = $('text').offsetHeight;
            session.viewportHeight = $('display').clientHeight;
            session.startY = session.viewportHeight / 2 - settings.fontSize * .85;
            session.y = session.viewportHeight / 2 - fraction * session.textHeight;
            session.drag = null;
            renderPosition();
        });
    };
    window.addEventListener('resize', reflow);
    window.visualViewport?.addEventListener('resize', reflow);
    window.visualViewport?.addEventListener('scroll', updateKeyboardInset);
    document.addEventListener('focusin', updateKeyboardInset);
    document.addEventListener('focusout', () => requestAnimationFrame(updateKeyboardInset));
    mobileLayout.addEventListener('change', reflow);
    $('openModalBtn').addEventListener('click', () => {
        stopPreview();
        $('myModal').showModal();
    });
    $('myModal').addEventListener('close', () => {
        if (!active()) $('openModalBtn').focus({ preventScroll: true });
    });
    $('myModal').addEventListener('click', (event) => {
        const bounds = $('myModal').getBoundingClientRect();
        if (event.target === $('myModal') && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) $('myModal').close();
    });
})();
