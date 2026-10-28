// Automatic backups: a moment after the icons, templates or settings change, a backup is
// written to a folder the user picked and/or uploaded to Google Drive, and only the newest
// few are kept. Picking a folder that Google Drive, OneDrive or Dropbox syncs also puts the
// backups in the cloud, like the desktop app does; writing to a folder needs Chrome or Edge
// on a computer. Signing in to Google Drive works on phones too.

import * as storage from './storage.js';
import { createStore } from './state.js';
import { app, boot, say, backupDigest, backupItemDigests, makeBackup, reloadSettings, reloadFonts } from './app.js';
import { library, deleteUserIcon, setFavourites, restoreIcons, reloadUserIcons } from './library.js';
import { templates, loadTemplates, deleteTemplate, putTemplate, freeTemplateName, reloadTemplates } from './templates.js';
import { collectBackup, readBackup, restoreBackup, localTime } from './backup.js';
import { history, loadHistory, historyIds, reloadHistory } from './history.js';
import {
  drive, driveReady, loadDrive, uploadDriveBackup, trashDriveBackup, continueDrive, listDriveBackups, downloadDriveBackup,
} from './gdrive.js';
import { planItems, planSettings, baseFor, pruneBackups } from './syncplan.js';

// Not the desktop app's "Cube Labeler backup ", so the two apps never prune each other's files
// when they share a folder
const PREFIX = 'Cube Labeler web backup ';
const EXTENSION = '.cubebackup';
const KEEP = 3;
const DELAY_MS = 3000;
// Google Drive keeps the newest few and one a day for two weeks (see pruneBackups)
const DRIVE_RECENT = 10;
const DRIVE_DAYS = 14;
// Only one tab of the app syncs at a time
const LOCK = 'cube-labeler-sync';
const SYNC_LOG = 20;

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
  offline: false,  // the last sync could not reach Google
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

// What kind of device this is, for the list of versions in Drive
function deviceName() {
  const ua = navigator.userAgent;
  if (/Android/i.test(ua)) return 'Android';
  if (/iPhone/i.test(ua)) return 'iPhone';
  if (/iPad/i.test(ua)) return 'iPad';
  if (/CrOS/i.test(ua)) return 'Chromebook';
  if (/Windows/i.test(ua)) return 'Windows';
  if (/Mac/i.test(ua)) return 'Mac';
  if (/Linux/i.test(ua)) return 'Linux';
  return 'Browser';
}

const offline = (err) => (typeof navigator !== 'undefined' && navigator.onLine === false)
  || (err instanceof TypeError && /fetch|network/i.test(err.message));
const sideOf = (digests, part) => (part === 'templates'
  ? Object.fromEntries(Object.entries(digests.templates).map(([k, v]) => [k, v.hash])) : digests[part]);
const baseSide = (base, part) => base && { l: sideOf(base.l, part), r: sideOf(base.r, part) };

// Brings in a newer backup from Drive, item by item (see syncplan.js), and returns what changed.
// base: both sides' fingerprints at the last sync, or null (then nothing is deleted).
async function mergeFromDrive(opened, base, from) {
  const contents = await collectBackup();
  const local = await backupItemDigests(contents);
  const remote = opened.digests;
  // A copy of this device as it was, so the sync can be undone here
  await storage.save('syncUndo', { created: contents.created, data: await makeBackup(contents) });
  const counts = { added: 0, changed: 0, removed: 0, copies: 0, settings: 0 };
  const copyName = (name) => `${name} (${from})`;

  // Icons
  const icons = planItems(local.icons, remote.icons, baseSide(base, 'icons'));
  const byFile = new Map(opened.icons.map((entry) => [entry.file.toLowerCase(), entry]));
  const take = icons.take.map((k) => byFile.get(k)).filter(Boolean);
  const copies = icons.conflict.map((k) => byFile.get(k)).filter(Boolean)
    .map((entry) => ({ ...entry, meta: { ...entry.meta, title: copyName(entry.meta.title || entry.file.replace(/\.png$/i, '').replace(/_/g, ' ')) } }));
  if (take.length) {
    const done = restoreIcons(take, 'replace');
    counts.added += done.added;
    counts.changed += done.replaced;
  }
  if (copies.length) counts.copies += restoreIcons(copies, 'keep_both').added;
  for (const key of icons.drop) {
    const icon = library.get().user.find((i) => i.key.slice(5).toLowerCase() === key);
    if (icon) { deleteUserIcon(icon.key); counts.removed++; }
  }

  // Templates (keyed by their file name, like the backup keeps them)
  const tplans = planItems(sideOf(local, 'templates'), sideOf(remote, 'templates'), baseSide(base, 'templates'));
  const byStem = new Map(opened.templates.map((t) => [t.name.toLowerCase(), t]));
  for (const key of tplans.take) {
    const t = byStem.get(key);
    if (!t) continue;
    const mine = local.templates[key];
    putTemplate(mine ? mine.name : t.name, t.item);
    counts[mine ? 'changed' : 'added']++;
  }
  for (const key of tplans.conflict) {
    const t = byStem.get(key);
    if (t) { putTemplate(freeTemplateName(copyName(t.name)), t.item); counts.copies++; }
  }
  for (const key of tplans.drop) {
    const mine = local.templates[key];
    if (mine) { deleteTemplate(mine.name); counts.removed++; }
  }

  // Settings, one by one; what is not taken from Drive stays as it is here
  let settings = null;
  if (opened.settings) {
    const takeKeys = planSettings(local.settings, remote.settings, baseSide(base, 'settings'))
      .filter((key) => key !== 'icon_recent');
    settings = { ...contents.settings };
    for (const key of takeKeys) settings[key] = opened.settings[key];
    // Tape counts always add up from both devices (see mergeRolls)
    if ('web_tape_rolls' in opened.settings) settings.web_tape_rolls = opened.settings.web_tape_rolls;
    counts.settings = takeKeys.length;
  }
  const result = await restoreBackup({ ...opened, settings }, { settings: !!settings, fonts: true, history: true }, 'skip',
    base ? base.history : null);
  if (settings) setFavourites(settings.icon_favourites);
  counts.history = result.history || 0;
  counts.fonts = result.fonts || 0;
  return counts;
}

