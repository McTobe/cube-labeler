// The label editor: text with its styling toolbar, then the label's options in folding cards.
// The preview and the print button stay in view while editing.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { IconPickerSheet } from './icons.js';
import { Icon } from '../icons.js';
import { Field, Menu, Section, Segmented, Select, Sheet, Slider, Toggle, useWide } from '../ui.js';
import { useStore } from '../state.js';
import { Preview } from '../preview.js';
import { BinCard, BinOptions } from './bin.js';
import {
  app, boot, printer, updateLabel, resetLabelSettings, toggleStyle, restyleLines, lineStyleAt,
  addFont, setImage, printLabel, connectPrinter, savePicture, feed, FEED_LENGTH_MM, setMode, addToQueue, queueLabelCount,
} from '../app.js';

const LINE_SIZES = [['large', 'Large'], ['medium', 'Medium'], ['normal', 'Normal'], ['small', 'Small']];
const LINE_ALIGNS = [['', 'Like the label'], ['left', 'Left'], ['center', 'Centre'], ['right', 'Right']];
const ALIGNS = [['left', 'Left'], ['center', 'Centre'], ['right', 'Right']];
const FRAMES = [['none', 'None'], ['box', 'Box'], ['rounded', 'Rounded']];
const SIDES = [['left', 'Left of text'], ['right', 'Right of text']];
const TAPE_COLOURS = [
  ['#FFFFFF/#000000', 'White tape, black text'],
  ['#FDD835/#000000', 'Yellow tape, black text'],
  ['#E53935/#FFFFFF', 'Red tape, white text'],
  ['#1E88E5/#FFFFFF', 'Blue tape, white text'],
  ['#43A047/#FFFFFF', 'Green tape, white text'],
  ['#212121/#FFFFFF', 'Black tape, white text'],
];
const STYLE_KEYS = { b: 'bold', i: 'italic', u: 'underline' };

const pct = (v) => `${Math.round(v * 100)}%`;

export function LabelPage() {
  const { mode } = useStore(app);
  // On a wide screen the text sits under the preview, so both stay in view while typing
  const wide = useWide();
  const textHere = mode === 'text' && wide;
  return html`<div class="label-page">
    <div class="label-preview-col">
      <${Preview} />
      ${textHere && html`<${TextCard} />`}
      ${mode === 'bin' && wide && html`<${BinCard} />`}
      <${ActionBar} />
    </div>
    <div class="label-edit-col">
      <div class="mode-switch" role="tablist" aria-label="Kind of label">
        <button role="tab" aria-selected=${mode === 'text'} class=${mode === 'text' ? 'on' : ''} onClick=${() => setMode('text')}>Text label</button>
        <button role="tab" aria-selected=${mode === 'bin'} class=${mode === 'bin' ? 'on' : ''} onClick=${() => setMode('bin')}>Bin label</button>
      </div>
      ${mode === 'bin' ? html`${!wide && html`<${BinCard} />`}<${BinOptions} />` : html`
        ${!wide && html`<${TextCard} />`}
        <${FontSection} />
        <${QrSection} />
        <${PictureSection} />
        <${TapeSection} />
        <${AdvancedSection} />`}
    </div>
  </div>`;
}

// --- Text ----------------------------------------------------------------------------------

