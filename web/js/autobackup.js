// Automatic backups: a moment after the icons, templates or settings change, a backup is
// written to a folder the user picked and/or uploaded to Google Drive, and only the newest
// few are kept. Picking a folder that Google Drive, OneDrive or Dropbox syncs also puts the
// backups in the cloud, like the desktop app does; writing to a folder needs Chrome or Edge
// on a computer. Signing in to Google Drive works on phones too.

import * as storage from './storage.js';
import { createStore } from './state.js';
import { app, boot, say, backupDigest, makeBackup } from './app.js';
import { library, deleteUserIcon, setFavourites } from './library.js';
import { templates, loadTemplates, deleteTemplate } from './templates.js';
import { collectBackup, readBackup, restoreBackup } from './backup.js';
import { history, loadHistory, historyIds } from './history.js';
import { drive, driveReady, loadDrive, uploadDriveBackup, continueDrive, listDriveBackups, downloadDriveBackup } from './gdrive.js';

// Not the desktop app's "Cube Labeler backup ", so the two apps never prune each other's files
// when they share a folder
const PREFIX = 'Cube Labeler web backup ';
const EXTENSION = '.cubebackup';
const KEEP = 3;
const DELAY_MS = 3000;

export const autoBackup = createStore({
  supported: typeof window !== 'undefined' && 'showDirectoryPicker' in window,
  folder: null,  // the folder's FileSystemDirectoryHandle
  allowed: false,  // the browser lets the page write there right now
  last: null,  // when the last automatic backup was written
  error: '',
  busy: false,
  driveLast: null,  // when the last backup went to Google Drive
  driveError: '',
  drivePending: false,  // a backup waits for the user to sign in to Google again
});

let timer = null;
let again = false;  // a change came in while a backup was being made

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

const failed = (err) => (err && err.message ? err.message : String(err));

async function toFolder(contents, digest, data, { force, ask }) {
  const { folder } = autoBackup.get();
  if (!(await permission(folder, ask))) {
    autoBackup.set({ allowed: false });
    return;
  }
  autoBackup.set({ allowed: true });
  if (!force && digest === (await storage.load('autoBackupDigest', ''))) return;
  try {
    await writeBackup(folder, contents.created, await data());
    await storage.save('autoBackupDigest', digest);
    await storage.save('autoBackupLast', contents.created);
    autoBackup.set({ last: contents.created, error: '' });
  } catch (err) {
    autoBackup.set({ error: failed(err) });
  }
}

const timeOfDay = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

// Brings this device in step with Google Drive. A newer backup from another device is restored
// first (it adds and replaces, it never deletes), then anything changed here is uploaded.
async function syncDrive({ force }) {
  // Google's token lasts an hour; after that syncing waits for a click on Continue
  if (!driveReady()) {
    autoBackup.set({ drivePending: true });
    return;
  }
  try {
    const [newest] = await listDriveBackups();
    if (newest && newest.id !== (await storage.load('driveSyncedId', null))) {
      const opened = await readBackup(await downloadDriveBackup(newest));
      // What was here at the last sync but is gone from the newer backup was deleted on the
      // other device; anything else only here is new on this one and stays
      const before = await storage.load('driveSyncedItems', null);
      await restoreBackup(opened, { icons: true, settings: true, templates: true, fonts: true, history: true }, 'replace',
        before && before.history ? before.history : null);
      if (before) {
        const icons = new Set(opened.icons.map((entry) => `user/${entry.file}`.toLowerCase()));
        const names = new Set(opened.templates.map((t) => t.name.trim().toLowerCase()));
        for (const icon of library.get().user) {
          if (!icons.has(icon.key.toLowerCase()) && before.icons.includes(icon.key.toLowerCase())) deleteUserIcon(icon.key);
        }
        for (const t of templates.get().mine) {
          if (!names.has(t.name.trim().toLowerCase()) && before.templates.includes(t.name.trim().toLowerCase())) deleteTemplate(t.name);
        }
      }
      if (opened.settings) setFavourites(opened.settings.icon_favourites);
      await storage.save('driveSyncedId', newest.id);
      await storage.save('driveBackupDigest', (newest.appProperties && newest.appProperties.digest) || '');
      await storage.save('driveBackupLast', newest.createdTime);
      autoBackup.set({ driveLast: newest.createdTime });
      say(`Synced from Google Drive (saved ${timeOfDay(newest.createdTime)}).`);
    }
    const contents = await collectBackup();
    const digest = await backupDigest(contents);
    if (force || digest !== (await storage.load('driveBackupDigest', ''))) {
      const name = `${PREFIX}${fileStamp(contents.created)}${EXTENSION}`;
      const id = await uploadDriveBackup(name, await makeBackup(contents), KEEP, digest);
      await storage.save('driveSyncedId', id);
      await storage.save('driveBackupDigest', digest);
      await storage.save('driveBackupLast', contents.created);
      autoBackup.set({ driveLast: contents.created });
    }
    await storage.save('driveSyncedItems', {
      icons: library.get().user.map((icon) => icon.key.toLowerCase()),
      templates: templates.get().mine.map((t) => t.name.trim().toLowerCase()),
      history: historyIds(),
    });
    autoBackup.set({ driveError: '', drivePending: false });
  } catch (err) {
    autoBackup.set({ driveError: failed(err), drivePending: !driveReady() });
  }
}

