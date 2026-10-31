// The label editor: text with its styling toolbar next to the extras (QR code, picture) in
// tabs, then the label's settings in folding cards. The preview and the print button stay in
// view while editing.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { IconPickerSheet } from './icons.js';
import { Icon } from '../icons.js';
import { Field, Menu, Section, Segmented, Select, Sheet, Slider, Toggle, useWide } from '../ui.js';
import { useStore } from '../state.js';
import { Preview } from '../preview.js';
import { markerHtml, stylesAt } from '../marker-view.js';
import { FontField } from '../font-picker.js';
import { BinCard, BinOptions } from './bin.js';
import {
  app, boot, printer, updateLabel, resetSettings, RESET_NOTES, labelDefaults, updateSettings, say, DEFAULT_LABEL, toggleStyle, restyleLines, lineStyleAt,
  setImage, printLabel, connectPrinter, savePicture, feed, FEED_LENGTH_MM, setMode, addToQueue, queueLabelCount, TEXT_SIZES, hasBarcode,
  updatePorts, PORT_COUNTS, PORT_SPACINGS,
} from '../app.js';

const LINE_SIZES = [['large', 'Large'], ['medium', 'Medium'], ['normal', 'Normal'], ['small', 'Small']];
const LINE_ALIGNS = [['', 'Like the label'], ['left', 'Left'], ['center', 'Centre'], ['right', 'Right']];
const ALIGN_ICONS = { '': 'align-auto', left: 'align-left', center: 'align-center', right: 'align-right' };
const SIZE_MARKS = { large: 'L', medium: 'M', normal: 'N', small: 'S' };
// Toolbar buttons don't take the focus, so the phone keyboard and the selection stay put
const keepFocus = (e) => e.preventDefault();
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
  // A cable flag is the text label printed twice, so it edits the same text
  const text = mode === 'text' || mode === 'flag';
  let options;
  if (mode === 'bin') {
    options = html`${!wide && html`<${BinCard} />`}<${BinOptions} />`;
  } else if (mode === 'ports') {
    options = html`${!wide && html`<${PortCard} />`}<${PortSection} /><${PortFontSection} />`;
  } else {
    options = html`
      ${!wide && html`<${TextCard} /><section class="card insert-card"><${InsertTabs} /></section>`}
      ${mode === 'flag' && html`<${FlagSection} />`}
      <${FontSection} />
      <${TapeSection} length=${mode !== 'flag'} />
      <${AdvancedSection} />`;
  }
  return html`<div class="label-page">
    <div class="label-preview-col">
      <${Preview} />
      ${text && wide && html`<${TextCard} />`}
      ${mode === 'bin' && wide && html`<${BinCard} />`}
      ${mode === 'ports' && wide && html`<${PortCard} />`}
      <${ActionBar} />
    </div>
    <div class="label-edit-col">
      <${SettingsHead} mode=${mode} />
      <${ModePicker} mode=${mode} />
      ${options}
    </div>
  </div>`;
}

// The kinds of label, as tiles two to a row; more kinds add rows
const MODES = [
  { id: 'text', name: 'Text label', icon: 'text' },
  { id: 'bin', name: 'Bin label', icon: 'bin' },
  { id: 'ports', name: 'Port strip', icon: 'ports' },
  { id: 'flag', name: 'Cable flag', icon: 'flag' },
];

// A slim line over the settings with Reset, which works the same for every kind of label
function SettingsHead({ mode }) {
  const { phase } = useStore(boot);
  return html`<div class="settings-head">
    <span>Kind of label</span>
    <button class="link-button reset-settings" disabled=${phase !== 'ready'}
      onClick=${() => { if (confirm(RESET_NOTES[mode])) resetSettings(); }}>
      <${Icon} name="undo" size=${16} /> Reset settings</button>
  </div>`;
}

function ModePicker({ mode }) {
  return html`<div class="mode-switch" role="tablist" aria-label="Kind of label">
    ${MODES.map((m) => html`<button role="tab" aria-selected=${mode === m.id} class=${mode === m.id ? 'on' : ''}
      onClick=${() => setMode(m.id)}><${Icon} name=${m.icon} size=${20} /> ${m.name}</button>`)}
  </div>`;
}

// --- Text ----------------------------------------------------------------------------------

