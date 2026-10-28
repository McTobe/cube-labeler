// Everything the app keeps lives in this browser's IndexedDB: settings, the label being
// edited and added fonts. Nothing goes to the server. If the browser blocks storage (a private
// window can), the app still works and simply forgets on reload.

const DB_NAME = 'cube-labeler';
const STORE = 'kv';

// Tabs of the app share this storage but each keeps its own copy in memory. When one saves
// something that backups and sync carry, it tells the others, which read it again, so an
// older tab never saves or syncs over a newer change.
const SHARED_KEYS = new Set([
  'userIcons', 'iconFavourites', 'iconRecent', 'templates', 'settings', 'history', 'fonts', 'desktopSettings',
  'driveOn', 'driveEmail', 'driveKept',
]);
const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('cube-labeler-storage') : null;
const listeners = [];

// fn(key) runs when another tab saved key
export function onOtherTabSaved(fn) {
  listeners.push(fn);
}
if (channel) channel.onmessage = ({ data }) => { if (data && SHARED_KEYS.has(data.key)) listeners.forEach((fn) => fn(data.key)); };

let dbPromise = null;

function openDb() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
  return dbPromise;
}

async function run(mode, action) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const request = action(tx.objectStore(STORE));
    tx.oncomplete = () => resolve(request.result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

export async function load(key, fallback = undefined) {
  try {
    const value = await run('readonly', (store) => store.get(key));
    return value === undefined ? fallback : value;
  } catch (err) {
    console.warn(`Could not read ${key}:`, err);
    return fallback;
  }
}

export async function save(key, value) {
  try {
    await run('readwrite', (store) => store.put(value, key));
    if (channel && SHARED_KEYS.has(key)) channel.postMessage({ key });
  } catch (err) {
    console.warn(`Could not save ${key}:`, err);
  }
}

export async function remove(key) {
  try {
    await run('readwrite', (store) => store.delete(key));
  } catch (err) {
    console.warn(`Could not delete ${key}:`, err);
  }
}

// Asks the browser not to clear the app's data when the device runs low on space
export async function askToPersist() {
  try {
    if (navigator.storage && navigator.storage.persist && !(await navigator.storage.persisted())) {
      await navigator.storage.persist();
    }
  } catch (err) {
    // Not supported or refused; the data is still kept, just not guaranteed
  }
}
