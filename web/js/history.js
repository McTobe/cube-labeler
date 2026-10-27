// Print history: every label that printed, newest first, kept in this browser. A printed queue
// goes in as its separate labels, and printing the same label again moves it back to the top.
// Only the newest few are kept (Settings: 20, 50 or 200); pinned ones never drop off. The
// history goes with backups and Google Drive sync as a part of its own.

import * as storage from './storage.js';
import { createStore } from './state.js';
import { app, boot, sameLabel, itemTapeWidth, labelThumbnail, copiesOf } from './app.js';

export const HISTORY_SIZES = [20, 50, 200];
const DEFAULT_SIZE = 50;

export const history = createStore({
  ready: false,
  entries: [],  // [{id, mode, label or bin (+ font), tape_width_mm, printed, times, copies, pinned, changed, thumb}]
  thumbs: {},  // entry id -> thumbnail URL
});

let loading = null;
let nextId = 0;
const newId = () => `${Date.now().toString(36)}-${(nextId++).toString(36)}-${Math.random().toString(36).slice(2, 6)}`;

export function historySize() {
  const keep = app.get().settings.history_keep;
  return HISTORY_SIZES.includes(keep) ? keep : DEFAULT_SIZE;
}

// The label part of an entry or queue item: {mode, label} or {mode, bin, font}
export function entryItem(entry) {
  return entry.mode === 'bin' ? { mode: 'bin', bin: entry.bin, font: entry.font } : { mode: 'text', label: entry.label };
}

// The newest entries that are not pinned, as many as Settings keeps, and every pinned one
function trim(entries) {
  let room = historySize();
  return entries.filter((e) => e.pinned || room-- > 0);
}

function show(entries) {
  // Thumbnails of entries that are gone are let go
  const ids = new Set(entries.map((e) => e.id));
  const thumbs = { ...history.get().thumbs };
  for (const id of Object.keys(thumbs)) {
    if (!ids.has(id)) { URL.revokeObjectURL(thumbs[id]); delete thumbs[id]; }
  }
  for (const e of entries) {
    if (e.thumb && !thumbs[e.id]) thumbs[e.id] = URL.createObjectURL(new Blob([e.thumb], { type: 'image/png' }));
  }
  history.set({ entries, thumbs });
}

function keep(entries) {
  show(entries);
  storage.save('history', entries);
  makeThumbs();
}

export function loadHistory() {
  if (!loading) {
    loading = (async () => {
      show(await storage.load('history', []));
      history.set({ ready: true });
      if (boot.get().phase === 'ready') makeThumbs();
      else {
        const stop = boot.subscribe(({ phase }) => { if (phase === 'ready') { stop(); makeThumbs(); } });
      }
    })();
  }
  return loading;
}

// Entries restored from a backup come without their small pictures; they are drawn here
let drawing = false;
async function makeThumbs() {
  if (drawing || boot.get().phase !== 'ready') return;
  drawing = true;
  try {
    for (;;) {
      const entry = history.get().entries.find((e) => !e.thumb && !e.noThumb);
      if (!entry) break;
      let thumb = null;
      try {
        thumb = await labelThumbnail(entryItem(entry), 48);
      } catch (err) {
        console.warn('No thumbnail:', err);
      }
      const entries = history.get().entries.map((e) => (e.id === entry.id ? { ...e, thumb, noThumb: !thumb } : e));
      show(entries);
      storage.save('history', entries);
    }
  } finally {
    drawing = false;
  }
}

// Called after a confirmed print with the labels that came out (queue items keep their copies)
export async function recordPrinted(items) {
  await loadHistory();
  const printed = new Date().toISOString();
  let entries = [...history.get().entries];
  const added = [];
  for (const raw of items) {
    const item = structuredClone(entryItem(raw));
    const old = entries.find((e) => sameLabel(e, item)) || added.find((e) => sameLabel(e, item));
    if (old && added.includes(old)) { old.copies += copiesOf(raw); continue; }
    entries = entries.filter((e) => e !== old);
    added.push({
      ...item,
      id: old ? old.id : newId(),
      tape_width_mm: itemTapeWidth(item),
      printed,
      changed: printed,
      times: (old ? old.times || 1 : 0) + 1,
      copies: copiesOf(raw),
      pinned: old ? old.pinned : false,
      thumb: old ? old.thumb : null,
    });
  }
  keep(trim([...added, ...entries]));
}