// The styled view of the text box (faded markers) is on unless this device turned it off
const STYLED_KEY = 'cube-labeler-styled-text';
function loadStyled() {
  try { return localStorage.getItem(STYLED_KEY) !== 'off'; } catch { return true; }
}
function saveStyled(on) {
  try { localStorage.setItem(STYLED_KEY, on ? 'on' : 'off'); } catch { /* forgets on reload */ }
}

// On a phone the box grows with the text, up to eight lines, so short labels show whole
const textRows = (text) => Math.min(8, Math.max(3, text.split('\n').length));

const NO_STYLES = { bold: false, italic: false, underline: false, invert: false };

function TextCard() {
  const { label } = useStore(app);
  const { phase } = useStore(boot);
  const ref = useRef(null);
  const viewRef = useRef(null);
  const [lineStyle, setLineStyle] = useState(['normal', null]);
  const [styles, setStyles] = useState(NO_STYLES);
  const [styled, setStyled] = useState(loadStyled);
  const [helpOpen, setHelpOpen] = useState(false);
  // The size or alignment picker open above the toolbar
  const [picker, setPicker] = useState(null);
  const ready = phase === 'ready';
  const wide = useWide();
  useTypingRoom(ref, wide);
  useMarkerView(ref, viewRef, styled, label.text);

  const syncLineStyle = async () => {
    const area = ref.current;
    if (!area) return;
    setStyles(stylesAt(area.value, area.selectionStart));
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

  const switchView = () => {
    setStyled(!styled);
    saveStyled(!styled);
    say(styled ? 'The text box shows the plain markers.' : 'The text box shows the styles, with the markers faded.');
  };

  const onKeyDown = (e) => {
    const key = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && STYLE_KEYS[key] && ready) {
      e.preventDefault();
      toggle(STYLE_KEYS[key]);
    }
  };

  // One even row: the four styles, the line's size, alignment and a new column, then the view
  const styleButton = (style, title, mark) => html`<button class=${`fmt${styles[style] ? ' on' : ''}`} title=${title}
    aria-label=${title.replace(/ \(.*/, '')} aria-pressed=${styles[style]} disabled=${!ready}
    onPointerDown=${keepFocus} onClick=${() => toggle(style)}>${mark}</button>`;

  // On a wide screen the card splits in two: the text, and the extras in tabs beside it
  return html`<section class="card text-card"><div class="text-split"><div class="text-col">
    <div class="card-head">
      <label class="card-title" for="label-text">Label text</label>
      <span class="card-head-buttons">
        <button class="secondary icon-only" title="How styling works" aria-label="How styling works"
          onPointerDown=${keepFocus} onClick=${() => setHelpOpen(true)}><${Icon} name="help" size=${20} /></button>
        <button class="secondary" onClick=${() => setText('', 0, 0)} disabled=${!label.text}>Clear</button>
      </span>
    </div>
    <div class="format-tools">
      ${picker && html`<div class="fmt-picker" role="group" aria-label=${picker === 'size' ? 'Line size' : 'Line alignment'}>
        ${(picker === 'size' ? LINE_SIZES : LINE_ALIGNS).map(([v, t]) => {
          const on = picker === 'size' ? lineStyle[0] === v : (lineStyle[1] || '') === v;
          return html`<button class=${`fmt${on ? ' on' : ''}`} aria-pressed=${on} onPointerDown=${keepFocus}
            onClick=${() => { setPicker(null); restyle(picker === 'size' ? { size: v } : { align: v || null }); }}>
            ${picker === 'align' && html`<${Icon} name=${ALIGN_ICONS[v]} size=${18} />`}<span class="fmt-text">${t}</span></button>`;
        })}
      </div>`}
      <div class="format-bar" role="toolbar" aria-label="Text style">
        ${styleButton('bold', 'Bold (Ctrl+B)', html`<b>B</b>`)}
        ${styleButton('italic', 'Italic (Ctrl+I)', html`<i class="italic-mark">I</i>`)}
        ${styleButton('underline', 'Underline (Ctrl+U)', html`<u>U</u>`)}
        ${styleButton('invert', 'Inverted: white text on black', html`<span class="inv-mark">A</span>`)}
        <span class="fmt-sep" aria-hidden="true"></span>
        <button class=${`fmt${picker === 'size' ? ' on' : ''}`} title=${`Size of this line: ${LINE_SIZES.find(([v]) => v === lineStyle[0])[1]}`}
          aria-label=${`Line size: ${lineStyle[0]}`} aria-expanded=${picker === 'size'}
          disabled=${!ready} onPointerDown=${keepFocus} onClick=${() => setPicker(picker === 'size' ? null : 'size')}>
          <span class="size-mark">A<small>a</small></span><span class="caret" aria-hidden="true">▾</span></button>
        <button class=${`fmt${picker === 'align' ? ' on' : ''}`} title="Alignment of this line" aria-label="Line alignment" aria-expanded=${picker === 'align'}
          disabled=${!ready} onPointerDown=${keepFocus} onClick=${() => setPicker(picker === 'align' ? null : 'align')}>
          <${Icon} name=${ALIGN_ICONS[lineStyle[1] || '']} size=${20} /><span class="caret" aria-hidden="true">▾</span></button>
        <button class="fmt" title="Add a column" aria-label="Add a column" disabled=${!ready} onPointerDown=${keepFocus} onClick=${addColumn}>
          <${Icon} name="column" size=${20} /></button>
        <span class="fmt-sep" aria-hidden="true"></span>
        <button class=${`fmt view-toggle${styled ? ' on' : ''}`} aria-pressed=${styled}
          title=${styled ? 'Styled view: tap to show the plain markers' : 'Plain markers: tap to show the styles'}
          aria-label="Show the styles in the text box" onPointerDown=${keepFocus} onClick=${switchView}>**</button>
      </div>
      ${!wide && html`<${DockActions} />`}
    </div>
    <div class=${`text-box${styled ? ' styled' : ''}`}>
      ${styled && html`<div class="marker-view" ref=${viewRef} aria-hidden="true"></div>`}
      <textarea id="label-text" ref=${ref} rows=${wide ? 3 : textRows(label.text)} value=${label.text} spellcheck="false"
        placeholder="Type your label"
        onInput=${(e) => { updateLabel({ text: e.currentTarget.value }); syncLineStyle(); }}
        onKeyDown=${onKeyDown} onKeyUp=${syncLineStyle} onClick=${syncLineStyle} onFocus=${syncLineStyle}
        onSelect=${syncLineStyle}></textarea>
    </div>
    <p class="hint marker-tips">Or type: <code>**bold**</code> <code>*italic*</code> <code>__underline__</code>
      <code>==inverted==</code> <code># big</code> <code>---</code> new column</p>
    <${Sheet} open=${helpOpen} title="Styling label text" onClose=${() => setHelpOpen(false)}>
      <${StylingHelp} />
    <//>
  </div>${wide && html`<div class="insert-col"><${InsertTabs} /></div>`}</div></section>`;
}

