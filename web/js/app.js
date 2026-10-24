// App state and the things the pages do with it: start Python, render, print, keep settings.
// Pages read the stores with useStore() and call these functions; none of them touch the
// printer or Python directly.

import { createStore } from './state.js';
import { startPython } from './python.js';
import * as storage from './storage.js';
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
  theme: 'system',  // 'system', 'light', 'dark'
  match_printer_tape: true,
};

// Startup: 'loading' with a progress text, then 'ready', or 'failed' with the reason
export const boot = createStore({ phase: 'loading', text: 'Starting...', error: null });

export const app = createStore({
  label: DEFAULT_LABEL,
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

export function say(text, error = false) {
  app.set({ status: { text, error } });
}

// --- Start ---------------------------------------------------------------------------------

export async function start() {
  const [settings, label, fonts] = await Promise.all([
    storage.load('settings', {}),
    storage.load('label', {}),
    storage.load('fonts', []),
  ]);
  app.set({
    settings: { ...DEFAULT_SETTINGS, ...settings },
    label: { ...DEFAULT_LABEL, ...label },
  });
  applyTheme(app.get().settings.theme);
  storage.askToPersist();

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
  const [tapeWidths, fontNames] = await Promise.all([py.tape_widths(), py.font_names()]);
  const current = app.get().label;
  app.set({
    tapeWidths,
    fonts: fontNames,
    label: fontNames.includes(current.font_name) ? current : { ...current, font_name: fontNames.includes('Arimo') ? 'Arimo' : fontNames[0] },
  });
  boot.set({ phase: 'ready' });
  await renderNow();
}

export function applyTheme(theme) {
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = getComputedStyle(document.documentElement).getPropertyValue('--bar').trim() || '#1f2430';
}

export function updateSettings(change) {
  const settings = { ...app.get().settings, ...change };
  app.set({ settings });
  storage.save('settings', settings);
  if ('theme' in change) applyTheme(settings.theme);
}

// --- Editing and rendering -----------------------------------------------------------------

let renderTimer = null;
let saveTimer = null;
let rendering = null;  // the render in flight
let renderAgain = false;

export function updateLabel(change) {
  const label = { ...app.get().label, ...change };
  app.set({ label });
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => storage.save('label', app.get().label), SAVE_DELAY_MS);
  clearTimeout(renderTimer);
  renderTimer = setTimeout(renderNow, RENDER_DELAY_MS);
}

export function resetLabelSettings() {
  updateLabel({ ...DEFAULT_LABEL, text: app.get().label.text, font_name: app.get().fonts.includes('Arimo') ? 'Arimo' : DEFAULT_LABEL.font_name });
  say('Settings reset. Your text is kept.');
}

// What Python's LabelConfig gets: the label minus the app's own fields
export function renderOptions(label) {
  const { image, ...options } = label;
  options.qr_enabled = label.qr_enabled && label.qr_data.trim() !== '';
  options.image_data = image ? image.data : null;
  if (!options.text.trim() && !options.qr_enabled && !image) options.text = ' ';
  return options;
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
      const label = app.get().label;
      try {
        const result = await py.render_label(renderOptions(label));
        const old = app.get().render;
        if (old) { URL.revokeObjectURL(old.previewUrl); URL.revokeObjectURL(old.dotsUrl); }
        app.set({
          render: {
            previewUrl: URL.createObjectURL(new Blob([result.preview_png], { type: 'image/png' })),
            dotsUrl: URL.createObjectURL(new Blob([result.dots_png], { type: 'image/png' })),
            raster: result.raster,
            metrics: result.metrics,
            tape_width_mm: label.tape_width_mm,
            label,
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

export async function setImage(file) {
  if (!file) {
    updateLabel({ image: null });
    return;
  }
  updateLabel({ image: { name: file.name, data: new Uint8Array(await file.arrayBuffer()) } });
}

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

export async function printLabel() {
  await renderNow();  // print exactly what the editor shows, even mid-typing
  const current = app.get().render;
  if (!current || !printer.get().transport) return;
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

export function savePicture() {
  const current = app.get().render;
  if (!current) return;
  const name = (current.label.text.split('\n')[0] || 'label').replace(/[*_=#<>\\/:?"|]/g, '').trim().slice(0, 40) || 'label';
  const link = document.createElement('a');
  link.href = current.previewUrl;
  link.download = `${name}.png`;
  link.click();
}
