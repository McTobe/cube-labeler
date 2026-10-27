// Backups: the user's icons, settings and templates in one .cubebackup file, the same format
// as the desktop app's, so a backup made in either one restores in the other.

import * as storage from './storage.js';
import { app, updateSettings, makeBackup, openBackup, templateToDesktop, restoreFonts } from './app.js';
import { library, iconsForBackup, planIcons, restoreIcons, restoreIconLists } from './library.js';
import { templates, loadTemplates, findTemplate, putTemplate, freeTemplateName } from './templates.js';
import { downloadBlob } from './ui.js';

// Settings of the web version go in a backup with this prefix; the desktop app keeps them unused
const WEB_PREFIX = 'web_';
const WEB_SETTINGS = ['theme', 'match_printer_tape', 'bin_label_mm', 'default_tape_mm', 'default_font', 'bin_font', 'bin_bold_name'];
// AI settings shared with the desktop app (the keys never go in a backup)
const AI_SERVICES = ['gemini', 'openai', 'openrouter'];

export function localTime(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    + `${sign}${pad(Math.floor(Math.abs(offset) / 60))}:${pad(Math.abs(offset) % 60)}`;
}

async function backupSettings() {
  // Settings from a desktop backup that the web version has no use for are kept and passed on
  const desktop = await storage.load('desktopSettings', {});
  const { settings } = app.get();
  const out = { ...desktop, label_language: settings.label_language };
  for (const key of WEB_SETTINGS) out[WEB_PREFIX + key] = settings[key];
  out.ai_provider = settings.ai_provider;
  for (const [service, model] of Object.entries(settings.ai_models || {})) out[`${service}_model`] = model;
  out.icon_favourites = library.get().favourites;
  out.icon_recent = library.get().recent;
  return out;
}

// What goes in a backup, for makeBackup and backupDigest
export async function collectBackup(created = localTime()) {
  if (!templates.get().ready) await loadTemplates();
  return {
    created,
    icons: iconsForBackup(),
    settings: await backupSettings(),
    templates: await Promise.all(templates.get().mine.map(async (t) => ({ name: t.name, json: await templateToDesktop(t.item) }))),
    fonts: await storage.load('fonts', []),
  };
}

// "2026-10-24T21:05:09+02:00" -> "2026-10-24 21-05"
const fileStamp = (created) => created.slice(0, 16).replace('T', ' ').replace(':', '-');

export async function saveBackup() {
  const contents = await collectBackup();
  const data = await makeBackup(contents);
  downloadBlob(new Blob([data], { type: 'application/zip' }), `Cube Labeler backup ${fileStamp(contents.created)}.cubebackup`);
  await storage.save('lastBackup', contents.created);
  return { icons: library.get().user.length, templates: templates.get().mine.length };
}

export const lastBackup = () => storage.load('lastBackup', null);

// Reads a backup file and works out what restoring it would do
export async function readBackup(file) {
  if (!templates.get().ready) await loadTemplates();
  const opened = await openBackup(new Uint8Array(await file.arrayBuffer()));
  const iconPlan = planIcons(opened.icons);
  const templatePlan = { new: 0, conflicts: 0 };
  for (const t of opened.templates) templatePlan[findTemplate(t.name) ? 'conflicts' : 'new']++;
  return { ...opened, iconPlan, templatePlan };
}

// Restores the chosen parts ({icons, settings, templates, fonts}) of a read backup
export async function restoreBackup(opened, parts, onConflict) {
  const result = { icons: null, templates: null, settings: false, fonts: null };
  // Fonts first, so restored labels and templates find them
  if (parts.fonts && opened.fonts && opened.fonts.length) result.fonts = await restoreFonts(opened.fonts);
  if (parts.icons && opened.icons.length) result.icons = restoreIcons(opened.icons, onConflict);
  if (parts.templates && opened.templates.length) {
    const counts = { added: 0, replaced: 0, skipped: 0 };
    for (const t of opened.templates) {
      if (findTemplate(t.name)) {
        if (onConflict === 'skip') { counts.skipped++; continue; }
        if (onConflict === 'replace') { putTemplate(t.name, t.item); counts.replaced++; continue; }
        putTemplate(freeTemplateName(t.name), t.item);
      } else {
        putTemplate(t.name, t.item);
      }
      counts.added++;
    }
    result.templates = counts;
  }
  if (parts.settings && opened.settings) {
    const s = opened.settings;
    const desktop = {};
    const change = {};
    const models = { ...app.get().settings.ai_models };
    for (const [key, value] of Object.entries(s)) {
      const service = key.endsWith('_model') ? key.slice(0, -'_model'.length) : null;
      if (key.startsWith(WEB_PREFIX) && WEB_SETTINGS.includes(key.slice(WEB_PREFIX.length))) change[key.slice(WEB_PREFIX.length)] = value;
      else if (AI_SERVICES.includes(service)) {
        // Older desktop versions saved a text-only Gemini model that cannot draw
        if (typeof value === 'string' && value !== 'gemini-2.5-flash') models[service] = value;
      }
      else if (key === 'ai_provider') { if (AI_SERVICES.includes(value)) change.ai_provider = value; }
      else if (key !== 'icon_favourites' && key !== 'icon_recent' && key !== 'label_language') desktop[key] = value;
    }
    change.ai_models = models;
    if (typeof s.label_language === 'string') change.label_language = s.label_language;
    if (!['system', 'light', 'dark'].includes(change.theme)) delete change.theme;
    if ('match_printer_tape' in change) change.match_printer_tape = !!change.match_printer_tape;
    if ('bin_label_mm' in change && !(Number(change.bin_label_mm) >= 10)) change.bin_label_mm = null;
    if ('default_tape_mm' in change && !(Number(change.default_tape_mm) > 0)) change.default_tape_mm = null;
    if ('default_font' in change && typeof change.default_font !== 'string') change.default_font = null;
    if ('bin_font' in change && typeof change.bin_font !== 'string') change.bin_font = null;
    if ('bin_bold_name' in change) change.bin_bold_name = change.bin_bold_name !== false;
    await storage.save('desktopSettings', desktop);
    await updateSettings(change);
    restoreIconLists(s.icon_favourites, s.icon_recent);
    result.settings = true;
  }
  return result;
}
