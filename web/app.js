// Cube Labeler web app: page controller.
//
// Pyodide runs the same Python core as the desktop app (rendering, print job bytes, status
// decoding); printer.js moves the bytes over Web Serial.

import { SerialTransport, queryStatus, printRaster, errorMessage } from './printer.js';

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.29.5/full/';
const QRCODE_VERSION = '8.2';  // keep in step with constraints.txt
const RENDER_DELAY_MS = 150;

const $ = (id) => document.getElementById(id);
const el = {
  loading: $('loading'),
  loadingText: $('loading-text'),
  app: $('app'),
  serialBadge: $('serial-badge'),
  serialHelp: $('serial-help'),
  text: $('text'),
  tape: $('tape'),
  font: $('font'),
  fontFile: $('font-file'),
  autoFit: $('auto-fit'),
  fontSize: $('font-size'),
  align: $('align'),
  qrEnabled: $('qr-enabled'),
  qrData: $('qr-data'),
  autoCut: $('auto-cut'),
  preview: $('preview'),
  metrics: $('metrics'),
  warning: $('warning'),
  connect: $('connect'),
  status: $('check-status'),
  print: $('print'),
  save: $('save'),
  printer: $('printer'),
  log: $('log'),
};

let py = null;
let transport = null;
let current = null;  // last render: {previewUrl, raster, metrics}
let busy = false;
let renderTimer = null;

function log(message, isError = false) {
  el.log.textContent = message;
  el.log.classList.toggle('error', isError);
}

function toPlain(proxy) {
  const value = proxy.toJs({ dict_converter: Object.fromEntries });
  proxy.destroy();
  return value;
}

async function loadPython() {
  el.loadingText.textContent = 'Loading Python...';
  const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });

  el.loadingText.textContent = 'Loading Pillow and QR codes...';
  await pyodide.loadPackage(['pillow', 'micropip']);
  await pyodide.pyimport('micropip').install(`qrcode==${QRCODE_VERSION}`);

  el.loadingText.textContent = 'Loading Cube Labeler...';
  const response = await fetch('cube_core.zip');
  if (!response.ok) throw new Error(`cube_core.zip: HTTP ${response.status}`);
  // The archive holds core/, cube_web.py and the bundled fonts in ~/.fonts
  pyodide.unpackArchive(await response.arrayBuffer(), 'zip', { extractDir: '/home/pyodide' });
  pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  return pyodide.pyimport('cube_web');
}

function fillSelect(select, values, selected, label = (v) => v) {
  select.replaceChildren(...values.map((value) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label(value);
    option.selected = value === selected;
    return option;
  }));
}

function labelOptions() {
  return {
    text: el.text.value || ' ',
    font_name: el.font.value,
    tape_width_mm: Number(el.tape.value),
    auto_fit_font: el.autoFit.checked,
    fixed_font_size: Number(el.fontSize.value) || 40,
    alignment: el.align.value,
    qr_enabled: el.qrEnabled.checked && el.qrData.value.trim() !== '',
    qr_data: el.qrData.value,
  };
}

function render() {
  try {
    const result = toPlain(py.render_label(labelOptions()));
    if (current) URL.revokeObjectURL(current.previewUrl);
    current = {
      previewUrl: URL.createObjectURL(new Blob([result.preview_png], { type: 'image/png' })),
      raster: result.raster,
      metrics: result.metrics,
    };
    el.preview.src = current.previewUrl;
    const m = result.metrics;
    el.metrics.textContent = `${m.print_length_mm} mm label, ${m.total_used_length_mm} mm of tape, `
      + `about ${m.print_duration_sec} s to print`;
    el.warning.textContent = m.warning || '';
    el.warning.hidden = !m.warning;
  } catch (err) {
    current = null;
    log(errorMessage(err), true);
  }
  updateButtons();
}

function scheduleRender() {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(render, RENDER_DELAY_MS);
}

