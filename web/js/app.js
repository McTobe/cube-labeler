// App state and the things the pages do with it: start Python, render, print, keep settings.
// Pages read the stores with useStore() and call these functions; none of them touch the
// printer or Python directly.

import { createStore } from './state.js';
import { startPython } from './python.js';
import * as storage from './storage.js';
import { loadLibrary } from './library.js';
import { SerialTransport, queryStatus, printRaster, feedTape, errorMessage } from '../printer.js';

const RENDER_DELAY_MS = 120;
const SAVE_DELAY_MS = 400;
export const FEED_LENGTH_MM = 25;

export const DEFAULT_LABEL = {
  text: 'Cube Labeler',
  font_name: 'Arimo',
  tape_width_mm: 12,
  auto_fit_font: true,
  fixed_font_size: 36,
  alignment: 'center',
  frame: 'none',
  qr_enabled: false,
  qr_data: '',
  qr_position: 'left',
  qr_scale: 0.95,
  image: null,  // {name, data: Uint8Array}
  image_position: 'left',
  image_scale: 1.0,
  fixed_width_mm: null,
  font_scale: 100,
  line_spacing: 1.2,
  h_padding: 8,
  stroke_width: 0,
  threshold: 100,
  tape_bg_color: '#FFFFFF',
  tape_fg_color: '#000000',
  show_guides: false,
  show_rulers: false,
};

export const DEFAULT_SETTINGS = {
  ai_provider: 'gemini',
  ai_models: {},
  theme: 'system',  // 'system', 'light', 'dark'
  match_printer_tape: true,
  label_language: 'en',  // kept for the desktop app's backups; the web version is in English
  bin_label_mm: null,  // the user's own bin label length for Reset, instead of 32 mm
  default_tape_mm: null,  // tape width a reset text label goes back to, instead of 12 mm
  default_font: null,  // font a reset text label goes back to, instead of Arimo
  bin_font: null,  // font for all text on bin labels, instead of BIN_FONT
};

export const BIN_FONT = 'Arimo SemiBold';

export const MAX_TAPE_MM = 499;
export const BIN_TAPE_MM = 12;

// Startup: 'loading' with a progress text, then 'ready', or 'failed' with the reason
export const boot = createStore({ phase: 'loading', text: 'Starting...', error: null });

export const app = createStore({
  mode: 'text',  // what the Label page edits: 'text' or 'bin'
  label: DEFAULT_LABEL,
  bin: null,  // {kind: 'fastener' or 'component', fastener: {...}, component: {...}}
  binNames: { fastener: [], component: [] },
  languages: [['en', 'English']],
  queue: [],  // [{id, mode, label, copies} or {id, mode, bin, copies}], printed as one strip
  queueUndo: null,  // {queue, text}: the queue before the last removal, while it can be undone
  queueRender: null,  // like render, for the whole queue
  previewDots: false,  // the label page's preview shows the printer's dots instead of the tape
  queuePrinted: 0,  // labels in the last printed queue, until the user keeps or clears it
  thumbs: {},  // queue item id -> preview URL
  settings: DEFAULT_SETTINGS,
  tapeWidths: [12, 9, 6, 3.5],
  fonts: [],
  render: null,  // {previewUrl, dotsUrl, raster, metrics, tape_width_mm}
  renderError: null,
  status: { text: '', error: false },
});

export const printer = createStore({
  supported: SerialTransport.isSupported(),
  transport: null,
  info: null,  // the last status read: model, tape, errors...
  state: 'none',  // 'none', 'paired', 'busy', 'ready', 'error'
  busy: false,
  message: '',
});

let py = null;

let saidAt = 0;
let sayTimer = null;
// How long a message stays up; errors stay until they are closed or replaced
const SAY_SECONDS = 6;

export function say(text, error = false) {
  saidAt = Date.now();
  clearTimeout(sayTimer);
  app.set({ status: { text, error, id: saidAt } });
  if (!error) sayTimer = setTimeout(hush, SAY_SECONDS * 1000);
}

export function hush() {
  clearTimeout(sayTimer);
  if (app.get().status.text) app.set({ status: { text: '', error: false } });
}

// A message belongs to the page it was said on; one said just before moving to another page
// (like "Opened Shelf A") goes along
export function pageChanged() {
  if (Date.now() - saidAt > 1000 && app.get().status.text) app.set({ status: { text: '', error: false } });
}

// --- Start ---------------------------------------------------------------------------------