export function setPinned(id, pinned) {
  const changed = new Date().toISOString();
  const entries = history.get().entries.map((e) => (e.id === id ? { ...e, pinned, changed } : e));
  keep(trim(entries));
}

export function removeEntry(id) {
  keep(history.get().entries.filter((e) => e.id !== id));
}

export function clearHistory({ pinnedToo = false } = {}) {
  keep(pinnedToo ? [] : history.get().entries.filter((e) => e.pinned));
}

// A smaller limit from Settings drops the oldest entries straight away
export function historySizeChanged() {
  if (history.get().ready) keep(trim(history.get().entries));
}

// --- Backups and sync ----------------------------------------------------------------------

// Pictures in labels are bytes; in the backup's JSON they are base64
function toJson(value) {
  if (value instanceof Uint8Array) {
    let text = '';
    for (let i = 0; i < value.length; i += 0x8000) text += String.fromCharCode(...value.subarray(i, i + 0x8000));
    return { $bytes: btoa(text) };
  }
  if (Array.isArray(value)) return value.map(toJson);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, toJson(v)]));
  return value;
}

function fromJson(value) {
  if (Array.isArray(value)) return value.map(fromJson);
  if (value && typeof value === 'object') {
    if (typeof value.$bytes === 'string') return Uint8Array.from(atob(value.$bytes), (c) => c.charCodeAt(0));
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, fromJson(v)]));
  }
  return value;
}

// The history as the JSON text a backup keeps; the thumbnails are drawn again on restore
export async function historyForBackup() {
  await loadHistory();
  const entries = history.get().entries.map(({ thumb, noThumb, ...entry }) => toJson(entry));
  return JSON.stringify({ version: 1, entries });
}

// The entries in a backup's history, or null when it has none or it cannot be read
export function readBackupHistory(text) {
  if (typeof text !== 'string') return null;
  try {
    const data = JSON.parse(text);
    if (!data || !Array.isArray(data.entries)) return null;
    return fromJson(data.entries).filter((e) => e && typeof e.id === 'string' && typeof e.printed === 'string'
      && ((e.mode === 'text' && e.label && typeof e.label.text === 'string') || (e.mode === 'bin' && e.bin && typeof e.bin.kind === 'string')));
  } catch (err) {
    return null;
  }
}

// Adds a backup's history to this one. An entry on both sides keeps the newer change; with
// gone (ids that were here at the last sync), entries the other device removed go here too.
// Returns how many entries were added or changed.
export async function restoreHistory(incoming, gone = null) {
  await loadHistory();
  const mine = new Map(history.get().entries.map((e) => [e.id, e]));
  const theirs = new Map(incoming.map((e) => [e.id, e]));
  let count = 0;
  const merged = [];
  for (const e of incoming) {
    const here = mine.get(e.id);
    if (here && (here.changed || here.printed) >= (e.changed || e.printed)) merged.push(here);
    else {
      merged.push({ ...e, thumb: here && sameLabel(here, e) ? here.thumb : null, noThumb: false });
      count++;
    }
  }
  for (const e of mine.values()) {
    if (theirs.has(e.id)) continue;
    if (gone && gone.includes(e.id)) { count++; continue; }
    merged.push(e);
  }
  // Newest first, and the same label printed on two devices kept once
  merged.sort((a, b) => (a.printed < b.printed ? 1 : a.printed > b.printed ? -1 : 0));
  const entries = [];
  for (const e of merged) {
    const twin = entries.find((x) => sameLabel(x, e));
    if (!twin) entries.push({ ...e });
    else twin.pinned = twin.pinned || e.pinned;
  }
  keep(trim(entries));
  return count;
}

export const historyIds = () => history.get().entries.map((e) => e.id);