function describe(counts) {
  const parts = [];
  const n = (count, one, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;
  if (counts.added) parts.push(`${n(counts.added, 'thing')} added`);
  if (counts.changed) parts.push(`${counts.changed} changed`);
  if (counts.removed) parts.push(`${counts.removed} removed`);
  if (counts.copies) parts.push(`${n(counts.copies, 'copy', 'copies')} kept of things changed on both devices`);
  if (counts.settings) parts.push(`${n(counts.settings, 'setting')} changed`);
  if (counts.fonts) parts.push(`${n(counts.fonts, 'font')} added`);
  if (counts.history) parts.push(`${n(counts.history, 'printed label')} in the history`);
  return parts.join(', ');
}

async function logSync(entry) {
  const log = await storage.load('syncLog', []);
  await storage.save('syncLog', [entry, ...log].slice(0, SYNC_LOG));
}

// Brings this device in step with Google Drive. A newer backup from another device is merged in
// first, then anything changed here is uploaded.
async function syncDrive({ force }) {
  // Google's token lasts an hour; after that syncing waits for a click on Continue
  if (!driveReady()) {
    autoBackup.set({ drivePending: true });
    return;
  }
  try {
    const files = await listDriveBackups();
    const [newest] = files;
    const synced = await storage.load('driveSyncedId', null);
    const account = drive.get().email || '';
    let base = await storage.load('driveSyncBase', null);
    let remoteDigests = base ? base.r : null;
    let remoteHistory = base ? base.history : [];
    if (newest && newest.id !== synced) {
      const opened = await readBackup(await downloadDriveBackup(newest));
      const start = baseFor(base, synced, newest, account, files);
      if (start.how === 'none') base = null;
      if (start.how === 'parent') {
        // Two devices synced at once: merge from the backup both of them started from
        const parent = files.find((f) => f.id === start.id);
        const p = await readBackup(await downloadDriveBackup(parent)).catch(() => null);
        base = p ? { l: p.digests, r: p.digests, history: (p.history || []).map((e) => e.id) } : null;
      }
      const from = (newest.appProperties && newest.appProperties.device) || 'other device';
      const counts = await mergeFromDrive(opened, base, from);
      remoteDigests = opened.digests;
      remoteHistory = (opened.history || []).map((e) => e.id);
      await storage.save('driveSyncedId', newest.id);
      await storage.save('driveBackupDigest', (newest.appProperties && newest.appProperties.digest) || '');
      await storage.save('driveBackupLast', newest.createdTime);
      autoBackup.set({ driveLast: newest.createdTime });
      const what = describe(counts);
      if (what) {
        await logSync({ at: localTime(), from, what, file: newest.id });
        say(`Synced from Google Drive: ${what}.`);
      }
    }
    const contents = await collectBackup();
    const digest = await backupDigest(contents);
    const mine = await backupItemDigests(contents);
    let syncedId = newest ? newest.id : null;
    if (force || digest !== (await storage.load('driveBackupDigest', ''))) {
      const name = `${PREFIX}${fileStamp(contents.created)}${EXTENSION}`;
      const id = await uploadDriveBackup(name, await makeBackup(contents), {
        digest, parent: newest ? newest.id : null, device: deviceName(), icons: contents.icons.length, templates: contents.templates.length,
      });
      syncedId = id;
      remoteDigests = mine;
      remoteHistory = historyIds();
      await storage.save('driveSyncedId', id);
      await storage.save('driveBackupDigest', digest);
      await storage.save('driveBackupLast', contents.created);
      autoBackup.set({ driveLast: contents.created });
      // Another device may have uploaded while this one did: then sync once more to merge it
      const after = await listDriveBackups();
      if (after.length && after[0].id !== id) again = true;
      for (const old of pruneBackups(after, { recent: DRIVE_RECENT, days: DRIVE_DAYS })) await trashDriveBackup(old).catch(() => {});
    }
    // Both sides as they are now, for the next sync to tell who changed what
    const historyNow = historyIds();
    await storage.save('driveSyncBase', {
      account,
      file: syncedId,
      l: mine,
      r: remoteDigests || mine,
      history: historyNow.filter((id) => remoteHistory.includes(id)),
    });
    await storage.save('driveCheckedAt', localTime());
    autoBackup.set({ driveError: '', drivePending: false, offline: false });
  } catch (err) {
    if (offline(err)) autoBackup.set({ driveError: 'Offline. Sync goes on by itself when the internet is back.', offline: true });
    else autoBackup.set({ driveError: failed(err), drivePending: !driveReady(), offline: false });
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
    await whileLocked(async () => {
      // What other tabs saved is read first, so this tab never syncs an older copy
      await reloadPending();
      // Drive first: what comes from another device then goes in the folder backup too
      if (toDriveToo) await syncDrive({ force: false });
      if (folder) {
        const contents = await collectBackup();
        const digest = await backupDigest(contents);
        await toFolder(contents, digest, () => makeBackup(contents), { force, ask });
      }
    });
    return true;
  } catch (err) {
    autoBackup.set({ error: failed(err) });
    return false;
  } finally {
    autoBackup.set({ busy: false });
    if (again) { again = false; schedule(); }
  }
}

// Runs fn while no other tab of the app syncs (Web Locks; a browser without them just runs it)
function whileLocked(fn) {
  if (typeof navigator !== 'undefined' && navigator.locks) return navigator.locks.request(LOCK, fn);
  return fn();
}

// Parts another tab saved, read again here a moment later. While they are read, the changes
// they make to the stores do not count as changes of this tab's own.
const RELOADERS = {
  userIcons: reloadUserIcons, iconFavourites: reloadUserIcons, iconRecent: reloadUserIcons,
  templates: reloadTemplates, settings: reloadSettings, history: reloadHistory, fonts: reloadFonts, desktopSettings: null,
  driveOn: loadDrive, driveEmail: loadDrive, driveKept: loadDrive,
};
const pending = new Set();
let reloadTimer = null;
let quiet = 0;

async function reloadPending() {
  clearTimeout(reloadTimer);
  const todo = [...new Set([...pending].map((key) => RELOADERS[key]).filter(Boolean))];
  pending.clear();
  if (!todo.length) return;
  quiet++;
  try {
    for (const reload of todo) await reload();
  } catch (err) {
    console.warn('Reading what another tab saved:', err);
  } finally {
    quiet--;
  }
}

storage.onOtherTabSaved((key) => {
  pending.add(key);
  clearTimeout(reloadTimer);
  reloadTimer = setTimeout(reloadPending, 150);
});

// Signs in to Google again after the hour ran out and syncs. Must run from a click.
export async function continueDriveBackup() {
  await continueDrive();
  autoBackup.set({ driveError: '' });
  return backupNow();
}

// Right after signing in: takes what is in Drive first, then uploads what this device adds
export async function startDriveBackup() {
  await storage.save('driveSyncedId', null);
  await storage.save('driveSyncBase', null);
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
      history: history.get().entries, fonts: app.get().fonts,
    });
    let seen = watched();
    const check = () => {
      const now = watched();
      // Reading another tab's changes is not a change of this tab's own (that tab syncs them)
      if (!quiet && Object.keys(now).some((key) => now[key] !== seen[key])) schedule();
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
    // Back online: sync what waited
    window.addEventListener('online', () => { if (drive.get().on) backupNow(); });
  };
  if (boot.get().phase === 'ready') watch();
  else {
    const stop = boot.subscribe(({ phase }) => { if (phase === 'ready') { stop(); watch(); } });
  }
}