export async function start() {
  const [settings, label, fonts, mode, bin, queue] = await Promise.all([
    storage.load('settings', {}),
    storage.load('label', {}),
    storage.load('fonts', []),
    storage.load('mode', 'text'),
    storage.load('bin', null),
    storage.load('queue', []),
  ]);
  app.set({
    settings: { ...DEFAULT_SETTINGS, ...settings },
    // The printable-area guides no longer have a switch, so a label saved with them on drops them
    label: { ...DEFAULT_LABEL, ...label, show_guides: false },
    mode,
    bin,
    queue: mergeCopies(queue),
  });
  applyTheme(app.get().settings.theme);
  storage.askToPersist();
  loadLibrary().catch((err) => console.warn('Icon library', err));

  if (printer.get().supported) {
    try {
      const transport = await SerialTransport.remembered();
      if (transport) printer.set({ transport, state: 'paired', message: 'Paired earlier. Check status to wake it.' });
    } catch (err) {
      // No permission to list ports yet; the user connects from the printer menu
    }
  }

  const python = startPython((text) => boot.set({ text }));
  try {
    await python.ready;
  } catch (err) {
    boot.set({ phase: 'failed', error: errorMessage(err) });
    return;
  }
  py = python.py;

  // Fonts added on an earlier visit live in IndexedDB; Python needs them on its own disk again
  for (const font of fonts) {
    try { await py.add_font(font.filename, font.data); } catch (err) { console.warn(err); }
  }
  // Bin labels are in English; a language from a desktop backup is kept for the desktop app only
  const lang = 'en';
  const [tapeWidths, fontNames, binNames, languages, binDefaults] = await Promise.all([
    py.tape_widths(), py.font_names(), py.bin_name_suggestions(lang), py.label_languages(), py.bin_defaults(lang),
  ]);
  const current = app.get().label;
  const binState = app.get().bin || { kind: 'fastener', ...binDefaults };
  app.set({
    tapeWidths,
    fonts: fontNames,
    binNames,
    languages,
    bin: binState,
    label: fontNames.includes(current.font_name) ? current : { ...current, font_name: fontNames.includes('Arimo') ? 'Arimo' : fontNames[0] },
  });
  boot.set({ phase: 'ready' });
  await renderNow();
  app.get().queue.forEach(makeThumb);
}

export function applyTheme(theme) {
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = getComputedStyle(document.documentElement).getPropertyValue('--bar').trim() || '#1f2430';
}

export async function updateSettings(change) {
  const settings = { ...app.get().settings, ...change };
  app.set({ settings });
  storage.save('settings', settings);
  if ('theme' in change) applyTheme(settings.theme);
  if ('bin_font' in change) {
    queueRenderStale = true;
    if (app.get().mode === 'bin') renderNow();
  }
}

// --- Editing and rendering -----------------------------------------------------------------

let renderTimer = null;
let saveTimer = null;
let rendering = null;  // the render in flight
let renderAgain = false;

function changed(key) {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => storage.save(key, app.get()[key]), SAVE_DELAY_MS);
  clearTimeout(renderTimer);
  renderTimer = setTimeout(renderNow, RENDER_DELAY_MS);
}

export function updateLabel(change) {
  app.set({ label: { ...app.get().label, ...change } });
  changed('label');
}

// change applies to the bin label being edited (fastener or part); {kind} switches between them
export function updateBin(change) {
  const bin = app.get().bin;
  if ('kind' in change) {
    app.set({ bin: { ...bin, kind: change.kind } });
  } else {
    app.set({ bin: { ...bin, [bin.kind]: { ...bin[bin.kind], ...change } } });
  }
  changed('bin');
}

export function setMode(mode) {
  app.set({ mode });
  storage.save('mode', mode);
  renderNow();
}

// The tape width and font a reset text label goes back to: the user's defaults from Settings
export function labelDefaults() {
  const { settings, fonts, tapeWidths } = app.get();
  return {
    tape_width_mm: tapeWidths.includes(settings.default_tape_mm) ? settings.default_tape_mm : DEFAULT_LABEL.tape_width_mm,
    font_name: fonts.includes(settings.default_font) ? settings.default_font : DEFAULT_LABEL.font_name,
  };
}

export function resetLabelSettings() {
  updateLabel({ ...DEFAULT_LABEL, ...labelDefaults(), text: app.get().label.text });
  say('Settings reset. Your text is kept.');
}

