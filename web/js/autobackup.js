// Automatic backups: a moment after the icons, templates or settings change, a backup is
// written to a folder the user picked, and only the newest few are kept. Picking a folder
// that Google Drive, OneDrive or Dropbox syncs puts the backups in the cloud, like the
// desktop app does. Writing to a folder needs Chrome or Edge on a computer.

import * as storage from './storage.js';
import { createStore } from './state.js';
import { app, boot, backupDigest, makeBackup } from './app.js';
import { library } from './library.js';
import { templates, loadTemplates } from './templates.js';
import { collectBackup } from './backup.js';

// Not the desktop app's "Cube Labeler backup ", so the two apps never prune each other's files
// when they share a folder
const PREFIX = 'Cube Labeler web backup ';
const EXTENSION = '.cubebackup';
const KEEP = 10;
const DELAY_MS = 3000;

export const autoBackup = createStore({
  supported: typeof window !== 'undefined' && 'showDirectoryPicker' in window,
  folder: null,  // the folder's FileSystemDirectoryHandle
  allowed: false,  // the browser lets the page write there right now
  last: null,  // when the last automatic backup was written
  error: '',
  busy: false,
});

let timer = null;

async function permission(folder, ask) {
  const options = { mode: 'readwrite' };
  if ((await folder.queryPermission(options)) === 'granted') return true;
  // Asking needs a click; without one the browser only says no
  return ask && (await folder.requestPermission(options)) === 'granted';
}

// "2026-10-24T21:05:09+02:00" -> "2026-10-24 210509", like the desktop app's names
const fileStamp = (created) => created.slice(0, 19).replace('T', ' ').replace(/:/g, '');

async function writeBackup(folder, created, data) {
  let name = `${PREFIX}${fileStamp(created)}${EXTENSION}`;
  for (let n = 2; await folder.getFileHandle(name).then(() => true, () => false); n++) {
    name = `${PREFIX}${fileStamp(created)}-${n}${EXTENSION}`;
  }
  const file = await folder.getFileHandle(name, { create: true });
  const out = await file.createWritable();
  await out.write(data);
  await out.close();
  // Keep the newest few; the names sort by time
  const names = [];
  for await (const [entry, handle] of folder.entries()) {
    if (handle.kind === 'file' && entry.startsWith(PREFIX) && entry.endsWith(EXTENSION)) names.push(entry);
  }
  names.sort().reverse();
  for (const old of names.slice(KEEP)) await folder.removeEntry(old).catch(() => {});
}

// Writes a backup now if anything changed since the last one (or always, with force)
export async function backupNow({ force = false, ask = false } = {}) {
  const { folder, busy } = autoBackup.get();
  // Never before the icons have loaded, or the backup would miss them
  if (!folder || busy || boot.get().phase !== 'ready' || !library.get().ready) return false;
  autoBackup.set({ busy: true });
  try {
    if (!(await permission(folder, ask))) {
      autoBackup.set({ allowed: false });
      return false;
    }
    autoBackup.set({ allowed: true });
    const contents = await collectBackup();
    const digest = await backupDigest(contents);
    if (!force && digest === (await storage.load('autoBackupDigest', ''))) return false;
    await writeBackup(folder, contents.created, await makeBackup(contents));
    await storage.save('autoBackupDigest', digest);
    await storage.save('autoBackupLast', contents.created);
    autoBackup.set({ last: contents.created, error: '' });
    return true;
  } catch (err) {
    autoBackup.set({ error: err && err.message ? err.message : String(err) });
    return false;
  } finally {
    autoBackup.set({ busy: false });
  }
}

function schedule() {
  if (!autoBackup.get().folder) return;
  clearTimeout(timer);
  timer = setTimeout(() => backupNow(), DELAY_MS);
}

// Asks for a folder and writes the first backup there. Must run from a click.
export async function chooseFolder() {
  let folder;
  try {
    folder = await window.showDirectoryPicker({ id: 'cube-labeler-backups', mode: 'readwrite', startIn: 'documents' });
  } catch (err) {
    if (err && err.name === 'AbortError') return false;
    throw err;
  }
  await storage.save('autoBackupFolder', folder);
  await storage.save('autoBackupDigest', '');
  autoBackup.set({ folder, error: '' });
  return backupNow({ force: true, ask: true });
}

// Lets the browser write to the folder again after a restart. Must run from a click.
export const allowFolder = () => backupNow({ ask: true });

export async function stopAutoBackup() {
  clearTimeout(timer);
  await storage.save('autoBackupFolder', null);
  autoBackup.set({ folder: null, allowed: false, error: '' });
}

// Loads the chosen folder and starts watching for changes once the app is ready
export async function startAutoBackup() {
  if (!autoBackup.get().supported) return;
  const [folder, last] = await Promise.all([storage.load('autoBackupFolder', null), storage.load('autoBackupLast', null)]);
  autoBackup.set({ folder, last });
  const watch = async () => {
    if (!templates.get().ready) await loadTemplates();
    let seen = { user: library.get().user, favourites: library.get().favourites, mine: templates.get().mine, settings: app.get().settings };
    const check = () => {
      const now = { user: library.get().user, favourites: library.get().favourites, mine: templates.get().mine, settings: app.get().settings };
      if (Object.keys(now).some((key) => now[key] !== seen[key])) schedule();
      seen = now;
    };
    library.subscribe(check);
    templates.subscribe(check);
    app.subscribe(check);
    if (folder) {
      autoBackup.set({ allowed: await permission(folder, false) });
      schedule();
    }
  };
  if (boot.get().phase === 'ready') watch();
  else {
    const stop = boot.subscribe(({ phase }) => { if (phase === 'ready') { stop(); watch(); } });
  }
}
