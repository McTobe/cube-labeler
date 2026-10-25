// Bin label editor. Two kinds, laid out like the desktop app:
// - Fasteners: size, a name, one/two/four bins of lengths, and a drive icon
// - Parts: a name banner, part number, note and an icon
// Bin labels are designed for 12 mm tape and always print at 12 mm.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Icon } from '../icons.js';
import { IconPickerSheet } from './icons.js';
import { Field, Section, Segmented, Toggle } from '../ui.js';
import { useStore } from '../state.js';
import { app, boot, updateBin, updateSettings, setBinIcon, setBinIconBytes, addToQueue, say } from '../app.js';

const QUICK_SIZES = ['M2', 'M2.5', 'M3', 'M4', 'M5', 'M6', 'M8'];
const QUICK_LENGTHS = ['4', '6', '8', '10', '12', '16', '20', '25', '30', '35', '40', '50'];
const BINS = [['single', 'One'], ['dual', 'Two'], ['quad', 'Four']];
// The bin label length Reset goes back to until the user saves their own
const FACTORY_LABEL_MM = 32;
const LENGTH_FIELDS = {
  single: ['length_single'],
  dual: ['length_dual_1', 'length_dual_2'],
  quad: ['length_quad_1', 'length_quad_2', 'length_quad_3', 'length_quad_4'],
};
// Drive icons to pick from, with the library pictures the label prints. Robertson and the hex
// nut have no drawn drive of their own, so they go on the label as pictures.
const DRIVE_TILES = [
  { value: 'phillips', name: 'PH', file: 'screw_drives/phillips.png' },
  { value: 'pozidriv', name: 'PZ', file: 'screw_drives/pozidriv.png' },
  { value: 'torx', name: 'Torx', file: 'screw_drives/torx.png' },
  { value: 'internal_hex', name: 'Allen', file: 'screw_drives/hex_socket.png' },
  { value: 'slotted', name: 'Slot', file: 'screw_drives/slotted.png' },
  { picture: 'robertson.png', name: 'Robertson', file: 'screw_drives/robertson.png' },
  { value: 'external_hex', name: 'Hex head', file: 'screw_drives/external_hex.png' },
  { picture: 'hex_nut_drive.png', name: 'Hex nut', file: 'screw_drives/hex_nut_drive.png' },
  { value: 'none', name: 'None' },
];
const DRIVES = DRIVE_TILES.filter((t) => t.value).map((t) => [t.value, t.name]);
const PART_TILES = [
  { value: 'ball_bearing', name: 'Bearing', file: 'mechanical/bearing_608zz.png' },
  { value: 'linear_bearing', name: 'Linear bearing', file: 'mechanical/linear_bearing.png' },
  { value: 'spring', name: 'Spring', file: 'mechanical/spring.png' },
  { value: 'wago', name: 'WAGO', file: 'wiring/wago_221.png' },
  { value: 'terminal_block', name: 'Terminal block', file: 'wiring/terminal_block.png' },
  { value: 'jst', name: 'JST', file: 'wiring/jst_connector.png' },
  { value: 'fuse', name: 'Fuse', file: 'electronics/fuse_inline.png' },
  { value: 'resistor', name: 'Resistor', file: 'electronics/resistor.png' },
  { value: 'capacitor', name: 'Capacitor', file: 'electronics/capacitor_elec.png' },
  { value: 'led', name: 'LED', file: 'electronics/led.png' },
  { value: 'none', name: 'None' },
];

// What sets a bin label apart from others with the same name, for lists: lengths, drive or icon, length
export function binSummary(cfg) {
  const pictureName = () => (cfg.icon ? cfg.icon.name.replace(/\.[a-z]+$/i, '').replace(/[_-]+/g, ' ') : '');
  const parts = [];
  if (cfg.kind === 'component') {
    parts.push(cfg.spec_secondary);
    const tile = PART_TILES.find((t) => t.value === cfg.icon_type);
    parts.push(cfg.icon_type === 'custom' ? pictureName() : tile && tile.value !== 'none' ? tile.name : '');
  } else {
    const lengths = cfg.compartment_mode === 'assortment'
      ? [cfg.assortment_line1, cfg.assortment_line2]
      : LENGTH_FIELDS[cfg.compartment_mode || 'single'].map((f) => cfg[f]);
    parts.push(lengths.filter((t) => t && t.trim()).join(' '));
    const tile = DRIVE_TILES.find((t) => t.value === cfg.tool_type);
    const drive = cfg.tool_type === 'custom' ? (DRIVE_TILES.find((t) => t.picture && cfg.icon && t.picture === cfg.icon.name) || {}).name || pictureName()
      : tile && tile.value !== 'none' ? tile.name : '';
    parts.push([cfg.tool_size, drive].filter(Boolean).join(' '));
  }
  parts.push(`${cfg.label_width_mm} mm`);
  return parts.filter((t) => t && t.trim()).join(' · ');
}