// What Python's LabelConfig gets: the label minus the app's own fields
export function renderOptions(label) {
  const { image, ...options } = label;
  options.qr_enabled = label.qr_enabled && label.qr_data.trim() !== '';
  options.image_data = image ? image.data : null;
  // The web app always fits text to the tape (line sizes and Text scale adjust it), so a
  // label saved by the desktop app with a fixed size fits too
  options.auto_fit_font = true;
  if (!options.text.trim() && !options.qr_enabled && !image) options.text = ' ';
  return options;
}

function binOptions(cfg) {
  const { icon, ...rest } = cfg;
  return { bin: { ...rest, icon_data: icon ? icon.data : null }, bin_font: app.get().settings.bin_font };
}

// A queue item or the label being edited, as render options for Python
export function itemOptions(item) {
  return item.mode === 'bin' ? binOptions(item.bin) : renderOptions(item.label);
}

export function currentItem() {
  const { mode, label, bin } = app.get();
  return mode === 'bin' && bin ? { mode, bin: bin[bin.kind] } : { mode: 'text', label };
}

function itemTapeWidth(item) {
  return item.mode === 'bin' ? BIN_TAPE_MM : item.label.tape_width_mm;
}

// A text label's lines without their styling marks
export function textLines(label) {
  return label.text.split('\n')
    .map((l) => l.replace(/^(#{1,2}|-#|<<|><|>>)\s+/g, '').replace(/(\*\*|__|==|\*)/g, '').trim())
    .filter((l) => l && l !== '---');
}

export function itemTitle(item) {
  if (item.mode === 'bin') {
    const b = item.bin;
    return (b.kind === 'component' ? `${b.category_banner} ${b.spec_primary}` : `${b.thread_size} ${b.category}`).trim() || 'Bin label';
  }
  return textLines(item.label)[0] || (item.label.qr_enabled ? 'QR code' : item.label.image ? 'Picture' : 'Label');
}

// Renders the current label. Calls made while one runs fold into a single follow-up render.
export async function renderNow() {
  clearTimeout(renderTimer);
  if (!py) return;
  if (rendering) {
    renderAgain = true;
    return rendering;
  }
  rendering = (async () => {
    do {
      renderAgain = false;
      const item = currentItem();
      try {
        // The rulers are only for this preview, so a bin label takes the text label's choice
        // here and not in its queue item
        const options = itemOptions(item);
        if (item.mode === 'bin') options.show_rulers = app.get().label.show_rulers;
        const result = await py.render_label(options);
        const old = app.get().render;
        if (old) { URL.revokeObjectURL(old.previewUrl); URL.revokeObjectURL(old.dotsUrl); }
        app.set({
          render: {
            previewUrl: URL.createObjectURL(new Blob([result.preview_png], { type: 'image/png' })),
            dotsUrl: URL.createObjectURL(new Blob([result.dots_png], { type: 'image/png' })),
            raster: result.raster,
            metrics: result.metrics,
            tape_width_mm: itemTapeWidth(item),
            item,
            tape_bg_color: item.mode === 'bin' ? '#FFFFFF' : item.label.tape_bg_color,
          },
          renderError: null,
        });
      } catch (err) {
        app.set({ renderError: `Couldn't draw the label: ${errorMessage(err)}` });
      }
    } while (renderAgain);
  })();
  try {
    await rendering;
  } finally {
    rendering = null;
  }
}

// Text editor helpers, done by the same Python code as the desktop editor
export const toggleStyle = (text, start, end, style) => py.toggle_style(text, start, end, style);
export const restyleLines = (text, start, end, changes) => py.restyle_lines(text, start, end, changes);
export const lineStyleAt = (text, pos) => (py ? py.line_style_at(text, pos) : Promise.resolve(['normal', null]));

export async function addFont(file) {
  const data = new Uint8Array(await file.arrayBuffer());
  const name = await py.add_font(file.name, data);
  if (!name) {
    say(`${file.name} is not a font file Cube Labeler can read.`, true);
    return null;
  }
  const fonts = (await storage.load('fonts', [])).filter((f) => f.filename !== file.name);
  fonts.push({ filename: file.name, data });
  await storage.save('fonts', fonts);
  app.set({ fonts: await py.font_names() });
  updateLabel({ font_name: name });
  say(`Added ${name}.`);
  return name;
}

// Fonts from a backup: added, or replaced by the backup's file of the same name. Returns how many changed.
export async function restoreFonts(list) {
  const fonts = await storage.load('fonts', []);
  const same = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
  let changed = 0;
  for (const { filename, data } of list) {
    const bytes = new Uint8Array(data);
    const had = fonts.find((f) => f.filename === filename);
    if (had && same(new Uint8Array(had.data), bytes)) continue;
    if (!(await py.add_font(filename, bytes))) continue;
    if (had) had.data = bytes;
    else fonts.push({ filename, data: bytes });
    changed++;
  }
  if (changed) {
    await storage.save('fonts', fonts);
    app.set({ fonts: await py.font_names() });
  }
  return changed;
}

export async function setBinIcon(file) {
  setBinIconBytes(file.name, new Uint8Array(await file.arrayBuffer()));
}

export function setBinIconBytes(name, data) {
  const icon = { name, data };
  updateBin(app.get().bin.kind === 'component' ? { icon_type: 'custom', icon } : { tool_type: 'custom', icon });
}

export async function setImage(file) {
  if (!file) {
    updateLabel({ image: null });
    return;
  }
  setImageBytes(file.name, new Uint8Array(await file.arrayBuffer()));
}

export function setImageBytes(name, data) {
  updateLabel({ image: { name, data } });
}

// --- Icons ---------------------------------------------------------------------------------

export const iconPrintPreview = (data) => py.icon_print_preview(data);
export const prepareIconOriginal = (data) => py.prepare_icon_original(data);
export const editIcon = (original, edit, touch) => py.edit_icon(original, edit, touch);

// --- Templates and backups (the desktop app's file formats, read and written in Python) ------

export const labelThumbnail = (item, height = 48) => py.label_thumbnail(itemOptions(item), height);
export const templatePresets = () => py.template_presets();
export const templateFromDesktop = (data) => py.template_from_desktop(data);
export const templateToDesktop = (item) => py.template_to_desktop(item);
export const makeBackup = (data) => py.make_backup(data);
export const backupDigest = (data) => py.backup_digest(data);
export const openBackup = (data) => py.open_backup(data);
export const pythonReady = () => py !== null;

// --- AI icons ------------------------------------------------------------------------------

export const aiServices = () => py.ai_services();
export const aiModels = (service, model) => py.ai_models(service, model);
export const aiRequest = (service, picture, preset, custom, model) => py.ai_request(service, picture, preset, custom, model);
export const aiAnswer = (service, model, status, body) => py.ai_answer(service, model, status, body);

// --- Printer -------------------------------------------------------------------------------

async function printerJob(job) {
  if (printer.get().busy) return;
  printer.set({ busy: true });
  try {
    await job();
  } catch (err) {
    const message = errorMessage(err);
    printer.set({ state: 'error', message });
    say(message, true);
  } finally {
    printer.set({ busy: false });
  }
}

function showStatus(info) {
  const problems = info.errors.length ? info.errors.join(', ') : '';
  printer.set({ info, state: problems ? 'error' : 'ready', message: problems });

  // Like the desktop app: the label follows the tape that is loaded
  const label = app.get().label;
  const width = Number(info.tape_width_mm);
  if (app.get().settings.match_printer_tape && app.get().tapeWidths.includes(width) && width !== label.tape_width_mm) {
    updateLabel({ tape_width_mm: width });
    say(`Tape set to ${width} mm to match the printer.`);
  }
}

export function connectPrinter() {
  return printerJob(async () => {
    let transport;
    try {
      transport = await SerialTransport.request();
    } catch (err) {
      if (err.name === 'NotFoundError') return;  // the user closed the picker
      throw err;
    }
    printer.set({ transport, state: 'paired', message: 'Checking printer status...' });
    say('Checking printer status...');
    showStatus(await queryStatus(transport, py));
    say('Printer connected.');
  });
}

export function checkStatus() {
  return printerJob(async () => {
    say('Checking printer status...');
    showStatus(await queryStatus(printer.get().transport, py));
    say('Printer is ready.');
  });
}

export function forgetPrinter() {
  return printerJob(async () => {
    const { transport } = printer.get();
    if (transport && transport.port.forget) await transport.port.forget();
    printer.set({ transport: null, info: null, state: 'none', message: '' });
    say('Printer forgotten. Connect it again from the printer menu.');
  });
}

function tooLong(metrics) {
  if (metrics.total_used_length_mm <= MAX_TAPE_MM) return false;
  say(`This needs ${Math.round(metrics.total_used_length_mm)} mm of tape, but the printer's limit is ${MAX_TAPE_MM} mm. Shorten it or split the queue.`, true);
  return true;
}

export async function printLabel() {
  await renderNow();  // print exactly what the editor shows, even mid-typing
  const current = app.get().render;
  if (!current || !printer.get().transport || tooLong(current.metrics)) return;
  await printerJob(async () => {
    const result = await printRaster(printer.get().transport, py, current.raster, {
      required_tape_width_mm: current.tape_width_mm,
    }, (message) => say(message));
    if (result.confirmed) {
      printer.set({ state: 'ready', message: '' });
      say('Printed.');
    } else {
      say('Print sent, but the printer did not confirm completion. Check the label.', true);
    }
  });
}

export function feed() {
  return printerJob(async () => {
    await feedTape(printer.get().transport, py, FEED_LENGTH_MM, (message) => say(message));
  });
}

export function savePicture(fromQueue = false) {
  const current = fromQueue ? app.get().queueRender : app.get().render;
  if (!current) return;
  const title = fromQueue ? 'queue' : itemTitle(current.item);
  const name = title.replace(/[\\/:*?"<>|]/g, '').trim().slice(0, 40) || 'label';
  const link = document.createElement('a');
  link.href = current.previewUrl;
  link.download = `${name}.png`;
  link.click();
}

// --- Queue ---------------------------------------------------------------------------------

let nextQueueId = Date.now();
let undoTimer = null;
const UNDO_SECONDS = 8;

const sameLabel = (a, b) => a.mode === b.mode && JSON.stringify(a.mode === 'bin' ? a.bin : a.label) === JSON.stringify(b.mode === 'bin' ? b.bin : b.label);
export const copiesOf = (item) => Math.max(1, item.copies || 1);
// Every printed label, copies included
export const queueLabelCount = (queue) => queue.reduce((sum, item) => sum + copiesOf(item), 0);

// Queues saved before copies existed hold the same label several times in a row
function mergeCopies(queue) {
  const merged = [];
  for (const item of queue) {
    const last = merged[merged.length - 1];
    if (last && sameLabel(last, item)) last.copies = copiesOf(last) + copiesOf(item);
    else merged.push({ ...item, copies: copiesOf(item) });
  }
  return merged;
}

function saveQueue(queue, undo = null) {
  clearTimeout(undoTimer);
  if (undo) undoTimer = setTimeout(() => app.set({ queueUndo: null }), UNDO_SECONDS * 1000);
  app.set({ queue, queuePrinted: 0, queueUndo: undo });
  storage.save('queue', queue);
  queueRenderStale = true;
  if (queueShown) renderQueue();
}

async function makeThumb(item) {
  if (!py || app.get().thumbs[item.id]) return;
  try {
    const png = await py.label_thumbnail(itemOptions(item), 48);
    const url = URL.createObjectURL(new Blob([png], { type: 'image/png' }));
    app.set({ thumbs: { ...app.get().thumbs, [item.id]: url } });
  } catch (err) {
    console.warn('No thumbnail:', err);
  }
}

export function addToQueue() {
  const item = { id: nextQueueId++, ...structuredClone(currentItem()) };
  if (item.mode === 'text' && !item.label.text.trim() && !(item.label.qr_enabled && item.label.qr_data.trim()) && !item.label.image) {
    say('Add some text, a QR code or a picture first.', true);
    return false;
  }
  const { queue } = app.get();
  // A queue prints as one strip, so every label in it needs the same tape
  if (queue.length && itemTapeWidth(queue[0]) !== itemTapeWidth(item)) {
    say(`The queue is for ${itemTapeWidth(queue[0])} mm tape, but this label is ${itemTapeWidth(item)} mm. Print or clear the queue first.`, true);
    return false;
  }
  const title = itemTitle(item);
  const short = title.length > 25 ? `${title.slice(0, 24)}…` : title;
  const last = queue[queue.length - 1];
  // The same label again is one more copy of it
  if (last && sameLabel(last, item)) {
    saveQueue([...queue.slice(0, -1), { ...last, copies: copiesOf(last) + 1 }]);
  } else {
    saveQueue([...queue, { ...item, copies: 1 }]);
    makeThumb(item);
  }
  const count = queueLabelCount(app.get().queue);
  const copies = copiesOf(app.get().queue[app.get().queue.length - 1]);
  say(`Added "${short}"${copies > 1 ? ` (×${copies})` : ''} to the queue${count > 1 ? ` (${count} labels, saves ${25 * (count - 1)} mm of tape)` : ''}.`);
  return true;
}

// Moves a queued label from one place in the list to another
export function moveQueueItem(from, to) {
  const queue = [...app.get().queue];
  if (from === to || to < 0 || to >= queue.length) return;
  const [item] = queue.splice(from, 1);
  queue.splice(to, 0, item);
  saveQueue(queue);
}

export function setQueueCopies(index, copies) {
  if (copies < 1) { removeQueueItem(index); return; }
  const queue = app.get().queue.map((item, i) => (i === index ? { ...item, copies: Math.min(99, copies) } : item));
  saveQueue(queue);
}

export function removeQueueItem(index) {
  const before = app.get().queue;
  const title = itemTitle(before[index]);
  saveQueue(before.filter((_, i) => i !== index), { queue: before, text: `Removed "${title.length > 30 ? `${title.slice(0, 29)}…` : title}".` });
}

export function clearQueue() {
  const before = app.get().queue;
  saveQueue([], before.length ? { queue: before, text: `Cleared ${queueLabelCount(before)} labels.` } : null);
}

// Puts back what the last removal or clearing took out
export function undoQueueRemoval() {
  const { queueUndo } = app.get();
  if (!queueUndo) return;
  saveQueue(queueUndo.queue);
  queueUndo.queue.forEach(makeThumb);
}

export function keepPrintedQueue() {
  app.set({ queuePrinted: 0 });
}

// Opens a queued label in the editor; the queued copy stays in the queue
// Puts a label (a queue item or a template: {mode, label} or {mode, bin}) in the editor
export function openItem(item) {
  item = structuredClone(item);
  if (item.mode === 'bin') {
    const bin = app.get().bin;
    app.set({ mode: 'bin', bin: { ...bin, kind: item.bin.kind, [item.bin.kind]: item.bin } });
    storage.save('bin', app.get().bin);
  } else {
    app.set({ mode: 'text', label: { ...DEFAULT_LABEL, ...item.label } });
    storage.save('label', app.get().label);
  }
  storage.save('mode', app.get().mode);
  renderNow();
  location.hash = '#/label';
}

export function editQueueItem(index) {
  openItem(app.get().queue[index]);
  say(`Editing queued label ${index + 1}. Add it to the queue again to keep your changes.`);
}

let queueShown = false;
let queueRenderStale = true;

// The queue page shows the whole strip; it is drawn only while that page is open
export function showingQueue(shown) {
  queueShown = shown;
  if (shown && queueRenderStale) renderQueue();
}

export async function renderQueue() {
  if (!py) return;
  queueRenderStale = false;
  const { queue } = app.get();
  const old = app.get().queueRender;
  if (!queue.length) {
    app.set({ queueRender: null });
  } else {
    try {
      const result = await py.render_queue(queue.map(itemOptions), queue.map(copiesOf));
      // Which list item each printed label on the strip belongs to
      const owners = queue.flatMap((item, i) => Array(copiesOf(item)).fill(i));
      app.set({
        queueRender: {
          previewUrl: URL.createObjectURL(new Blob([result.preview_png], { type: 'image/png' })),
          dotsUrl: URL.createObjectURL(new Blob([result.dots_png], { type: 'image/png' })),
          raster: result.raster,
          metrics: result.metrics,
          tape_width_mm: itemTapeWidth(queue[0]),
          tape_bg_color: queue[0].mode === 'bin' ? '#FFFFFF' : queue[0].label.tape_bg_color,
          count: queueLabelCount(queue),
          spans: result.spans.map(([from, to], n) => ({ from, to, item: owners[n] })),
          bins: queue.some((item) => item.mode === 'bin'),
        },
      });
    } catch (err) {
      say(`Couldn't draw the queue: ${errorMessage(err)}`, true);
      app.set({ queueRender: null });
    }
  }
  if (old) { URL.revokeObjectURL(old.previewUrl); URL.revokeObjectURL(old.dotsUrl); }
}

export async function printQueue() {
  if (queueRenderStale || !app.get().queueRender) await renderQueue();
  const strip = app.get().queueRender;
  if (!strip || !printer.get().transport || tooLong(strip.metrics)) return;
  await printerJob(async () => {
    const result = await printRaster(printer.get().transport, py, strip.raster, {
      required_tape_width_mm: strip.tape_width_mm,
    }, (message) => say(message));
    if (result.confirmed) {
      printer.set({ state: 'ready', message: '' });
      say(`Printed ${strip.count} labels as one strip.`);
      app.set({ queuePrinted: strip.count });
    } else {
      say(`Queue of ${strip.count} labels sent, but the printer did not confirm completion.`, true);
    }
  });
}