function TextCard() {
  const { label } = useStore(app);
  const { phase } = useStore(boot);
  const ref = useRef(null);
  const [lineStyle, setLineStyle] = useState(['normal', null]);
  const [helpOpen, setHelpOpen] = useState(false);
  const ready = phase === 'ready';

  const syncLineStyle = async () => {
    const area = ref.current;
    if (!area) return;
    setLineStyle(await lineStyleAt(area.value, area.selectionStart));
  };

  const setText = (text, start, end) => {
    updateLabel({ text });
    requestAnimationFrame(() => {
      const area = ref.current;
      area.focus();
      area.setSelectionRange(start, end);
      syncLineStyle();
    });
  };

  const toggle = async (style) => {
    const area = ref.current;
    const [text, start, end] = await toggleStyle(area.value, area.selectionStart, area.selectionEnd, style);
    setText(text, start, end);
  };

  const restyle = async (changes) => {
    const area = ref.current;
    const { selectionStart, selectionEnd, value } = area;
    const text = await restyleLines(value, selectionStart, selectionEnd, changes);
    // Keep the cursor on the same spot in its line, give or take the prefix that changed
    const delta = text.length - value.length;
    setText(text, Math.max(0, selectionStart + delta), Math.max(0, selectionEnd + delta));
  };

  const addColumn = () => {
    const area = ref.current;
    const { value, selectionEnd } = area;
    const lineEnd = value.indexOf('\n', selectionEnd);
    const at = lineEnd === -1 ? value.length : lineEnd;
    const text = `${value.slice(0, at)}\n---\n${value.slice(at)}`;
    setText(text, at + 5, at + 5);
  };

  const onKeyDown = (e) => {
    const key = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && STYLE_KEYS[key] && ready) {
      e.preventDefault();
      toggle(STYLE_KEYS[key]);
    }
  };

  return html`<section class="card text-card">
    <div class="card-head">
      <label class="card-title" for="label-text">Label text</label>
      <button class="link-button" onClick=${() => setText('', 0, 0)} disabled=${!label.text}>Clear</button>
    </div>
    <div class="format-bar" role="toolbar" aria-label="Text style">
      <button class="fmt" title="Bold (Ctrl+B)" aria-label="Bold" disabled=${!ready} onClick=${() => toggle('bold')}><b>B</b></button>
      <button class="fmt" title="Italic (Ctrl+I)" aria-label="Italic" disabled=${!ready} onClick=${() => toggle('italic')}><i>I</i></button>
      <button class="fmt" title="Underline (Ctrl+U)" aria-label="Underline" disabled=${!ready} onClick=${() => toggle('underline')}><u>U</u></button>
      <button class="fmt inverted" title="White text on black" disabled=${!ready} onClick=${() => toggle('invert')}>Inverted</button>
      <span class="format-sep" aria-hidden="true"></span>
      <select class="fmt-select" aria-label="Line size" title="Size of this line" disabled=${!ready}
        value=${lineStyle[0]} onChange=${(e) => restyle({ size: e.currentTarget.value })}>
        ${LINE_SIZES.map(([v, t]) => html`<option value=${v}>${t}</option>`)}
      </select>
      <select class="fmt-select" aria-label="Line alignment" title="Alignment of this line" disabled=${!ready}
        value=${lineStyle[1] || ''} onChange=${(e) => restyle({ align: e.currentTarget.value || null })}>
        ${LINE_ALIGNS.map(([v, t]) => html`<option value=${v}>${t}</option>`)}
      </select>
      <button class="fmt" title="Add a column" disabled=${!ready} onClick=${addColumn}><${Icon} name="column" size=${18} /><span class="fmt-text">Column</span></button>
      <button class="fmt" title="How styling works" aria-label="How styling works" onClick=${() => setHelpOpen(true)}><${Icon} name="help" size=${18} /></button>
    </div>
    <textarea id="label-text" ref=${ref} rows="3" value=${label.text} spellcheck="false"
      placeholder="Type your label"
      onInput=${(e) => { updateLabel({ text: e.currentTarget.value }); syncLineStyle(); }}
      onKeyDown=${onKeyDown} onKeyUp=${syncLineStyle} onClick=${syncLineStyle} onFocus=${syncLineStyle}></textarea>
    <${Sheet} open=${helpOpen} title="Styling label text" onClose=${() => setHelpOpen(false)}>
      <${StylingHelp} />
    <//>
  </section>`;
}

function StylingHelp() {
  return html`<div class="help-text">
    <p>Select text and use the buttons, or type the markers yourself:</p>
    <table class="markers">
      <tr><td><code>**bold**</code></td><td><b>bold</b></td></tr>
      <tr><td><code>*italic*</code></td><td><i>italic</i></td></tr>
      <tr><td><code>__underline__</code></td><td><u>underline</u></td></tr>
      <tr><td><code>==inverted==</code></td><td><span class="inverted-sample">inverted</span></td></tr>
    </table>
    <p>At the start of a line: <code>#</code> large, <code>##</code> medium, <code>-#</code> small,
      <code>&lt;&lt;</code> left, <code>&gt;&lt;</code> centre, <code>&gt;&gt;</code> right.</p>
    <p>A line with only <code>---</code> starts a new column with a divider line.</p>
    <p>Put a backslash before a marker to print it as it is, as in <code>M3 \\* 8</code>.</p>
  </div>`;
}

