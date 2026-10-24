// Bin label editor. Two kinds, laid out like the desktop app:
// - Fasteners: size, a name, one/two/four bins of lengths, and a drive icon
// - Parts: a name banner, part number, note and an icon
// Bin labels are designed for 12 mm tape and always print at 12 mm.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Field, Section, Segmented, Select, Toggle } from '../ui.js';
import { useStore } from '../state.js';
import { app, boot, updateBin, setBinIcon } from '../app.js';

const SIZES = ['M2', 'M2.5', 'M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12'];
const BINS = [['single', 'One'], ['dual', 'Two'], ['quad', 'Four']];
const DRIVES = [
  ['internal_hex', 'Allen'], ['external_hex', 'Hex'], ['phillips', 'PH'], ['pozidriv', 'PZ'],
  ['torx', 'Torx'], ['slotted', 'Slot'], ['none', 'None'],
];
const PART_ICONS = [
  ['ball_bearing', 'Bearing'], ['linear_bearing', 'Linear bearing'], ['spring', 'Spring'], ['wago', 'WAGO'],
  ['terminal_block', 'Terminal block'], ['jst', 'JST'], ['fuse', 'Fuse'], ['resistor', 'Resistor'],
  ['capacitor', 'Capacitor'], ['led', 'LED'], ['none', 'None'],
];

// A plain number is a length and prints as "x30"; anything else prints as typed
const formatLength = (text) => (/^\d+(?:[.,]\d+)?$/.test(text.trim()) ? `x${text.trim()}` : text);
const unformatLength = (text) => {
  const m = String(text || '').trim().match(/^[x×]\s*(\d+(?:[.,]\d+)?)$/i);
  return m ? m[1] : String(text || '');
};

// A text box with suggestions that still takes anything typed
function Suggest({ label, value, options, placeholder, onChange, hint }) {
  const id = useRef(`list-${Math.random().toString(36).slice(2)}`).current;
  return html`<${Field} label=${label} hint=${hint}>
    <input type="text" list=${id} value=${value} placeholder=${placeholder} autocomplete="off"
      onInput=${(e) => onChange(e.currentTarget.value)} />
    <datalist id=${id}>${options.map((o) => html`<option value=${o} />`)}</datalist>
  <//>`;
}

function Text({ label, value, placeholder, onChange, hint }) {
  return html`<${Field} label=${label} hint=${hint}>
    <input type="text" value=${value} placeholder=${placeholder} autocomplete="off"
      onInput=${(e) => onChange(e.currentTarget.value)} />
  <//>`;
}

function Length({ value, field, placeholder, label }) {
  return html`<input type="text" inputmode="decimal" aria-label=${label} value=${unformatLength(value)}
    placeholder=${placeholder} onInput=${(e) => updateBin({ [field]: formatLength(e.currentTarget.value) })} />`;
}

function IconPicker({ icon, options, value, field }) {
  const { phase } = useStore(boot);
  const fileRef = useRef(null);
  const [thumb, setThumb] = useState(null);
  useEffect(() => {
    if (!icon || value !== 'custom') { setThumb(null); return undefined; }
    const url = URL.createObjectURL(new Blob([icon.data]));
    setThumb(url);
    return () => URL.revokeObjectURL(url);
  }, [icon, value]);

  const choices = value === 'custom' ? [...options, ['custom', icon ? icon.name : 'Own picture']] : options;
  const onFile = async (e) => {
    const file = e.currentTarget.files[0];
    e.currentTarget.value = '';
    if (file) await setBinIcon(file);
  };
  return html`<div class="row icon-row">
    <${Select} label="Icon" value=${value} options=${choices} onChange=${(v) => updateBin({ [field]: v })} />
    ${thumb && html`<img class="picture-thumb small" src=${thumb} alt="" />`}
    <button class="secondary" disabled=${phase !== 'ready'} onClick=${() => fileRef.current.click()}>Own picture</button>
    <input ref=${fileRef} type="file" accept="image/*" hidden onChange=${onFile} />
  </div>`;
}