function updateButtons() {
  const canSerial = SerialTransport.isSupported();
  el.connect.disabled = busy || !canSerial;
  el.status.disabled = busy || !transport;
  el.print.disabled = busy || !transport || !current;
  el.save.disabled = !current;
  el.fontSize.disabled = el.autoFit.checked;
  el.qrData.disabled = !el.qrEnabled.checked;
}

function showPrinter(status) {
  const parts = [status.model, `${status.tape_width_mm} mm ${status.tape_color} tape`, status.power];
  if (status.errors.length) parts.push(status.errors.join(', '));
  el.printer.textContent = parts.join(' · ');
}

async function runJob(job) {
  busy = true;
  updateButtons();
  try {
    await job();
  } catch (err) {
    log(errorMessage(err), true);
  } finally {
    busy = false;
    updateButtons();
  }
}

async function connect() {
  await runJob(async () => {
    try {
      transport = await SerialTransport.request();
    } catch (err) {
      if (err.name === 'NotFoundError') return;  // the user closed the picker
      throw err;
    }
    log('Checking printer status...');
    showPrinter(await queryStatus(transport, py));
    log('Printer connected.');
  });
}

async function checkStatus() {
  await runJob(async () => {
    log('Checking printer status...');
    showPrinter(await queryStatus(transport, py));
    log('Printer is ready.');
  });
}

async function print() {
  render();  // print exactly what the form shows, even mid-typing
  if (!current) return;
  const raster = current.raster;
  await runJob(async () => {
    const result = await printRaster(transport, py, raster, {
      auto_cut: el.autoCut.checked,
      required_tape_width_mm: Number(el.tape.value),
    }, (message) => log(message));
    if (!result.confirmed) log('Print sent, but the printer did not confirm completion.', true);
  });
}

function save() {
  const link = document.createElement('a');
  link.href = current.previewUrl;
  link.download = `${(el.text.value.split('\n')[0] || 'label').trim().slice(0, 40) || 'label'}.png`;
  link.click();
}

async function addFont() {
  const file = el.fontFile.files[0];
  el.fontFile.value = '';
  if (!file) return;
  const name = py.add_font(file.name, new Uint8Array(await file.arrayBuffer()));
  if (!name) {
    log(`${file.name} is not a font file Cube Labeler can read.`, true);
    return;
  }
  const names = toPlain(py.font_names());
  fillSelect(el.font, names, name);
  log(`Added ${name}. Fonts you add are kept until the page is closed.`);
  render();
}

async function main() {
  if (SerialTransport.isSupported()) {
    el.serialBadge.textContent = 'Bluetooth printing available';
    el.serialBadge.classList.add('ok');
  } else {
    el.serialBadge.textContent = 'Printing not supported in this browser';
    el.serialHelp.hidden = false;
  }

  try {
    py = await loadPython();
  } catch (err) {
    el.loadingText.textContent = `Could not start: ${errorMessage(err)}`;
    el.loading.classList.add('error');
    return;
  }

  const widths = toPlain(py.tape_widths());
  fillSelect(el.tape, widths.map(String), '12', (w) => `${w} mm`);
  const fonts = toPlain(py.font_names());
  fillSelect(el.font, fonts, fonts.includes('Arimo') ? 'Arimo' : fonts[0]);

  if (SerialTransport.isSupported()) {
    transport = await SerialTransport.remembered();
    if (transport) el.printer.textContent = 'Printer paired earlier. Check status to wake it.';
  }

  for (const input of [el.text, el.qrData, el.fontSize]) input.addEventListener('input', scheduleRender);
  for (const input of [el.tape, el.font, el.align, el.autoFit, el.qrEnabled]) {
    input.addEventListener('change', () => { updateButtons(); render(); });
  }
  el.fontFile.addEventListener('change', addFont);
  el.connect.addEventListener('click', connect);
  el.status.addEventListener('click', checkStatus);
  el.print.addEventListener('click', print);
  el.save.addEventListener('click', save);

  el.loading.hidden = true;
  el.app.hidden = false;
  render();
}

main();