// Keeps the styled layer behind the text box in step with it: the same text, the same width
// (less a scroll bar, if the box has one) and the same scroll position
function useMarkerView(ref, viewRef, styled, text) {
  useEffect(() => {
    const area = ref.current;
    const view = viewRef.current;
    if (!area || !view) return undefined;
    const fit = () => {
      const bar = area.offsetWidth - area.clientWidth - 2;  // the scroll bar, less the two borders
      view.style.paddingRight = `${12 + Math.max(0, Math.round(bar))}px`;
      view.scrollTop = area.scrollTop;
    };
    const paint = () => {
      view.innerHTML = markerHtml(area.value);
      fit();
    };
    paint();
    // Typing shows at once, before the label is drawn again
    area.addEventListener('input', paint);
    area.addEventListener('scroll', fit);
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(fit) : null;
    if (observer) observer.observe(area);
    return () => {
      area.removeEventListener('input', paint);
      area.removeEventListener('scroll', fit);
      if (observer) observer.disconnect();
    };
  }, [styled, text]);
}

// Print (or Connect) and Add, docked under the toolbar while typing on a phone, so a label prints
// without closing the keyboard first
function DockActions() {
  return html`<div class="dock-actions"><${PrimaryAction} keepKeyboard /><${AddButton} keepKeyboard /></div>`;
}