// --- Options -------------------------------------------------------------------------------

function FontSection() {
  const { label, fonts, render } = useStore(app);
  const { phase } = useStore(boot);
  const fileRef = useRef(null);
  const names = fonts.length ? fonts : [label.font_name];
  const autoSize = render && render.metrics.effective_font_size;

  const onFile = async (e) => {
    const file = e.currentTarget.files[0];
    e.currentTarget.value = '';
    if (file) await addFont(file);
  };

  return html`<${Section} id="font" title="Font and size" summary=${`${label.font_name}, ${label.auto_fit_font ? 'fit to tape' : `${label.fixed_font_size} pt`}`}>
    <div class="row">
      <${Select} label="Font" value=${label.font_name} options=${names.map((n) => [n, n])}
        onChange=${(font_name) => updateLabel({ font_name })} />
      <button class="secondary add-font" disabled=${phase !== 'ready'} onClick=${() => fileRef.current.click()}>Add font</button>
      <input ref=${fileRef} type="file" accept=".ttf,.otf,.ttc" hidden onChange=${onFile} />
    </div>
    <${Toggle} label="Fit to tape height" checked=${label.auto_fit_font}
      onChange=${(auto_fit_font) => updateLabel({ auto_fit_font })} />
    <${Slider} label="Size" min=${8} max=${80} value=${label.fixed_font_size} disabled=${label.auto_fit_font}
      display=${label.auto_fit_font ? (autoSize ? `Auto (${autoSize} pt)` : 'Auto') : `${label.fixed_font_size} pt`}
      onChange=${(fixed_font_size) => updateLabel({ fixed_font_size })} />
    <${Segmented} label="Alignment" options=${ALIGNS} value=${label.alignment}
      onChange=${(alignment) => updateLabel({ alignment })} />
    <${Segmented} label="Frame" options=${FRAMES} value=${label.frame}
      onChange=${(frame) => updateLabel({ frame })} />
  <//>`;
}

