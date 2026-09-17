(() => {
    'use strict';

    const DATABASE_NAME = 'flow.teleprompter.scripts';
    const DATABASE_VERSION = 1;
    const STORAGE_TIMEOUT = 3000;
    const MIGRATION_KEY = 'legacyMigration';
    const ACTIVE_KEY = 'activeId';
    const clone = (record) => record ? { ...record } : null;
    class StorageConflictError extends Error {}

    function sameRecord(actual, expected) {
        if (!actual || !expected) return actual === expected;
        const keys = Object.keys(expected);
        return Object.keys(actual).length === keys.length
            && keys.every((key) => actual[key] === expected[key]);
    }

    function validRecord(record) {
        return record && typeof record.id === 'string' && record.id.length > 0
            && typeof record.title === 'string' && record.title.length <= 120
            && typeof record.text === 'string'
            && Number.isFinite(record.createdAt) && record.createdAt >= 0
            && Number.isFinite(record.updatedAt) && record.updatedAt >= record.createdAt;
    }

    function copyRecord(record) {
        return {
            id: record.id, title: record.title, text: record.text,
            createdAt: record.createdAt, updatedAt: record.updatedAt,
        };
    }

    function newRecord({ title = '', text = '' } = {}) {
        const now = Date.now();
        const id = globalThis.crypto?.randomUUID?.()
            || `${now.toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
        return {
            id,
            title: typeof title === 'string' ? title.slice(0, 120) : '',
            text: typeof text === 'string' ? text : '',
            createdAt: now,
            updatedAt: now,
        };
    }

    function openDatabase() {
        return new Promise((resolve, reject) => {
            let request;
            let settled = false;
            const finish = (error, database) => {
                if (settled) {
                    database?.close();
                    return;
                }
                settled = true;
                clearTimeout(timer);
                if (error) reject(error);
                else resolve(database);
            };
            const timer = setTimeout(() => finish(new Error('Database open timed out.')), STORAGE_TIMEOUT);
            try {
                request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
                request.onupgradeneeded = (event) => {
                    // A timed-out request may unblock later. It must not create or alter data.
                    if (settled || event.oldVersion !== 0) {
                        request.transaction.abort();
                        return;
                    }
                    request.result.createObjectStore('drafts', { keyPath: 'id' });
                    request.result.createObjectStore('meta', { keyPath: 'key' });
                };
                request.onsuccess = () => finish(null, request.result);
                request.onerror = () => finish(request.error || new Error('Database unavailable.'));
                request.onblocked = () => finish(new Error('Database open is blocked.'));
            } catch (error) {
                finish(error);
            }
        });
    }

    function transaction(database, configure) {
        return new Promise((resolve, reject) => {
            let tx;
            let result;
            let failure;
            let settled = false;
            const finish = (error) => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                if (error) reject(error);
                else resolve(result);
            };
            const abort = (error) => {
                failure = error;
                try { tx?.abort(); } catch { /* The transaction may already have ended. */ }
                finish(error);
            };
            const timer = setTimeout(() => abort(new Error('Database transaction timed out.')), STORAGE_TIMEOUT);
            try {
                tx = database.transaction(['drafts', 'meta'], 'readwrite');
                tx.oncomplete = () => finish();
                tx.onerror = (event) => { failure = event.target.error; };
                tx.onabort = () => finish(failure || tx.error || new Error('Database transaction aborted.'));
                configure(tx, (value) => { result = value; }, abort);
            } catch (error) {
                abort(error);
            }
        });
    }

    function initialize(database, legacyText) {
        if (database.version !== DATABASE_VERSION
            || !database.objectStoreNames.contains('drafts')
            || !database.objectStoreNames.contains('meta')) {
            return Promise.reject(new Error('Unrecognized database schema.'));
        }
        return transaction(database, (tx, complete, abort) => {
            const drafts = tx.objectStore('drafts');
            const meta = tx.objectStore('meta');
            if (drafts.keyPath !== 'id' || meta.keyPath !== 'key'
                || drafts.autoIncrement || meta.autoIncrement) {
                throw new Error('Unrecognized database schema.');
            }
            const recordsRequest = drafts.getAll();
            const activeRequest = meta.get(ACTIVE_KEY);
            const migrationRequest = meta.get(MIGRATION_KEY);
            let remaining = 3;
            const loaded = () => {
                if (--remaining) return;
                try {
                    const records = recordsRequest.result;
                    const migration = migrationRequest.result;
                    const selected = activeRequest.result;
                    if (!records.every(validRecord)
                        || (migration !== undefined && migration.value !== 1)
                        || (selected !== undefined && typeof selected.value !== 'string')) {
                        throw new Error('Unrecognized database contents.');
                    }
                    let activeId = selected?.value;
                    if (!records.length) {
                        // The durable marker prevents an empty library from importing an old mirror again.
                        const initial = newRecord({ text: migration === undefined ? legacyText : '' });
                        records.push(initial);
                        drafts.add(initial);
                    }
                    if (!records.some((record) => record.id === activeId)) {
                        activeId = records.slice().sort((a, b) => b.updatedAt - a.updatedAt)[0].id;
                        meta.put({ key: ACTIVE_KEY, value: activeId });
                    }
                    if (migration === undefined) meta.put({ key: MIGRATION_KEY, value: 1 });
                    complete({ records: records.map(copyRecord), activeId });
                } catch (error) {
                    abort(error);
                }
            };
            recordsRequest.onsuccess = loaded;
            activeRequest.onsuccess = loaded;
            migrationRequest.onsuccess = loaded;
        });
    }

    async function open({ legacyText = '', onStatus } = {}) {
        let database = null;
        let unavailable = false;
        let unavailableReason;
        let state;
        let records;
        let persistedRecords = new Map();
        let activeId;
        let revision = 0;
        let pending = 0;
        let queue = Promise.resolve();
        const status = (next) => {
            if (state === next) return;
            state = next;
            const event = { state: next };
            if (next === 'unavailable' && unavailableReason) event.reason = unavailableReason;
            try { onStatus?.(event); } catch { /* UI observers cannot interrupt saving. */ }
        };
        const disableStorage = (reason) => {
            unavailable = true;
            if (reason === 'conflict') unavailableReason = reason;
            database?.close();
            database = null;
            status('unavailable');
        };
        const mirror = (record, savedRevision) => {
            if (unavailable || !database || activeId !== record.id || revision !== savedRevision) return;
            // This compatibility copy is best effort; IndexedDB is the authoritative saved draft.
            try { localStorage.setItem('savedText', record.text); } catch { /* Canonical save succeeded. */ }
        };

        status('saving');
        try {
            database = await openDatabase();
            database.onversionchange = () => disableStorage();
            database.onclose = () => disableStorage();
            const initial = await initialize(database, typeof legacyText === 'string' ? legacyText : '');
            if (unavailable) throw new Error('Database connection was closed.');
            records = new Map(initial.records.map((record) => [record.id, record]));
            persistedRecords = new Map(initial.records.map((record) => [record.id, clone(record)]));
            activeId = initial.activeId;
            mirror(records.get(activeId), revision);
            status('saved');
        } catch {
            disableStorage();
            const initial = newRecord({ text: legacyText });
            records = new Map([[initial.id, initial]]);
            activeId = initial.id;
        }

        const enqueue = ({ puts = [], adds = [], deletes = [], setActive = false } = {}) => {
            const savedRevision = ++revision;
            const selectedId = activeId;
            const selected = clone(records.get(activeId));
            // Capture every queued value now. Subsequent keystrokes must not mutate a pending write.
            const changes = { puts: puts.map(clone), adds: adds.map(clone), deletes: [...deletes] };
            pending += 1;
            status(unavailable ? 'unavailable' : 'saving');
            queue = queue.then(async () => {
                try {
                    if (unavailable || !database) return;
                    await transaction(database, (tx, complete, abort) => {
                        const drafts = tx.objectStore('drafts');
                        const checkedIds = [...new Set([...changes.puts.map((record) => record.id), ...changes.deletes])];
                        let remaining = checkedIds.length;
                        let canceled = false;
                        const fail = (error) => { canceled = true; abort(error); };
                        const write = () => {
                            if (canceled) return;
                            try {
                                changes.puts.forEach((record) => drafts.put(record));
                                changes.adds.forEach((record) => drafts.add(record));
                                changes.deletes.forEach((id) => drafts.delete(id));
                                if (setActive) tx.objectStore('meta').put({ key: ACTIVE_KEY, value: selectedId });
                            } catch (error) {
                                fail(error);
                            }
                        };
                        if (!remaining) return write();
                        checkedIds.forEach((id) => {
                            const request = drafts.get(id);
                            request.onsuccess = () => {
                                if (canceled) return;
                                // Compare inside the write transaction, against the preceding committed save.
                                // A stale tab must neither replace newer contents nor resurrect a deleted draft.
                                if (!sameRecord(request.result, persistedRecords.get(id))) {
                                    fail(new StorageConflictError('Draft changed in another tab.'));
                                    return;
                                }
                                if (--remaining === 0) write();
                            };
                        });
                    });
                    changes.puts.forEach((record) => persistedRecords.set(record.id, record));
                    changes.adds.forEach((record) => persistedRecords.set(record.id, record));
                    changes.deletes.forEach((id) => persistedRecords.delete(id));
                    mirror(selected, savedRevision);
                } catch (error) {
                    // Keep all subsequent changes in memory: later writes cannot hide this failed save.
                    disableStorage(error instanceof StorageConflictError ? 'conflict' : undefined);
                } finally {
                    pending -= 1;
                    if (!pending && !unavailable) status('saved');
                }
            });
            return queue;
        };

        return {
            get active() { return clone(records.get(activeId)); },
            list() {
                return [...records.values()].sort((a, b) => b.updatedAt - a.updatedAt).map(clone);
            },
            update(changes = {}) {
                const current = records.get(activeId);
                const updated = clone(current);
                if (Object.hasOwn(changes, 'title')) {
                    updated.title = typeof changes.title === 'string' ? changes.title.slice(0, 120) : '';
                }
                if (Object.hasOwn(changes, 'text')) updated.text = typeof changes.text === 'string' ? changes.text : '';
                if (updated.title === current.title && updated.text === current.text) return queue;
                updated.updatedAt = Math.max(Date.now(), current.updatedAt + 1);
                records.set(activeId, updated);
                return enqueue({ puts: [updated], setActive: true });
            },
            create(fields = {}) {
                const record = newRecord(fields);
                records.set(record.id, record);
                activeId = record.id;
                return enqueue({ adds: [record], setActive: true }).then(() => clone(record));
            },
            select(id) {
                const record = records.get(id);
                if (!record) return Promise.resolve(null);
                activeId = id;
                return enqueue({ setActive: true }).then(() => clone(record));
            },
            remove(id) {
                const removed = records.get(id);
                if (!removed) return Promise.resolve(null);
                records.delete(id);
                const adds = [];
                if (!records.size) {
                    const blank = newRecord();
                    records.set(blank.id, blank);
                    adds.push(blank);
                }
                const changedActive = id === activeId;
                if (changedActive) activeId = records.keys().next().value;
                return enqueue({ deletes: [id], adds, setActive: changedActive }).then(() => clone(removed));
            },
            restore(record) {
                if (!validRecord(record)) return Promise.reject(new TypeError('Invalid draft snapshot.'));
                if (records.has(record.id)) return Promise.resolve(clone(records.get(record.id)));
                const restored = copyRecord(record);
                records.set(restored.id, restored);
                return enqueue({ adds: [restored] }).then(() => clone(restored));
            },
            flush() { return queue; },
        };
    }

    window.FlowScriptLibrary = Object.freeze({ open, databaseName: DATABASE_NAME });
})();