// On a phone, while the keyboard is up for the label text, the page goes back to the top (preview,
// label kind and the text card in view) and the text box stretches down to the toolbar docked on
// the keyboard
function useTypingRoom(ref, wide) {
  useEffect(() => {
    const area = ref.current;
    if (!area || wide) return undefined;
    let timer = null;
    const reset = () => {
      area.style.height = '';
      document.documentElement.style.scrollPaddingBottom = '';
    };
    const fit = () => {
      if (document.activeElement !== area || !document.body.classList.contains('typing')) { reset(); return; }
      const tools = area.closest('.text-card').querySelector('.format-tools');
      const toolsHeight = tools ? tools.offsetHeight : 0;
      window.scrollTo({ top: 0 });
      const room = window.innerHeight - toolsHeight - area.getBoundingClientRect().top - 12;
      area.style.height = `${Math.max(60, room)}px`;
      // The browser keeps the caret in view; it must look above the toolbar for that
      document.documentElement.style.scrollPaddingBottom = `${toolsHeight + 8}px`;
    };
    const later = () => { clearTimeout(timer); timer = setTimeout(fit, 120); };
    area.addEventListener('focus', later);
    area.addEventListener('blur', reset);
    window.addEventListener('resize', later);
    return () => {
      clearTimeout(timer);
      area.removeEventListener('focus', later);
      area.removeEventListener('blur', reset);
      window.removeEventListener('resize', later);
    };
  }, [wide]);
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
    <p>The text box shows the styles, with the markers in pale grey. The <code>**</code> button at the
      end of the toolbar switches it to the plain markers and back. Sizes and alignment only show on the label.</p>
  </div>`;
}

// --- Options -------------------------------------------------------------------------------

function FontSection() {
  const { label, fonts, settings } = useStore(app);
  const names = fonts.length ? fonts : [label.font_name];
  // The font Reset picks, which the user can make their own (it goes with backups and sync)
  const standard = labelDefaults().font_name;
  const makeDefault = () => {
    updateSettings({ default_font: label.font_name === DEFAULT_LABEL.font_name ? null : label.font_name });
    say(`Reset now picks ${label.font_name}.`);
  };

  return html`<${Section} id="font" title="Font and layout" summary=${label.text_height_mm ? `${label.font_name}, ${label.text_height_mm} mm` : label.font_name}>
    <${FontField} label="Font" value=${label.font_name} fonts=${names} onChange=${(font_name) => updateLabel({ font_name })} />
    ${label.font_name !== standard && fonts.includes(label.font_name) && html`<div class="button-row">
      <button class="secondary" onClick=${makeDefault}>Make ${label.font_name} my default</button>
    </div>`}
    <p class="hint">${settings.default_font && fonts.includes(settings.default_font)
      ? `Reset goes back to your default, ${standard}. It goes with your backups and sync.`
      : `Reset goes back to ${standard}. Make a font your default and Reset picks it on every device.`}</p>
    <${TextSizeField} label=${label} onChange=${updateLabel} />
    <${Segmented} label="Alignment" options=${ALIGNS} value=${label.alignment}
      onChange=${(alignment) => updateLabel({ alignment })} />
    <${Segmented} label="Frame" options=${FRAMES} value=${label.frame}
      onChange=${(frame) => updateLabel({ frame })} />
  <//>`;
}