function wifiCode({ ssid, password, security, hidden }) {
  const esc = (s) => s.replace(/([\;,:"])/g, '\\$1');
  let code = `WIFI:T:${security};S:${esc(ssid)};`;
  if (security !== 'nopass') code += `P:${esc(password)};`;
  if (hidden) code += 'H:true;';
  return `${code};`;
}

function WifiForm({ onDone }) {
  const [wifi, setWifi] = useState({ ssid: '', password: '', security: 'WPA', hidden: false });
  const set = (change) => setWifi({ ...wifi, ...change });
  const submit = (e) => {
    e.preventDefault();
    updateLabel({ qr_enabled: true, qr_data: wifiCode(wifi) });
    onDone();
  };
  return html`<form class="wifi-form" onSubmit=${submit}>
    <${Field} label="Network name"><input required value=${wifi.ssid} autocomplete="off" onInput=${(e) => set({ ssid: e.currentTarget.value })} /><//>
    <${Segmented} label="Security" value=${wifi.security} options=${[['WPA', 'WPA/WPA2/WPA3'], ['WEP', 'WEP'], ['nopass', 'None']]}
      onChange=${(security) => set({ security })} />
    ${wifi.security !== 'nopass' && html`<${Field} label="Password">
      <input value=${wifi.password} autocomplete="off" onInput=${(e) => set({ password: e.currentTarget.value })} /><//>`}
    <${Toggle} label="Hidden network" checked=${wifi.hidden} onChange=${(hidden) => set({ hidden })} />
    <p class="hint">Phones that scan the code join the network. Anyone who sees the label can read the password.</p>
    <div class="button-row"><button class="primary" type="submit">Use this network</button></div>
  </form>`;
}

function QrSection() {
  const { label } = useStore(app);
  const [wifiOpen, setWifiOpen] = useState(false);
  return html`<${Section} id="qr" title="QR code" defaultOpen=${false} summary=${label.qr_enabled ? 'On' : 'Off'}>
    <${Toggle} label="Add a QR code" checked=${label.qr_enabled} onChange=${(qr_enabled) => updateLabel({ qr_enabled })} />
    <${Field} label="Content: a link, text, or Wi-Fi details">
      <input type="text" value=${label.qr_data} placeholder="https://example.com"
        onInput=${(e) => updateLabel({ qr_data: e.currentTarget.value, qr_enabled: label.qr_enabled || e.currentTarget.value !== '' })} />
    <//>
    <button class="secondary" onClick=${() => setWifiOpen(true)}>Make a Wi-Fi QR code</button>
    <${Segmented} label="Position" options=${SIDES} value=${label.qr_position}
      onChange=${(qr_position) => updateLabel({ qr_position })} />
    <${Slider} label="Size" min=${0.6} max=${1.1} step=${0.05} value=${label.qr_scale} format=${pct}
      onChange=${(qr_scale) => updateLabel({ qr_scale })} />
    <${Sheet} open=${wifiOpen} title="Wi-Fi QR code" onClose=${() => setWifiOpen(false)}>
      <${WifiForm} onDone=${() => setWifiOpen(false)} />
    <//>
  <//>`;
}

function PictureSection() {
  const { label } = useStore(app);
  const { phase } = useStore(boot);
  const fileRef = useRef(null);
  const [thumb, setThumb] = useState(null);
  const [picking, setPicking] = useState(false);

  useEffect(() => {
    if (!label.image) { setThumb(null); return undefined; }
    const url = URL.createObjectURL(new Blob([label.image.data]));
    setThumb(url);
    return () => URL.revokeObjectURL(url);
  }, [label.image]);

  const onFile = async (e) => {
    const file = e.currentTarget.files[0];
    e.currentTarget.value = '';
    if (file) await setImage(file);
  };

  return html`<${Section} id="picture" title="Picture" defaultOpen=${false} summary=${label.image ? label.image.name : 'None'}>
    <div class="picture-row">
      ${thumb ? html`<img class="picture-thumb" src=${thumb} alt="" />` : html`<span class="picture-thumb empty"><${Icon} name="image" /></span>`}
      <span class="picture-name">${label.image ? label.image.name : 'No picture'}</span>
      ${label.image && html`<button class="link-button" onClick=${() => setImage(null)}>Remove</button>`}
    </div>
    <div class="button-row">
      <button class="secondary" disabled=${phase !== 'ready'} onClick=${() => setPicking(true)}>Icon library</button>
      <button class="secondary" disabled=${phase !== 'ready'} onClick=${() => fileRef.current.click()}>Your own picture</button>
    </div>
    <input ref=${fileRef} type="file" accept="image/*" hidden onChange=${onFile} />
    <${IconPickerSheet} open=${picking} target="text" onClose=${() => setPicking(false)} />
    <${Segmented} label="Position" options=${SIDES} value=${label.image_position}
      onChange=${(image_position) => updateLabel({ image_position })} />
    <${Slider} label="Size" min=${0.3} max=${1.5} step=${0.05} value=${label.image_scale} format=${pct}
      onChange=${(image_scale) => updateLabel({ image_scale })} />
  <//>`;
}

function TapeSection() {
  const { label, tapeWidths } = useStore(app);
  const [lengthText, setLengthText] = useState(label.fixed_width_mm == null ? '' : String(label.fixed_width_mm));

  useEffect(() => {
    const shown = lengthText.trim() === '' ? null : Number(lengthText);
    if (shown !== label.fixed_width_mm) setLengthText(label.fixed_width_mm == null ? '' : String(label.fixed_width_mm));
  }, [label.fixed_width_mm]);

  const onLength = (e) => {
    const text = e.currentTarget.value;
    setLengthText(text);
    const value = Number(text.replace(',', '.'));
    updateLabel({ fixed_width_mm: text.trim() !== '' && value > 0 ? value : null });
  };

  return html`<${Section} id="tape" title="Tape and length" summary=${`${label.tape_width_mm} mm${label.fixed_width_mm ? `, ${label.fixed_width_mm} mm long` : ''}`}>
    <${Segmented} label="Tape width" options=${tapeWidths.map((w) => [w, `${w} mm`])} value=${label.tape_width_mm}
      onChange=${(tape_width_mm) => updateLabel({ tape_width_mm: Number(tape_width_mm) })} />
    <${Field} label="Length in mm" hint="Leave empty to fit the content.">
      <input type="text" inputmode="decimal" value=${lengthText} placeholder="Automatic" onInput=${onLength} />
    <//>
    <${Select} label="Tape colour in the preview" value=${`${label.tape_bg_color}/${label.tape_fg_color}`}
      options=${TAPE_COLOURS} onChange=${(v) => { const [bg, fg] = v.split('/'); updateLabel({ tape_bg_color: bg, tape_fg_color: fg }); }} />
  <//>`;
}

function AdvancedSection() {
  const { label } = useStore(app);
  return html`<${Section} id="advanced" title="Advanced" defaultOpen=${false}>
    <${Slider} label="Text scale" min=${50} max=${150} step=${5} value=${label.font_scale} format=${(v) => `${v}%`}
      onChange=${(font_scale) => updateLabel({ font_scale })} />
    <${Slider} label="Line spacing" min=${0.8} max=${2} step=${0.05} value=${label.line_spacing} format=${(v) => `${v.toFixed(2)}×`}
      onChange=${(line_spacing) => updateLabel({ line_spacing })} />
    <${Slider} label="Side padding" min=${0} max=${40} value=${label.h_padding} format=${(v) => `${v} dots`}
      onChange=${(h_padding) => updateLabel({ h_padding })} />
    <${Slider} label="Outline" min=${0} max=${4} value=${label.stroke_width} format=${(v) => `${v} dots`}
      onChange=${(stroke_width) => updateLabel({ stroke_width })} />
    <${Slider} label="Darkness cutoff" min=${20} max=${220} step=${5} value=${label.threshold}
      onChange=${(threshold) => updateLabel({ threshold })} />

    <button class="secondary" onClick=${() => { if (confirm('Reset font, size, QR code, picture and tape settings? Your text is kept.')) resetLabelSettings(); }}>Reset settings</button>
  <//>`;
}

// --- Print ---------------------------------------------------------------------------------

function ActionBar() {
  const { render, status, queue } = useStore(app);
  const p = useStore(printer);
  const { phase } = useStore(boot);
  const [menuOpen, setMenuOpen] = useState(false);
  const ready = phase === 'ready';

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'p') {
        e.preventDefault();
        if (ready && p.transport && !p.busy) printLabel();
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (ready) addToQueue();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [ready, p.transport, p.busy]);

  const needsPrinter = p.supported && !p.transport;
  // With labels waiting in the queue, the next step is printing them together
  const queued = queueLabelCount(queue);
  return html`<div class="action-bar">
    <p class=${`status-line${status.error ? ' error' : ''}`} role="status">${status.text}</p>
    <div class="action-buttons">
      ${queued > 0
        ? html`<a class="button primary big" href="#/queue" title="Print the queue with this label or without it">
            <${Icon} name="queue" size=${20} /> <span>Go to queue (${queued})</span></a>`
        : needsPrinter
        ? html`<button class="primary big" disabled=${!ready || p.busy} onClick=${connectPrinter}>
            <${Icon} name="printer" size=${20} /> <span>Connect<span class="hide-narrow"> printer</span></span></button>`
        : html`<button class="primary big" disabled=${!ready || !render || p.busy || !p.supported}
            title="Print (Ctrl+P)" onClick=${printLabel}>
            <${Icon} name="printer" size=${20} /> ${p.busy ? 'Printing...' : 'Print'}</button>`}
      <button class="secondary big" disabled=${!ready} title="Add to queue (Ctrl+Enter)" onClick=${addToQueue}>
        <${Icon} name="queue" size=${20} /><span class="hide-narrow">Add to queue</span><span class="show-narrow">Queue</span>
      </button>
      <span class="menu-anchor">
        <button class="secondary big icon-only" aria-label="More actions" onClick=${() => setMenuOpen(true)}>
          <${Icon} name="more" /></button>
        <${Menu} open=${menuOpen} onClose=${() => setMenuOpen(false)} items=${[
          queued > 0 && { label: 'Print only this label', icon: 'printer', action: printLabel,
            disabled: !ready || !render || !p.transport || p.busy },
          { label: 'Save as picture', icon: 'download', action: savePicture, disabled: !render },
          { label: `Feed ${FEED_LENGTH_MM} mm of tape`, icon: 'feed', action: feed, disabled: !p.transport || p.busy || !ready },
        ]} />
      </span>
    </div>
  </div>`;
}