// A plain number is a length and prints as "x30"; anything else prints as typed
const formatLength = (text) => (/^\d+(?:[.,]\d+)?$/.test(text.trim()) ? `x${text.trim()}` : text);
const unformatLength = (text) => {
  const m = String(text || '').trim().match(/^[x×]\s*(\d+(?:[.,]\d+)?)$/i);
  return m ? m[1] : String(text || '');
};

function Text({ label, value, placeholder, onChange, hint }) {
  return html`<${Field} label=${label} hint=${hint}>
    <input type="text" value=${value} placeholder=${placeholder} autocomplete="off"
      onInput=${(e) => onChange(e.currentTarget.value)} />
  <//>`;
}

function Length({ value, field, placeholder, label, onFocus }) {
  return html`<input type="text" inputmode="decimal" aria-label=${label} value=${unformatLength(value)}
    placeholder=${placeholder} onFocus=${onFocus} onInput=${(e) => updateBin({ [field]: formatLength(e.currentTarget.value) })} />`;
}

// The icon as a row of pictures to click, then the library and the user's own pictures
function IconTiles({ cfg, tiles, field }) {
  const { phase } = useStore(boot);
  const fileRef = useRef(null);
  const [thumb, setThumb] = useState(null);
  const [picking, setPicking] = useState(false);
  const value = cfg[field];
  const icon = cfg.icon;
  const custom = value === 'custom' && icon;
  const tileFor = custom && tiles.find((t) => t.picture === icon.name);
  useEffect(() => {
    if (!custom || tileFor) { setThumb(null); return undefined; }
    const url = URL.createObjectURL(new Blob([icon.data]));
    setThumb(url);
    return () => URL.revokeObjectURL(url);
  }, [icon, value]);

  const pick = async (tile) => {
    if (tile.value) { updateBin({ [field]: tile.value }); return; }
    const response = await fetch(`icons/${tile.file}`);
    setBinIconBytes(tile.picture, new Uint8Array(await response.arrayBuffer()));
  };
  const onFile = async (e) => {
    const file = e.currentTarget.files[0];
    e.currentTarget.value = '';
    if (file) await setBinIcon(file);
  };
  const on = (tile) => (tile.value ? value === tile.value : tileFor === tile);
  return html`<${Field} label="Icon">
    <div class="icon-tiles" role="group" aria-label="Icon">
      ${tiles.map((tile) => html`<button class=${`icon-choice${on(tile) ? ' on' : ''}`} aria-pressed=${on(tile)}
        title=${tile.name} onClick=${() => pick(tile)}>
        ${tile.file ? html`<img src=${`icons/${tile.file}`} alt="" />` : html`<span class="none-mark" aria-hidden="true">—</span>`}
        <span>${tile.name}</span></button>`)}
      ${thumb && html`<button class="icon-choice on" aria-pressed="true" title=${icon.name}>
        <img src=${thumb} alt="" /><span>${icon.name.replace(/\.[a-z]+$/i, '')}</span></button>`}
    </div>
    <div class="icon-sources">
      <button class="secondary" disabled=${phase !== 'ready'} onClick=${() => setPicking(true)}>
        <${Icon} name="icons" size=${18} /> Library</button>
      <button class="secondary" disabled=${phase !== 'ready'} onClick=${() => fileRef.current.click()}>
        <${Icon} name="image" size=${18} /> Own picture</button>
    </div>
    <input ref=${fileRef} type="file" accept="image/*" hidden onChange=${onFile} />
    <${IconPickerSheet} open=${picking} target="bin" onClose=${() => setPicking(false)} />
  <//>`;
}

// Chips that fill in a common value; typing still works
function Chips({ label, values, current, onPick }) {
  return html`<div class="quick-chips" role="group" aria-label=${label}>
    ${values.map((v) => html`<button class=${current === v ? 'on' : ''} onClick=${() => onPick(v)}>${v}</button>`)}
  </div>`;
}