// Fit fills the tape; a size in mm is the height of a capital letter, the same on every label.
// The size menu above the text still makes a line bigger or smaller than that. Sizes too tall
// for the text are left out, and one that stops fitting goes back to Fit (see renderNow).
function TextSizeField({ label, onChange }) {
  const { render } = useStore(app);
  const mm = label.text_height_mm;
  const chosen = TEXT_SIZES.includes(mm) ? String(mm) : 'fit';
  const ports = label.layout === 'ports';
  const metrics = render && render.item.mode === 'text' && (render.item.label.layout === 'ports') === ports ? render.metrics : null;
  const max = metrics && metrics.max_text_height_mm;
  const fits = (v) => max == null || v <= max || String(v) === chosen;
  const options = [['fit', 'Fit'], ...TEXT_SIZES.filter(fits).map((v) => [String(v), `${v} mm`])];
  return html`<${Segmented} label="Text size" options=${options} value=${chosen}
      onChange=${(v) => onChange({ text_height_mm: v === 'fit' ? null : Number(v) })} />
    <p class="hint">${TEXT_SIZES.some((v) => !fits(v))
      ? `Sizes over ${Math.floor(max * 10) / 10} mm don't fit this text ${ports ? 'between the dividers' : 'on the tape'}, so they're left out.`
      : ports ? 'Fit makes the text as big as the ports and the tape allow. Every port gets the same size.'
      : 'Fit fills the tape height. A size in mm is the height of a capital letter, the same on every label.'}</p>`;
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

// --- Extras next to the text ---------------------------------------------------------------

// The things that can go next to the text, as tabs; a dot marks the ones on the label.
// More kinds are added here.
const INSERTS = [
  { id: 'qr', name: 'QR code', icon: 'qr', on: (label) => label.qr_enabled, Panel: QrPanel },
  { id: 'barcode', name: 'Barcode', icon: 'barcode', on: hasBarcode, Panel: BarcodePanel },
  { id: 'picture', name: 'Picture', icon: 'image', on: (label) => !!label.image, Panel: PicturePanel },
];
let lastInsert = INSERTS[0].id;

function InsertTabs() {
  const { label } = useStore(app);
  const [tab, setTab] = useState(lastInsert);
  const pick = (id) => { lastInsert = id; setTab(id); };
  const current = INSERTS.find((t) => t.id === tab) || INSERTS[0];
  return html`<div class="insert-tabs">
    <div class="insert-tab-bar" role="tablist" aria-label="Add to the label">
      ${INSERTS.map((t) => html`<button role="tab" id=${`insert-tab-${t.id}`} aria-selected=${t.id === current.id}
        aria-controls="insert-panel" aria-label=${t.name} title=${t.name} class=${t.id === current.id ? 'on' : ''} onClick=${() => pick(t.id)}>
        <${Icon} name=${t.icon} size=${18} /><span class="tab-name">${t.name}</span>${t.on(label) && html`<span class="on-dot" title="On the label"></span>`}</button>`)}
    </div>
    <div class="insert-panel" id="insert-panel" role="tabpanel" aria-labelledby=${`insert-tab-${current.id}`}>
      <${current.Panel} />
    </div>
  </div>`;
}

// What goes in at the top, then where it sits and how big at the bottom, the same in every tab
function Placement({ position, scale, min, max, field }) {
  return html`<div class="insert-group">
    <${Segmented} label="Position" options=${SIDES} value=${position}
      onChange=${(v) => updateLabel({ [`${field}_position`]: v })} />
    <${Slider} label="Size" min=${min} max=${max} step=${0.05} value=${scale} format=${pct}
      onChange=${(v) => updateLabel({ [`${field}_scale`]: v })} />
  </div>`;
}

function QrPanel() {
  const { label } = useStore(app);
  const [wifiOpen, setWifiOpen] = useState(false);
  return html`<div class="insert-group">
      <${Toggle} label="Add a QR code" checked=${label.qr_enabled} onChange=${(qr_enabled) => updateLabel({ qr_enabled })} />
      <div class="row icon-row">
        <${Field} label="Content: a link or text">
          <input type="text" value=${label.qr_data} placeholder="https://example.com"
            onInput=${(e) => updateLabel({ qr_data: e.currentTarget.value, qr_enabled: e.currentTarget.value !== '' })} />
        <//>
        <button class="secondary" title="Make a code that joins a Wi-Fi network" onClick=${() => setWifiOpen(true)}>
          <${Icon} name="wifi" size=${18} /> Wi-Fi</button>
      </div>
    </div>
    <${Placement} field="qr" position=${label.qr_position} scale=${label.qr_scale} min=${0.6} max=${1.1} />
    <${Sheet} open=${wifiOpen} title="Wi-Fi QR code" onClose=${() => setWifiOpen(false)}>
      <${WifiForm} onDone=${() => setWifiOpen(false)} />
    <//>`;
}

// Code 128, which holds plain letters, numbers and symbols; the bars keep a width scanners read,
// so Size only changes their height
function BarcodePanel() {
  const { label } = useStore(app);
  const data = label.barcode_data || '';
  return html`<div class="insert-group">
      <${Toggle} label="Add a barcode" checked=${!!label.barcode_enabled} onChange=${(barcode_enabled) => updateLabel({ barcode_enabled })} />
      <${Field} label="Content: a number or code">
        <input type="text" value=${data} placeholder="PN-10432" autocomplete="off" spellcheck="false"
          onInput=${(e) => updateLabel({ barcode_data: e.currentTarget.value, barcode_enabled: e.currentTarget.value !== '' })} />
      <//>
      <${Toggle} label="Number under the bars" checked=${label.barcode_show_text !== false}
        onChange=${(barcode_show_text) => updateLabel({ barcode_show_text })} />
    </div>
    <${Placement} field="barcode" position=${label.barcode_position || 'left'} scale=${label.barcode_scale ?? 1} min=${0.6} max=${1} />`;
}

function PicturePanel() {
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

  return html`<div class="insert-group">
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
  </div>
  <${Placement} field="image" position=${label.image_position} scale=${label.image_scale} min=${0.3} max=${1.5} />`;
}

// length is off for a cable flag, which has a length for each side in its own card
function TapeSection({ length = true }) {
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

  return html`<${Section} id="tape" title=${length ? 'Tape and length' : 'Tape'} summary=${`${label.tape_width_mm} mm${length && label.fixed_width_mm ? `, ${label.fixed_width_mm} mm long` : ''}`}>
    <${Segmented} label="Tape width" options=${tapeWidths.map((w) => [w, `${w} mm`])} value=${label.tape_width_mm}
      onChange=${(tape_width_mm) => updateLabel({ tape_width_mm: Number(tape_width_mm) })} />
    ${length && html`<${Field} label="Length in mm" hint="Empty fits the content. A length is exact: content that doesn't fit is cut off.">
      <input type="text" inputmode="decimal" value=${lengthText} placeholder="Automatic" onInput=${onLength} />
    <//>`}
    <${Select} label="Tape colour in the preview" value=${`${label.tape_bg_color}/${label.tape_fg_color}`}
      options=${TAPE_COLOURS} onChange=${(v) => { const [bg, fg] = v.split('/'); updateLabel({ tape_bg_color: bg, tape_fg_color: fg }); }} />
  <//>`;
}

// --- Port strip ----------------------------------------------------------------------------

const PORT_DIVIDERS = [['0', 'None'], ['6', 'Every 6'], ['8', 'Every 8']];
const PORT_CONTENT = [['numbers', 'Numbers'], ['names', 'Names']];

// A number typed into a field: the text as typed, and the value it holds (null while it holds none)
function useNumberText(value, onValue, parse = Number) {
  const [text, setText] = useState(value == null ? '' : String(value));
  useEffect(() => {
    const shown = text.trim() === '' ? null : parse(text.replace(',', '.'));
    if (shown !== value) setText(value == null ? '' : String(value));
  }, [value]);
  const onInput = (e) => {
    const typed = e.currentTarget.value;
    setText(typed);
    const number = parse(typed.replace(',', '.'));
    onValue(typed.trim() !== '' && Number.isFinite(number) ? number : null);
  };
  return [text, onInput];
}

// What goes over each port, under the preview: numbers with a prefix, or a name for each port
function PortCard() {
  const { ports } = useStore(app);
  const [prefix, setPrefix] = useState(ports.port_prefix);
  useEffect(() => { if (ports.port_prefix !== prefix) setPrefix(ports.port_prefix); }, [ports.port_prefix]);
  const names = ports.port_names.split('\n');
  const extra = names.length > ports.port_count && names.slice(ports.port_count).some((n) => n.trim());
  return html`<section class="card port-card">
    <h2 class="card-title">On each port</h2>
    <${Segmented} ariaLabel="On each port" options=${PORT_CONTENT} value=${ports.port_use_names ? 'names' : 'numbers'}
      onChange=${(v) => updatePorts({ port_use_names: v === 'names' })} />
    ${ports.port_use_names ? html`
      <p class="hint">One name per line, such as NAS, Router, Office. An empty line leaves a port blank.</p>
      <textarea class="port-names" rows="4" value=${ports.port_names} spellcheck="false" aria-label="Port names"
        placeholder=${'NAS\nRouter\nOffice'} onInput=${(e) => updatePorts({ port_names: e.currentTarget.value })}></textarea>
      ${extra && html`<p class="hint">Only the first ${ports.port_count} names fit on ${ports.port_count} ports.</p>`}` : html`
      <p class="hint">The ports count up from the First number setting.</p>
      <${Field} label="Before each number">
        <input type="text" value=${prefix} placeholder="Nothing, or A for A1, A2 ..." spellcheck="false"
          onInput=${(e) => { setPrefix(e.currentTarget.value); updatePorts({ port_prefix: e.currentTarget.value }); }} />
      <//>`}
  </section>`;
}

function PortSection() {
  const { ports } = useStore(app);
  const spacing = PORT_SPACINGS.find(([id]) => id === ports.port_spacing) || PORT_SPACINGS[0];
  const [pitchText, onPitch] = useNumberText(ports.port_pitch_mm, (v) => { if (v >= 3 && v <= 60) updatePorts({ port_pitch_mm: v }); });
  const [firstText, onFirst] = useNumberText(ports.port_first, (v) => { if (v != null) updatePorts({ port_first: v }); },
    (t) => (/^\s*-?\d+\s*$/.test(t) ? parseInt(t, 10) : NaN));
  const pickSpacing = (id) => {
    const preset = PORT_SPACINGS.find(([v]) => v === id);
    updatePorts(preset[2] ? { port_spacing: id, port_pitch_mm: preset[2] } : { port_spacing: id });
  };
  const pitch = ports.port_pitch_mm.toFixed(1);
  return html`<${Section} id="ports" title="Port strip" summary=${`${ports.port_count} ports, ${pitch} mm apart`}>
    <${Segmented} label="Ports" options=${PORT_COUNTS.map((n) => [n, String(n)])} value=${ports.port_count}
      onChange=${(port_count) => updatePorts({ port_count: Number(port_count) })} />
    <${Segmented} label="Port spacing" options=${PORT_SPACINGS.map(([id, name]) => [id, name])} value=${spacing[0]}
      onChange=${pickSpacing} />
    ${spacing[2] ? html`<p class="hint">${spacing[1]}: ${pitch} mm from port to port. Measure 6 ports and divide by 6 if yours differ.</p>`
      : html`<${Field} label="Spacing in mm" hint="From the middle of one port to the next. Measure across 6 ports and divide by 6.">
        <input type="text" inputmode="decimal" value=${pitchText} placeholder="19.0" onInput=${onPitch} />
      <//>`}
    ${!ports.port_use_names && html`<${Field} label="First number">
      <input type="text" inputmode="numeric" value=${firstText} placeholder="1" onInput=${onFirst} />
    <//>`}
    <${Segmented} label="Thicker divider" options=${PORT_DIVIDERS} value=${String(ports.port_divider_every || 0)}
      onChange=${(v) => updatePorts({ port_divider_every: Number(v) })} />
  <//>`;
}

function PortFontSection() {
  const { ports, fonts, tapeWidths } = useStore(app);
  const names = fonts.length ? fonts : [ports.font_name];
  return html`<${Section} id="port-font" title="Font and tape" summary=${`${ports.font_name}, ${ports.tape_width_mm} mm tape`}>
    <${FontField} label="Font" value=${ports.font_name} fonts=${names} onChange=${(font_name) => updatePorts({ font_name })} />
    <${TextSizeField} label=${ports} onChange=${updatePorts} />
    <${Segmented} label="Tape width" options=${tapeWidths.map((w) => [w, `${w} mm`])} value=${ports.tape_width_mm}
      onChange=${(tape_width_mm) => updatePorts({ tape_width_mm: Number(tape_width_mm) })} />
    <${Select} label="Tape colour in the preview" value=${`${ports.tape_bg_color}/${ports.tape_fg_color}`}
      options=${TAPE_COLOURS} onChange=${(v) => { const [bg, fg] = v.split('/'); updatePorts({ tape_bg_color: bg, tape_fg_color: fg }); }} />
  <//>`;
}

// --- Cable flag ----------------------------------------------------------------------------

const CABLES = [4, 6, 8];

function FlagSection() {
  const { label } = useStore(app);
  const preset = CABLES.includes(label.flag_cable_mm);
  const [custom, setCustom] = useState(!preset);
  const [cableText, onCable] = useNumberText(label.flag_cable_mm, (v) => { if (v >= 1 && v <= 30) updateLabel({ flag_cable_mm: v }); });
  const [sideText, onSide] = useNumberText(label.flag_side_mm, (v) => updateLabel({ flag_side_mm: v > 0 ? v : null }));
  const chosen = custom || !preset ? 'custom' : String(label.flag_cable_mm);
  const pick = (v) => {
    setCustom(v === 'custom');
    if (v !== 'custom') updateLabel({ flag_cable_mm: Number(v) });
  };
  const wrap = Math.round(Math.PI * label.flag_cable_mm);
  return html`<${Section} id="flag" title="Cable flag" summary=${`${label.flag_cable_mm} mm cable`}>
    <${Segmented} label="Cable thickness" options=${[...CABLES.map((v) => [String(v), `${v} mm`]), ['custom', 'Custom']]}
      value=${chosen} onChange=${pick} />
    ${chosen === 'custom' ? html`<${Field} label="Thickness in mm">
        <input type="text" inputmode="decimal" value=${cableText} placeholder="6" onInput=${onCable} />
      <//>`
      : html`<p class="hint">USB cables are about 4 mm thick, network cables 6 mm and power cords 8 mm.</p>`}
    <p class="hint">The text is printed twice, with ${wrap} mm of blank tape between that goes once round the cable. Fold the two ends together and the flag reads from both sides.</p>
    <${Field} label="Length of each side in mm" hint="Empty fits the text.">
      <input type="text" inputmode="decimal" value=${sideText} placeholder="Automatic" onInput=${onSide} />
    <//>
    <${Toggle} label="Fold marks" checked=${label.flag_fold_marks} onChange=${(flag_fold_marks) => updateLabel({ flag_fold_marks })} />
  <//>`;
}