function FastenerForm({ cfg, names }) {
  const mode = cfg.compartment_mode;
  let lengths;
  if (mode === 'single') {
    lengths = html`<div class="length-grid one">
      <${Length} label="Length" value=${cfg.length_single} field="length_single" placeholder="20" />
      <input type="text" aria-label="Note" value=${cfg.standard_line1} placeholder="Note, e.g. DIN 933 8.8"
        onInput=${(e) => updateBin({ standard_line1: e.currentTarget.value })} />
    </div>`;
  } else if (mode === 'quad') {
    lengths = html`<div class="length-grid quad">
      ${[1, 2, 3, 4].map((n) => html`<${Length} label=${`Bin ${n}`} value=${cfg[`length_quad_${n}`]} field=${`length_quad_${n}`} />`)}
    </div>`;
  } else if (mode === 'assortment') {
    // Older labels: two lines of text instead of lengths; the Bins buttons switch away from it
    lengths = html`<div class="length-grid">
      <input type="text" aria-label="Line 1" value=${cfg.assortment_line1} onInput=${(e) => updateBin({ assortment_line1: e.currentTarget.value })} />
      <input type="text" aria-label="Line 2" value=${cfg.assortment_line2} onInput=${(e) => updateBin({ assortment_line2: e.currentTarget.value })} />
    </div>`;
  } else {
    lengths = html`<div class="length-grid">
      <${Length} label="Bin 1" value=${cfg.length_dual_1} field="length_dual_1" />
      <${Length} label="Bin 2" value=${cfg.length_dual_2} field="length_dual_2" />
    </div>`;
  }
  const builtInDrive = DRIVES.some(([v]) => v === cfg.tool_type && v !== 'none');
  return html`
    <div class="row">
      <${Suggest} label="Size" value=${cfg.thread_size} options=${SIZES} placeholder="M3"
        onChange=${(thread_size) => updateBin({ thread_size })} />
      <${Suggest} label="Name" value=${cfg.category} options=${names} placeholder="SCREWS"
        onChange=${(category) => updateBin({ category })} />
    </div>
    <p class="hint">Type your own size too, like 1/4" or #6-32.</p>
    <${Segmented} label="Bins" options=${BINS} value=${mode === 'assortment' ? '' : mode}
      onChange=${(compartment_mode) => updateBin({ compartment_mode })} />
    <${Field} label=${mode === 'single' ? 'Length and note' : 'Lengths'} hint="Numbers print as x30.">${lengths}<//>
    <${IconPicker} icon=${cfg.icon} value=${cfg.tool_type} field="tool_type"
      options=${cfg.tool_type === 'washer' ? [...DRIVES, ['washer', 'Washer']] : DRIVES} />
    <div class="row">
      <${Text} label="Drive size" value=${cfg.tool_size} placeholder="2.5" onChange=${(tool_size) => updateBin({ tool_size })} />
    </div>
    <${Toggle} label="Simple drive icon" checked=${cfg.simple_drive_icon} disabled=${!builtInDrive}
      onChange=${(simple_drive_icon) => updateBin({ simple_drive_icon })} />
  `;
}

function PartForm({ cfg, names }) {
  return html`
    <${Suggest} label="Name" value=${cfg.category_banner} options=${names} placeholder="BEARINGS"
      onChange=${(category_banner) => updateBin({ category_banner })} />
    <${Text} label="Part number" value=${cfg.spec_primary} placeholder="608ZZ" onChange=${(spec_primary) => updateBin({ spec_primary })} />
    <${Text} label="Note" value=${cfg.spec_secondary} placeholder="Optional, e.g. 0.2–4.0 mm²" onChange=${(spec_secondary) => updateBin({ spec_secondary })} />
    <${IconPicker} icon=${cfg.icon} value=${cfg.icon_type} field="icon_type" options=${PART_ICONS} />
  `;
}

export function BinEditor() {
  const { bin, binNames } = useStore(app);
  const [widthText, setWidthText] = useState(null);
  if (!bin) return html`<section class="card"><p class="hint">Loading...</p></section>`;
  const cfg = bin[bin.kind];

  const onWidth = (e) => {
    const text = e.currentTarget.value;
    setWidthText(text);
    const mm = Number(text.replace(',', '.'));
    if (mm >= 10) updateBin({ label_width_mm: mm });
  };

  return html`
    <section class="card">
      <${Segmented} label="Label for" options=${[['fastener', 'Fasteners'], ['component', 'Parts']]} value=${bin.kind}
        onChange=${(kind) => { setWidthText(null); updateBin({ kind }); }} />
      ${bin.kind === 'fastener'
        ? html`<${FastenerForm} cfg=${cfg} names=${binNames.fastener} />`
        : html`<${PartForm} cfg=${cfg} names=${binNames.component} />`}
    </section>
    <${Section} id="bin-size" title="Label length" summary=${`${cfg.label_width_mm} mm, 12 mm tape`}>
      <${Field} label="Length in mm" hint="Bin labels are designed for 12 mm tape and always print at 12 mm.">
        <input type="text" inputmode="decimal" value=${widthText ?? String(cfg.label_width_mm)} onInput=${onWidth}
          onBlur=${() => setWidthText(null)} />
      <//>
    <//>`;
}
