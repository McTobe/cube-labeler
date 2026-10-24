// The user's templates and the starting points. Templates are kept in IndexedDB as
// {name, item: {mode, label | bin}, saved}; files and backups use the desktop app's format.

import { createStore } from './state.js';
import * as storage from './storage.js';
import { currentItem, labelThumbnail, templatePresets, templateFromDesktop, templateToDesktop } from './app.js';

export const templates = createStore({ ready: false, mine: [], presets: [], thumbs: {} });

export async function loadTemplates() {
  const [mine, presets] = await Promise.all([storage.load('templates', []), templatePresets()]);
  templates.set({ ready: true, mine, presets });
}

const sameName = (a, b) => a.trim().toLowerCase() === b.trim().toLowerCase();

export function findTemplate(name) {
  return templates.get().mine.find((t) => sameName(t.name, name)) || null;
}

function saveMine(mine) {
  mine = [...mine].sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
  templates.set({ mine });
  storage.save('templates', mine);
}

function forgetThumb(name) {
  const { thumbs } = templates.get();
  const key = `mine:${name.toLowerCase()}`;
  if (thumbs[key]) {
    URL.revokeObjectURL(thumbs[key]);
    const next = { ...thumbs };
    delete next[key];
    templates.set({ thumbs: next });
  }
}

// Saves an item under a name, over a template with the same name (as the desktop app does)
export function putTemplate(name, item) {
  name = name.trim() || 'My template';
  forgetThumb(name);
  const mine = templates.get().mine.filter((t) => !sameName(t.name, name));
  saveMine([...mine, { name, item: structuredClone(item), saved: new Date().toISOString() }]);
  return name;
}

export const saveCurrentAsTemplate = (name) => putTemplate(name, currentItem());

export function deleteTemplate(name) {
  forgetThumb(name);
  saveMine(templates.get().mine.filter((t) => !sameName(t.name, name)));
}

// A free name like "Shelf (2)" for keeping both of two templates
export function freeTemplateName(name) {
  if (!findTemplate(name)) return name;
  for (let n = 2; ; n++) if (!findTemplate(`${name} (${n})`)) return `${name} (${n})`;
}

export async function thumbnail(key, item) {
  const { thumbs } = templates.get();
  if (thumbs[key]) return;
  try {
    const png = await labelThumbnail(item, 48);
    templates.set({ thumbs: { ...templates.get().thumbs, [key]: URL.createObjectURL(new Blob([png], { type: 'image/png' })) } });
  } catch (err) {
    console.warn('No thumbnail:', err);
  }
}

export async function templateFile(entry) {
  return new Blob([await templateToDesktop(entry.item)], { type: 'application/json' });
}

export async function readTemplateFile(file) {
  return templateFromDesktop(new Uint8Array(await file.arrayBuffer()));
}