function AdvancedSection() {
  const { label, previewDots } = useStore(app);
  return html`<${Section} id="advanced" title="Advanced" defaultOpen=${false}>
    <${Slider} label="Text scale" min=${50} max=${150} step=${5} value=${label.font_scale} format=${(v) => `${v}%`}
      disabled=${label.text_height_mm != null} display=${label.text_height_mm != null ? 'Off for a size in mm' : undefined}
      onChange=${(font_scale) => updateLabel({ font_scale })} />
    <${Slider} label="Line spacing" min=${0.8} max=${2} step=${0.05} value=${label.line_spacing} format=${(v) => `${v.toFixed(2)}×`}
      onChange=${(line_spacing) => updateLabel({ line_spacing })} />
    <${Slider} label="Side padding" min=${0} max=${40} value=${label.h_padding} format=${(v) => `${v} dots`}
      onChange=${(h_padding) => updateLabel({ h_padding })} />
    <${Slider} label="Outline" min=${0} max=${4} value=${label.stroke_width} format=${(v) => `${v} dots`}
      onChange=${(stroke_width) => updateLabel({ stroke_width })} />
    <${Slider} label="Darkness cutoff" min=${20} max=${220} step=${5} value=${label.threshold}
      onChange=${(threshold) => updateLabel({ threshold })} />
    <${Toggle} label="Show print dots in the preview" checked=${previewDots}
      onChange=${(on) => app.set({ previewDots: on })} />

  <//>`;
}

