// The icon library: built-in icons (served as files, listed in icons/library.json) and the
// user's own icons (kept in IndexedDB). Search, favourites and recently used work like the
// desktop app's core/icon_manager.py, with the same keys ("folder/file.png", "user/file.png")
// so backups can move between the two.

import { createStore } from './state.js';
import * as storage from './storage.js';

export const ALL = 'All';
export const FAVOURITES = 'Favourites';
export const RECENT = 'Recently used';
export const USER_CATEGORY = 'My Icons';
const RECENT_LIMIT = 12;

export const library = createStore({
  ready: false,
  categories: [],  // built-in categories, in order
  builtIn: [],  // [{key, id, title, category, file, keywords}]
  user: [],  // [{key, id, title, category, keywords, png: Uint8Array, original?, edit?, touch?}]
  favourites: [],
  recent: [],
});

const userUrls = new Map();  // key -> object URL of a user icon

export async function loadLibrary() {
  const [response, user, favourites, recent] = await Promise.all([
    fetch('icons/library.json'),
    storage.load('userIcons', []),
    storage.load('iconFavourites', []),
    storage.load('iconRecent', []),
  ]);
  const data = await response.json();
  library.set({ ready: true, categories: data.categories, builtIn: data.icons, user, favourites, recent });
}

export const views = () => [ALL, FAVOURITES, RECENT, ...library.get().categories, USER_CATEGORY];

function allIcons() {
  const { builtIn, user } = library.get();
  return [...builtIn, ...user.map((icon) => ({ ...icon, user: true }))];
}

export function iconByKey(key) {
  return allIcons().find((icon) => icon.key === key) || null;
}

export function listIcons(view = ALL, query = '') {
  const q = query.trim().toLowerCase();
  const icons = allIcons();
  let pool;
  if (view === RECENT) {
    const byKey = new Map(icons.map((icon) => [icon.key, icon]));
    pool = library.get().recent.map((key) => byKey.get(key)).filter(Boolean);
  } else if (view === FAVOURITES) {
    const favourites = new Set(library.get().favourites);
    pool = icons.filter((icon) => favourites.has(icon.key));
  } else if (view === USER_CATEGORY) {
    pool = icons.filter((icon) => icon.user);
  } else if (view !== ALL) {
    pool = icons.filter((icon) => icon.category === view);
  } else {
    pool = icons;
  }
  if (q) {
    pool = pool.filter((icon) => icon.id.toLowerCase().includes(q) || icon.title.toLowerCase().includes(q)
      || icon.keywords.some((kw) => kw.toLowerCase().includes(q)));
  }
  if (view !== RECENT) {
    pool = [...pool].sort((a, b) => (Number(!!a.user) - Number(!!b.user)) || a.title.toLowerCase().localeCompare(b.title.toLowerCase()));
  }
  return pool;
}

export function viewCount(view) {
  return listIcons(view).length;
}

export function iconUrl(icon) {
  if (!icon.user) return icon.file;
  let url = userUrls.get(icon.key);
  if (!url) {
    url = URL.createObjectURL(new Blob([icon.png], { type: 'image/png' }));
    userUrls.set(icon.key, url);
  }
  return url;
}

export async function iconBytes(icon) {
  if (icon.user) return icon.png;
  const response = await fetch(icon.file);
  return new Uint8Array(await response.arrayBuffer());
}

function forgetUrl(key) {
  const url = userUrls.get(key);
  if (url) URL.revokeObjectURL(url);
  userUrls.delete(key);
}

export function isFavourite(icon) {
  return library.get().favourites.includes(icon.key);
}

export function toggleFavourite(icon) {
  const { favourites } = library.get();
  const next = favourites.includes(icon.key) ? favourites.filter((k) => k !== icon.key) : [...favourites, icon.key];
  library.set({ favourites: next });
  storage.save('iconFavourites', next);
}

export function markUsed(icon) {
  const recent = [icon.key, ...library.get().recent.filter((k) => k !== icon.key)].slice(0, RECENT_LIMIT);
  library.set({ recent });
  storage.save('iconRecent', recent);
}

export function parseKeywords(text) {
  return text.split(',').map((w) => w.trim().toLowerCase()).filter(Boolean);
}

// A file name for a new icon called `name`, not used by any icon yet (like free_icon_path)
function freeKey(name) {
  const safe = name.trim().replace(/ /g, '_').replace(/[^\p{L}\p{N}_-]/gu, '').replace(/^_+|_+$/g, '') || 'custom_icon';
  const taken = new Set(library.get().user.map((icon) => icon.key));
  let key = `user/${safe}.png`;
  for (let n = 1; taken.has(key); n++) key = `user/${safe}_${n}.png`;
  return key;
}

function saveUser(user) {
  library.set({ user });
  storage.save('userIcons', user);
}

const builtInCategory = (category) => (library.get().categories.includes(category) ? category : USER_CATEGORY);