// A length chip fills the bin that was last clicked (or the first empty one, or bin 1) and then
// moves on to the next bin, so clicking a few chips fills the label in order
let lastLength = null;
function pickLength(cfg, v) {
  const fields = LENGTH_FIELDS[cfg.compartment_mode] || [];
  if (!fields.length) return;
  const target = fields.includes(lastLength) ? lastLength : (fields.find((f) => !cfg[f].trim()) || fields[0]);
  updateBin({ [target]: formatLength(v) });
  lastLength = fields[fields.indexOf(target) + 1] || null;
}

function FastenerForm({ cfg, names }) {
  const mode = cfg.compartment_mode;
  const focus = (field) => () => { lastLength = field; };
  let lengths;
  if (mode === 'single') {
    lengths = html`<div class="length-grid one">
      <${Length} label="Length" value=${cfg.length_single} field="length_single" placeholder="20" onFocus=${focus('length_single')} />
      <input type="text" aria-label="Note" value=${cfg.standard_line1} placeholder="Note, e.g. DIN 933 8.8"
        onInput=${(e) => updateBin({ standard_line1: e.currentTarget.value })} />
    </div>`;
  } else if (mode === 'quad') {
    lengths = html`<div class="length-grid quad">
      ${[1, 2, 3, 4].map((n) => html`<${Length} label=${`Bin ${n}`} value=${cfg[`length_quad_${n}`]} field=${`length_quad_${n}`}
        onFocus=${focus(`length_quad_${n}`)} />`)}
    </div>`;
  } else if (mode === 'assortment') {
    // Older labels: two lines of text instead of lengths; the Bins buttons switch away from it
    lengths = html`<div class="length-grid">
      <input type="text" aria-label="Line 1" value=${cfg.assortment_line1} onInput=${(e) => updateBin({ assortment_line1: e.currentTarget.value })} />
      <input type="text" aria-label="Line 2" value=${cfg.assortment_line2} onInput=${(e) => updateBin({ assortment_line2: e.currentTarget.value })} />
    </div>`;
  } else {
    lengths = html`<div class="length-grid">
      <${Length} label="Bin 1" value=${cfg.length_dual_1} field="length_dual_1" onFocus=${focus('length_dual_1')} />
      <${Length} label="Bin 2" value=${cfg.length_dual_2} field="length_dual_2" onFocus=${focus('length_dual_2')} />
    </div>`;
  }
  return html`
    <div class="bin-grid three">
      <div class="bin-col">
        <${Text} label="Size" value=${cfg.thread_size} placeholder="M3" onChange=${(thread_size) => updateBin({ thread_size })} />
        <${Chips} label="Common sizes" values=${QUICK_SIZES} current=${cfg.thread_size}
          onPick=${(thread_size) => updateBin({ thread_size })} />
        <${Text} label="Name" value=${cfg.category} placeholder="SCREWS" onChange=${(category) => updateBin({ category })} />
        <${Chips} label="Common names" values=${names.slice(0, 4)} current=${cfg.category}
          onPick=${(category) => updateBin({ category })} />
      </div>
      <div class="bin-col">
        <${Segmented} label="Bins" options=${BINS} value=${mode === 'assortment' ? '' : mode}
          onChange=${(compartment_mode) => { lastLength = null; updateBin({ compartment_mode }); }} />
        <${Field} label=${mode === 'single' ? 'Length and note' : 'Lengths'}>${lengths}<//>
        ${mode !== 'assortment' && html`<${Chips} label="Common lengths" values=${QUICK_LENGTHS} onPick=${(v) => pickLength(cfg, v)} />`}
      </div>
      <div class="bin-col">
        <${IconTiles} cfg=${cfg} field="tool_type"
          tiles=${cfg.tool_type === 'washer' ? [...DRIVE_TILES, { value: 'washer', name: 'Washer' }] : DRIVE_TILES} />
        <div class="row">
          <${Text} label="Drive size" value=${cfg.tool_size} placeholder="2.5" onChange=${(tool_size) => updateBin({ tool_size })} />
        </div>
      </div>
    </div>
  `;
}

function PartForm({ cfg, names }) {
  return html`
    <div class="bin-grid">
      <div class="bin-col">
        <${Text} label="Name" value=${cfg.category_banner} placeholder="BEARINGS" onChange=${(category_banner) => updateBin({ category_banner })} />
        <${Chips} label="Common names" values=${names.slice(0, 4)} current=${cfg.category_banner}
          onPick=${(category_banner) => updateBin({ category_banner })} />
        <${Text} label="Part number" value=${cfg.spec_primary} placeholder="608ZZ" onChange=${(spec_primary) => updateBin({ spec_primary })} />
        <${Text} label="Note" value=${cfg.spec_secondary} placeholder="Optional, e.g. 0.2–4.0 mm²" onChange=${(spec_secondary) => updateBin({ spec_secondary })} />
      </div>
      <div class="bin-col">
        <${IconTiles} cfg=${cfg} field="icon_type" tiles=${PART_TILES} />
      </div>
    </div>
  `;
}