// --- Print ---------------------------------------------------------------------------------

function ActionBar() {
  const { render, queue } = useStore(app);
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

  const queued = queueLabelCount(queue);
  return html`<div class="action-bar">
    <div class="action-buttons">
      <${PrimaryAction} />
      <${AddButton} />
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

// The main button: Go to queue while labels wait there, Connect without a printer, or Print
function PrimaryAction({ keepKeyboard = false }) {
  const { render, queue } = useStore(app);
  const p = useStore(printer);
  const { phase } = useStore(boot);
  const ready = phase === 'ready';
  const needsPrinter = p.supported && !p.transport;
  // With labels waiting in the queue, the next step is printing them together
  const queued = queueLabelCount(queue);
  const down = keepKeyboard ? keepFocus : undefined;
  if (queued > 0) {
    return html`<a class="button primary big" href="#/queue" title="Print the queue with this label or without it">
      <${Icon} name="queue" size=${20} /> <span>Go to queue (${queued})</span></a>`;
  }
  if (needsPrinter) {
    return html`<button class="primary big" disabled=${!ready || p.busy} onPointerDown=${down} onClick=${connectPrinter}>
      <${Icon} name="printer" size=${20} /> <span>Connect<span class="hide-narrow"> printer</span></span></button>`;
  }
  return html`<button class="primary big" disabled=${!ready || !render || p.busy || !p.supported}
    title="Print (Ctrl+P)" onPointerDown=${down} onClick=${printLabel}>
    <${Icon} name="printer" size=${20} /> ${p.busy ? 'Printing...' : 'Print'}</button>`;
}

function AddButton({ keepKeyboard = false }) {
  const { phase } = useStore(boot);
  return html`<button class="secondary big" disabled=${phase !== 'ready'} title="Add to queue (Ctrl+Enter)"
    onPointerDown=${keepKeyboard ? keepFocus : undefined} onClick=${addToQueue}>
    <${Icon} name="queue" size=${20} /><span class="hide-narrow">Add to queue</span><span class="show-narrow">Add</span>
  </button>`;
}