// Saves a new icon of the user's; with the original and settings it can be edited again later
export function saveUserIcon({ title, category, keywords = [], png, original = null, edit = null, touch = null }) {
  const key = freeKey(title);
  const id = key.slice(5, -4);
  const icon = {
    key, id, title: title.trim() || id.replace(/_/g, ' '), category: builtInCategory(category),
    keywords, png, original, edit, touch,
  };
  saveUser([...library.get().user, icon]);
  return { ...icon, user: true };
}

// Changes one of the user's icons; the key stays, so labels and favourites keep pointing at it
export function updateUserIcon(key, change) {
  if ('png' in change) forgetUrl(key);
  const user = library.get().user.map((icon) => (icon.key === key ? {
    ...icon,
    ...change,
    ...(change.category !== undefined ? { category: builtInCategory(change.category) } : {}),
    ...(change.title !== undefined ? { title: change.title.trim() || icon.id.replace(/_/g, ' ') } : {}),
  } : icon));
  saveUser(user);
  const updated = user.find((icon) => icon.key === key);
  return updated ? { ...updated, user: true } : null;
}

export function deleteUserIcon(key) {
  forgetUrl(key);
  saveUser(library.get().user.filter((icon) => icon.key !== key));
  const { favourites, recent } = library.get();
  library.set({ favourites: favourites.filter((k) => k !== key), recent: recent.filter((k) => k !== key) });
  storage.save('iconFavourites', library.get().favourites);
  storage.save('iconRecent', library.get().recent);
}

// --- Backups ------------------------------------------------------------------------------------

const sameBytes = (a, b) => a && b && a.length === b.length && a.every((v, i) => v === b[i]);

// The user's icons the way a desktop backup lists them
export function iconsForBackup() {
  const { user, favourites } = library.get();
  return user.map((icon) => ({
    file: icon.key.slice(5),
    meta: { title: icon.title, category: icon.category, keywords: icon.keywords, ...(icon.original && icon.edit ? { edit: icon.edit } : {}) },
    favourite: favourites.includes(icon.key),
    icon: icon.png,
    original: icon.original && icon.edit ? icon.original : null,
    touch: icon.original && icon.edit ? icon.touch : null,
  }));
}

// How the icons of a backup line up with the ones here: new, the same, or a different icon by the same name
export function planIcons(entries) {
  const byKey = new Map(library.get().user.map((icon) => [icon.key.toLowerCase(), icon]));
  const plan = { new: 0, same: 0, conflicts: 0 };
  for (const entry of entries) {
    const here = byKey.get(`user/${entry.file}`.toLowerCase());
    if (!here) plan.new++;
    else if (sameBytes(here.png, entry.icon)) plan.same++;
    else plan.conflicts++;
  }
  return plan;
}

// Adds a backup's icons. onConflict: 'skip', 'replace' or 'keep_both'. Returns how many were added.
export function restoreIcons(entries, onConflict) {
  let user = [...library.get().user];
  const favourites = new Set(library.get().favourites);
  const counts = { added: 0, replaced: 0, skipped: 0 };
  const keys = () => new Set(user.map((icon) => icon.key.toLowerCase()));
  for (const entry of entries) {
    let key = `user/${entry.file}`;
    const index = user.findIndex((icon) => icon.key.toLowerCase() === key.toLowerCase());
    const meta = entry.meta || {};
    const stem = entry.file.replace(/\.png$/i, '');
    const icon = {
      key, id: stem, title: meta.title || stem.replace(/_/g, ' '),
      category: library.get().categories.includes(meta.category) ? meta.category : USER_CATEGORY,
      keywords: Array.isArray(meta.keywords) ? meta.keywords.map(String) : [],
      png: entry.icon, original: entry.original || null, edit: entry.original ? meta.edit || null : null, touch: entry.touch || null,
    };
    if (index >= 0) {
      if (sameBytes(user[index].png, entry.icon)) continue;
      if (onConflict === 'skip') { counts.skipped++; continue; }
      if (onConflict === 'replace') {
        forgetUrl(user[index].key);
        icon.key = user[index].key;
        user[index] = icon;
        counts.replaced++;
        if (entry.favourite) favourites.add(icon.key);
        continue;
      }
      const taken = keys();
      for (let n = 1; taken.has(key.toLowerCase()); n++) key = `user/${stem}_${n}.png`;
      Object.assign(icon, { key, id: key.slice(5, -4) });
    }
    user.push(icon);
    counts.added++;
    if (entry.favourite) favourites.add(icon.key);
  }
  saveUser(user);
  library.set({ favourites: [...favourites] });
  storage.save('iconFavourites', library.get().favourites);
  return counts;
}

// Favourites and recently used from a backup's settings, for the icons that exist here
export function restoreIconLists(favouriteKeys, recentKeys) {
  const known = new Set([...library.get().builtIn, ...library.get().user].map((icon) => icon.key));
  if (Array.isArray(favouriteKeys)) {
    const favourites = [...new Set([...library.get().favourites, ...favouriteKeys.filter((k) => known.has(k))])];
    library.set({ favourites });
    storage.save('iconFavourites', favourites);
  }
  if (Array.isArray(recentKeys)) {
    const recent = recentKeys.filter((k) => known.has(k)).slice(0, RECENT_LIMIT);
    library.set({ recent });
    storage.save('iconRecent', recent);
  }
}