// Writes a backup now to the folder where anything changed since the last one (or always,
// with force), and syncs with Google Drive
export async function backupNow({ force = false, ask = false } = {}) {
  const { folder, busy } = autoBackup.get();
  const toDriveToo = drive.get().on;
  // Never before the icons have loaded, or the backup would miss them
  if ((!folder && !toDriveToo) || boot.get().phase !== 'ready' || !library.get().ready) return false;
  if (busy) { again = true; return false; }
  autoBackup.set({ busy: true });
  try {
    // Drive first: what comes from another device then goes in the folder backup too
    if (toDriveToo) await syncDrive({ force: false });
    if (folder) {
      const contents = await collectBackup();
      const digest = await backupDigest(contents);
      await toFolder(contents, digest, () => makeBackup(contents), { force, ask });
    }
    return true;
  } catch (err) {
    autoBackup.set({ error: failed(err) });
    return false;
  } finally {
    autoBackup.set({ busy: false });
    if (again) { again = false; schedule(); }
  }
}

// Signs in to Google again after the hour ran out and syncs. Must run from a click.
export async function continueDriveBackup() {
  await continueDrive();
  autoBackup.set({ driveError: '' });
  return backupNow();
}

// Right after signing in: takes what is in Drive first, then uploads what this device adds
export async function startDriveBackup() {
  await storage.save('driveSyncedId', null);
  await storage.save('driveBackupDigest', '');
  autoBackup.set({ driveError: '' });
  return backupNow();
}

function schedule() {
  if (!autoBackup.get().folder && !drive.get().on) return;
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
  const [folder, last, driveLast] = await Promise.all([
    storage.load('autoBackupFolder', null), storage.load('autoBackupLast', null), storage.load('driveBackupLast', null), loadDrive(),
  ]);
  autoBackup.set({ folder: autoBackup.get().supported ? folder : null, last, driveLast });
  const watch = async () => {
    if (!templates.get().ready) await loadTemplates();
    await loadHistory();
    const watched = () => ({
      user: library.get().user, favourites: library.get().favourites, mine: templates.get().mine, settings: app.get().settings,
      history: history.get().entries,
    });
    let seen = watched();
    const check = () => {
      const now = watched();
      if (Object.keys(now).some((key) => now[key] !== seen[key])) schedule();
      seen = now;
    };
    library.subscribe(check);
    templates.subscribe(check);
    app.subscribe(check);
    history.subscribe(check);
    if (autoBackup.get().folder) autoBackup.set({ allowed: await permission(folder, false) });
    schedule();
    // Coming back to the app (another tab, the phone's app switcher) picks up other devices' changes
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && drive.get().on) backupNow();
    });
  };
  if (boot.get().phase === 'ready') watch();
  else {
    const stop = boot.subscribe(({ phase }) => { if (phase === 'ready') { stop(); watch(); } });
  }
}