// Adds the label to the queue and clears what changes from bin to bin (the lengths, or the
// part number and note), so a whole drawer goes quickly
function addAndNext() {
  const { bin } = app.get();
  if (!addToQueue()) return;
  if (bin.kind === 'fastener') {
    const cfg = bin.fastener;
    const fields = [...LENGTH_FIELDS.single, ...LENGTH_FIELDS.dual, ...LENGTH_FIELDS.quad, 'standard_line1'];
    updateBin(Object.fromEntries(fields.filter((f) => f in cfg).map((f) => [f, ''])));
  } else {
    updateBin({ spec_primary: '', spec_secondary: '' });
  }
  lastLength = null;
  say(`${app.get().status.text} Ready for the next one.`);
  setTimeout(() => {
    const first = document.querySelector('.bin-card .length-grid input, .bin-card input[placeholder="608ZZ"]');
    if (first) first.focus();
  });
}

// The bin label's main fields: under the preview on a wide screen, like the text label's text
export function BinCard() {
  const { bin, binNames } = useStore(app);
  const { phase } = useStore(boot);
  if (!bin) return html`<section class="card bin-card"><p class="hint">Loading...</p></section>`;
  const cfg = bin[bin.kind];
  return html`<section class="card bin-card">
    <div class="card-head">
      <${Segmented} ariaLabel="Label for" options=${[['fastener', 'Fasteners'], ['component', 'Parts']]} value=${bin.kind}
        onChange=${(kind) => { lastLength = null; updateBin({ kind }); }} />
      <button class="secondary" disabled=${phase !== 'ready'} title="Add to the queue and clear the lengths for the next bin"
        onClick=${addAndNext}>Add to queue and start the next</button>
    </div>
    ${bin.kind === 'fastener'
      ? html`<${FastenerForm} cfg=${cfg} names=${binNames.fastener} />`
      : html`<${PartForm} cfg=${cfg} names=${binNames.component} />`}
  </section>`;
}

// The bin label's less used options, in the side panel
export function BinOptions() {
  const { bin, settings } = useStore(app);
  const [widthText, setWidthText] = useState(null);
  if (!bin) return null;
  const cfg = bin[bin.kind];

  const onWidth = (e) => {
    const text = e.currentTarget.value;
    setWidthText(text);
    const mm = Number(text.replace(',', '.'));
    if (mm >= 10) updateBin({ label_width_mm: mm });
  };
  const builtInDrive = DRIVES.some(([v]) => v === cfg.tool_type && v !== 'none');
  const fallback = settings.bin_label_mm || FACTORY_LABEL_MM;
  const current = Number(cfg.label_width_mm);
  const reset = () => { setWidthText(null); updateBin({ label_width_mm: fallback }); };
  const keep = () => { updateSettings({ bin_label_mm: current }); say(`Reset now goes back to ${current} mm.`); };

  return html`
    <${Section} id="bin-size" title="Label length" summary=${`${cfg.label_width_mm} mm, 12 mm tape`}>
      <${Field} label="Length in mm" hint="Bin labels are designed for 12 mm tape and always print at 12 mm.">
        <input type="text" inputmode="decimal" value=${widthText ?? String(cfg.label_width_mm)} onInput=${onWidth}
          onBlur=${() => setWidthText(null)} />
      <//>
      <div class="button-row">
        <button class="secondary" disabled=${current === fallback} onClick=${reset}>Reset to ${fallback} mm</button>
        ${current !== fallback && current >= 10 && html`<button class="secondary" onClick=${keep}>Make ${current} mm my default</button>`}
      </div>
      <p class="hint">${settings.bin_label_mm ? `Your default is ${settings.bin_label_mm} mm. It goes with your backups and sync.` : `Make a length your default and Reset goes back to it on every device.`}</p>
    <//>
    ${bin.kind === 'fastener' && html`<${Section} id="bin-drive" title="Drive icon" summary=${cfg.simple_drive_icon ? 'Simple' : 'Library picture'}>
      <${Toggle} label="Simple drive icon" checked=${cfg.simple_drive_icon} disabled=${!builtInDrive}
        onChange=${(simple_drive_icon) => updateBin({ simple_drive_icon })} />
      <p class="hint">A plain drawn symbol instead of the library picture. Robertson, hex nut and your own pictures always print as pictures.</p>
    <//>`}`;
}
