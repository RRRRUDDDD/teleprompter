(() => {
    'use strict';

    const baseURL = new URL('./', document.currentScript?.src || document.baseURI);
    const workerURL = new URL('worker.js', baseURL).href;
    const webProtocol = ['http:', 'https:'].includes(location.protocol);
    const supported = webProtocol && window.isSecureContext && 'serviceWorker' in navigator;
    const installButton = document.getElementById('installAppBtn');
    const installHint = document.getElementById('installHint');
    const offlineStatus = document.getElementById('offlineStatus');
    const updateStatus = document.getElementById('updateStatus');
    const displayMode = window.matchMedia('(display-mode: standalone)');
    const isiOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    let installed = displayMode.matches || navigator.standalone === true;
    let deferredPrompt = null;
    let prompting = false;
    let registration = null;
    let registrationFailed = false;
    let statusRevision = 0;
    const watchedWorkers = new WeakSet();

    function setOfflineStatus(state, text) {
        if (!offlineStatus) return;
        offlineStatus.dataset.state = state;
        offlineStatus.textContent = text;
    }

    function renderInstall() {
        if (installButton) {
            installButton.hidden = !supported || installed || !deferredPrompt;
            installButton.disabled = prompting;
        }
        if (!installHint) return;
        if (!webProtocol) {
            installHint.textContent = '请通过网站打开，才能安装到设备。';
        } else if (installed) {
            installHint.textContent = '已安装，可从设备主屏幕或应用列表打开。';
        } else if (!window.isSecureContext) {
            installHint.textContent = '请通过 HTTPS 网站打开，才能安装到设备。';
        } else if (isiOS) {
            installHint.textContent = '在 Safari 中打开，轻点“共享”，再选“添加到主屏幕”。';
        } else if (deferredPrompt) {
            installHint.textContent = '安装后可从设备主屏幕或应用列表直接打开。';
        } else {
            installHint.textContent = '可在浏览器菜单中选择“安装应用”或“添加到主屏幕”（如支持）。';
        }
    }

    function checkCache(controller) {
        return new Promise((resolve) => {
            const channel = new MessageChannel();
            const finish = (ready) => {
                clearTimeout(timer);
                channel.port1.close();
                resolve(ready);
            };
            const timer = setTimeout(() => finish(false), 3000);
            channel.port1.onmessage = (event) => finish(event.data?.ready === true);
            try {
                controller.postMessage({ type: 'FLOW_OFFLINE_STATUS' }, [channel.port2]);
            } catch (_) {
                finish(false);
            }
        });
    }

    async function refreshStatus() {
        const revision = ++statusRevision;
        if (updateStatus) {
            updateStatus.textContent = registration?.waiting
                ? '有新版本；结束后关闭所有提词器窗口，再重新打开即可更新。' : '';
            updateStatus.hidden = !registration?.waiting;
        }
        if (!supported) {
            setOfflineStatus('unsupported', webProtocol
                ? '当前浏览器或连接不支持离线准备，仍可正常提词。'
                : '当前为本地文件模式；通过网站打开并联网准备后可离线使用。');
            return;
        }
        const controller = navigator.serviceWorker.controller;
        if (registration?.active?.state === 'activated' && controller?.scriptURL === workerURL) {
            const ready = await checkCache(controller);
            if (revision !== statusRevision) return;
            if (ready) {
                setOfflineStatus(navigator.onLine ? 'ready' : 'offline', navigator.onLine
                    ? '离线已准备好，可离线打开、编辑文稿并导入 TXT / DOCX。'
                    : '当前离线，可继续编辑、切换文稿、提词及导入 TXT / DOCX。');
                return;
            }
        }
        if (revision !== statusRevision) return;
        if (!navigator.onLine) {
            setOfflineStatus('unavailable', '当前离线，离线资源尚未准备完整；请联网后重新打开。');
        } else if (registrationFailed) {
            setOfflineStatus('unavailable', '离线准备未完成；请保持联网，稍后重新打开。');
        } else if (!registration || registration.installing) {
            setOfflineStatus('preparing', '正在准备离线资源，请保持联网…');
        } else {
            setOfflineStatus('unavailable', '离线资源尚未准备完整；请联网后重新打开。');
        }
    }

    function watchWorker(worker) {
        if (!worker || watchedWorkers.has(worker)) return;
        watchedWorkers.add(worker);
        worker.addEventListener('statechange', () => {
            if (worker.state === 'redundant' && !registration?.active) registrationFailed = true;
            refreshStatus();
        });
    }

    window.addEventListener('beforeinstallprompt', (event) => {
        event.preventDefault();
        deferredPrompt = event;
        renderInstall();
    });
    installButton?.addEventListener('click', async () => {
        const promptEvent = deferredPrompt;
        if (!promptEvent || prompting || installed) return;
        prompting = true;
        renderInstall();
        try {
            await promptEvent.prompt();
            await promptEvent.userChoice;
        } catch (_) {
            // Dismissed or unavailable native prompts leave the browser-menu fallback.
        } finally {
            if (deferredPrompt === promptEvent) deferredPrompt = null;
            prompting = false;
            renderInstall();
        }
    });
    window.addEventListener('appinstalled', () => {
        installed = true;
        deferredPrompt = null;
        renderInstall();
    });
    const displayChanged = () => {
        installed = displayMode.matches || navigator.standalone === true;
        renderInstall();
    };
    if (displayMode.addEventListener) displayMode.addEventListener('change', displayChanged);
    else if (displayMode.addListener) displayMode.addListener(displayChanged);
    window.addEventListener('online', refreshStatus);
    window.addEventListener('offline', refreshStatus);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) refreshStatus();
    });

    const manifest = document.getElementById('appManifest');
    if (webProtocol && manifest) manifest.href = new URL('manifest.json', baseURL).href;
    renderInstall();
    refreshStatus();
    if (!supported) return;

    navigator.serviceWorker.addEventListener('controllerchange', refreshStatus);
    navigator.serviceWorker.register(workerURL, { scope: baseURL.href, updateViaCache: 'none' })
        .then((result) => {
            registration = result;
            watchWorker(result.installing);
            watchWorker(result.waiting);
            watchWorker(result.active);
            result.addEventListener('updatefound', () => {
                watchWorker(result.installing);
                refreshStatus();
            });
            refreshStatus();
        })
        .catch(() => {
            registrationFailed = true;
            refreshStatus();
        });
})();
