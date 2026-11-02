// The label editor: text with its styling toolbar next to the extras (QR code, picture) in
// tabs, then the label's settings in folding cards. The preview and the print button stay in
// view while editing.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { IconPickerSheet } from './icons.js';
import { SaveTemplateSheet } from './templates.js';
import { Icon } from '../icons.js';
import { Field, Menu, Section, Segmented, Select, Sheet, Slider, Toggle, useWide } from '../ui.js';
import { useStore } from '../state.js';
import { Preview } from '../preview.js';
import { markerHtml, stylesAt, everyLineSized } from '../marker-view.js';
import { QR_HELPERS, QR_ROW, helperCode, helperDefaults, looksLikeSite, fitLevel } from '../qr-helpers.js';
import { FontField } from '../font-picker.js';
import { BinCard, BinOptions } from './bin.js';
import { OutletCard, OutletHelp, OutletStyleSection } from './outlet.js';
import { KindSheet } from './kinds.js';
import {
  app, boot, printer, updateLabel, resetSettings, RESET_NOTES, labelDefaults, updateSettings, say, DEFAULT_LABEL, toggleStyle, restyleLines, lineStyleAt,
  setImage, printLabel, connectPrinter, savePicture, feed, FEED_LENGTH_MM, setMode, addToQueue, queueLabelCount, TEXT_SIZES, hasBarcode, hasQr,
  updatePorts, updateOutlet, PORT_COUNTS, PORT_SPACINGS, qrFit, getBorderTiles,
} from '../app.js';

// A line's size is the height of its capital letters in mm, like the Text size option. Auto
// follows that option; − and + step by half a millimetre, and the number can be typed.
const LINE_MM_STEP = 0.5;
const LINE_MM_MIN = 1.5;
const LINE_MM_MAX = 30;  // as core/rich_text.py reads a marker
const LINE_SIZE_NAMES = { large: 'Large', medium: 'Medium', small: 'Small' };
const mmText = (v) => String(Math.round(v * 100) / 100);
const roundTenth = (v) => (v == null ? null : Math.round(v * 10) / 10);
const LINE_ALIGNS = [['', 'Like the label'], ['left', 'Left'], ['center', 'Centre'], ['right', 'Right']];
const ALIGN_ICONS = { '': 'align-auto', left: 'align-left', center: 'align-center', right: 'align-right' };
// Toolbar buttons don't take the focus, so the phone keyboard and the selection stay put
const keepFocus = (e) => e.preventDefault();
const ALIGNS = [['left', 'Left'], ['center', 'Centre'], ['right', 'Right']];
const DIRECTIONS = [['horizontal', 'Horizontal'], ['vertical', 'Vertical'], ['turned', 'Turned']];
const DIRECTION_HINTS = {
  horizontal: 'The text runs along the tape.',
  vertical: 'Letters stand one under another, for tape stuck on upright. Each line is a column.',
  turned: 'The text is turned a quarter, so it reads across tape stuck on upright. Best for short text.',
};
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
  } else if (mode === 'outlet') {
    options = html`${wide ? html`<${OutletHelp} />` : html`<${OutletCard} />`}<${OutletStyleSection} />
      <${PortFontSection} id="outlet-font" kind="outlet" update=${updateOutlet} />`;
  } else {
    // On a phone the text, codes, picture and these options are tabs of one card
    options = !wide ? html`<${PhoneTextCard} />` : html`
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
      ${mode === 'outlet' && wide && html`<${OutletCard} />`}
      <${ActionBar} />
    </div>
    <div class="label-edit-col">
      ${wide ? html`<${SettingsHead} mode=${mode} /><${ModePicker} mode=${mode} />`
        : !text && html`<${SettingsHead} mode=${mode} phone />`}
      ${options}
    </div>
  </div>`;
}

// The kinds of label. The side panel shows the main one, Text label, next to a More tile that
// opens all of them as cards (kinds.js), as the phone's Label button does (main.js). A kind
// marked soon is still being built and stays out of the sheet until it is ready, so each new
// kind only has to drop its soon.
export const MODES = [
  { id: 'text', name: 'Text label', icon: 'text', main: true },
  { id: 'bin', name: 'Bin label', icon: 'bin' },
  { id: 'flag', name: 'Cable flag', icon: 'flag' },
  { id: 'ports', name: 'Port strip', icon: 'ports' },
  { id: 'outlet', name: 'Network outlet', icon: 'outlet' },
  { id: 'breakers', name: 'Breaker strip', icon: 'breaker', soon: true },
  { id: 'asset', name: 'Asset tag', icon: 'asset', soon: true },
  { id: 'date', name: 'Date label', icon: 'calendar', soon: true },
];
export const modeName = (mode) => (MODES.find((m) => m.id === mode) || MODES[0]).name;

// Every kind of label that is ready
export const readyKinds = () => MODES.filter((m) => !m.soon);

// A slim line over the settings with Reset, which works the same for every kind of label. On a
// phone it names the kind of label, which the Label button changes.
function SettingsHead({ mode, phone = false }) {
  const { phase } = useStore(boot);
  return html`<div class="settings-head">
    <span>${phone ? `${modeName(mode)} settings` : 'Kind of label'}</span>
    <button class="link-button reset-settings" disabled=${phase !== 'ready'}
      onClick=${() => { if (confirm(RESET_NOTES[mode])) resetSettings(); }}>
      <${Icon} name="undo" size=${16} /> Reset settings</button>
  </div>`;
}

// The side panel's picker: Text label, and More for every other kind, which shows the kind
// picked from it
function ModePicker({ mode }) {
  const [open, setOpen] = useState(false);
  const other = MODES.find((m) => m.id === mode && !m.main);
  return html`<div class="mode-switch" role="tablist" aria-label="Kind of label">
    ${MODES.filter((m) => m.main).map((m) => html`<button role="tab" aria-selected=${mode === m.id} class=${mode === m.id ? 'on' : ''}
      onClick=${() => setMode(m.id)}><${Icon} name=${m.icon} size=${20} /> ${m.name}</button>`)}
    <button role="tab" aria-selected=${!!other} aria-haspopup="dialog" class=${other ? 'on' : ''} onClick=${() => setOpen(true)}>
      <${Icon} name=${other ? other.icon : 'more'} size=${20} /> ${other ? other.name : 'More'}
      <${Icon} name="chevron" size=${16} /></button>
  </div>
  <${KindSheet} open=${open} onClose=${() => setOpen(false)} kinds=${readyKinds()} />`;
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

function TextEditor() {
  const { label, render } = useStore(app);
  const { phase } = useStore(boot);
  const ref = useRef(null);
  const viewRef = useRef(null);
  const [lineStyle, setLineStyle] = useState(['normal', null]);
  const [lineNo, setLineNo] = useState(0);
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
    setLineNo(area.value.slice(0, area.selectionStart).split('\n').length - 1);
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

  // The caret's line: its letter height (set, or what Auto or a Large/Small marker comes to on the
  // label) and the tallest it can be next to the other lines
  const metrics = render && render.item.mode === 'text' && render.item.label.layout !== 'ports' ? render.metrics : null;
  const shown = (list) => (list && list[lineNo] != null ? list[lineNo] : null);
  const set = typeof lineStyle[0] === 'number' ? lineStyle[0] : null;
  const lineSize = {
    set,
    auto: lineStyle[0] === 'normal',
    // A size the text asks for shows as typed; one the label works out, to a tenth of a mm
    mm: set != null ? set : roundTenth(shown(metrics && metrics.line_sizes_mm)),
    max: shown(metrics && metrics.line_max_mm),
  };
  lineSize.title = lineSize.mm == null ? 'Auto'
    : `${mmText(lineSize.mm)} mm${lineSize.auto ? ' (Auto)' : LINE_SIZE_NAMES[lineStyle[0]] ? ` (${LINE_SIZE_NAMES[lineStyle[0]]})` : ''}`;

  // One even row: the four styles, the line's size, alignment and a new column, then the view
  const styleButton = (style, title, mark) => html`<button class=${`fmt${styles[style] ? ' on' : ''}`} title=${title}
    aria-label=${title.replace(/ \(.*/, '')} aria-pressed=${styles[style]} disabled=${!ready}
    onPointerDown=${keepFocus} onClick=${() => toggle(style)}>${mark}</button>`;

  // On a wide screen the card splits in two: the text, and the extras in tabs beside it
  return html`<div class="text-editor">
    <div class="card-head">
      <label class="card-title" for="label-text">Label text</label>
      <span class="card-head-buttons">
        <button class="secondary icon-only" title="How styling works" aria-label="How styling works"
          onPointerDown=${keepFocus} onClick=${() => setHelpOpen(true)}><${Icon} name="help" size=${20} /></button>
        <button class="secondary" onClick=${() => setText('', 0, 0)} disabled=${!label.text}>Clear</button>
      </span>
    </div>
    <div class="format-tools">
      ${picker === 'size' && html`<${LineSizePicker} size=${lineSize} ready=${ready} onChange=${(v) => restyle({ size: v })} />`}
      ${picker === 'align' && html`<div class="fmt-picker" role="group" aria-label="Line alignment">
        ${LINE_ALIGNS.map(([v, t]) => {
          const on = (lineStyle[1] || '') === v;
          return html`<button class=${`fmt${on ? ' on' : ''}`} aria-pressed=${on} onPointerDown=${keepFocus}
            onClick=${() => { setPicker(null); restyle({ align: v || null }); }}>
            <${Icon} name=${ALIGN_ICONS[v]} size=${18} /><span class="fmt-text">${t}</span></button>`;
        })}
      </div>`}
      <div class="format-bar" role="toolbar" aria-label="Text style">
        ${styleButton('bold', 'Bold (Ctrl+B)', html`<b>B</b>`)}
        ${styleButton('italic', 'Italic (Ctrl+I)', html`<i class="italic-mark">I</i>`)}
        ${styleButton('underline', 'Underline (Ctrl+U)', html`<u>U</u>`)}
        ${styleButton('invert', 'Inverted: white text on black', html`<span class="inv-mark">A</span>`)}
        <span class="fmt-sep" aria-hidden="true"></span>
        <button class=${`fmt${picker === 'size' ? ' on' : ''}`} title=${`Size of this line: ${lineSize.title}`}
          aria-label=${`Line size: ${lineSize.title}`} aria-expanded=${picker === 'size'}
          disabled=${!ready} onPointerDown=${keepFocus} onClick=${() => setPicker(picker === 'size' ? null : 'size')}>
          ${lineSize.mm == null ? html`<span class="size-mark">A<small>a</small></span>` : html`<span class="size-mm">${mmText(lineSize.mm)}</span>`}
          <span class="caret" aria-hidden="true">▾</span></button>
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
      <code>==inverted==</code> <code>[5mm]</code> size <code>---</code> new column</p>
    <${Sheet} open=${helpOpen} title="Styling label text" onClose=${() => setHelpOpen(false)}>
      <${StylingHelp} />
    <//>
  </div>`;
}

// The size row under the toolbar: Auto, then − / the letter height in mm / +. The number can be
// typed (a comma works too); Enter or leaving the box sets it.
function LineSizePicker({ size, ready, onChange }) {
  const [draft, setDraftState] = useState(null);
  // The typed text, also as a ref so Enter and the blur that follows set it only once
  const typed = useRef(null);
  const setDraft = (v) => { typed.current = v; setDraftState(v); };
  const { mm, max, auto } = size;
  const top = max == null ? LINE_MM_MAX : Math.max(LINE_MM_MIN, max);
  // − and + land on the half-millimetre steps, from wherever the line is now
  const down = mm == null ? null : Math.ceil(mm / LINE_MM_STEP - 1e-6) * LINE_MM_STEP - LINE_MM_STEP;
  const up = mm == null ? null : Math.floor(mm / LINE_MM_STEP + 1e-6) * LINE_MM_STEP + LINE_MM_STEP;
  const commit = () => {
    if (typed.current == null) return;
    const v = parseFloat(typed.current.replace(',', '.'));
    setDraft(null);
    if (Number.isFinite(v) && v > 0) onChange(Math.min(Math.max(Math.round(v * 100) / 100, LINE_MM_MIN), LINE_MM_MAX));
  };
  const onKeyDown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { e.preventDefault(); setDraft(null); e.currentTarget.blur(); }
    if (e.key === 'ArrowUp' && up != null && up <= top + 0.01) { e.preventDefault(); setDraft(null); onChange(up); }
    if (e.key === 'ArrowDown' && down != null && down >= LINE_MM_MIN - 0.01) { e.preventDefault(); setDraft(null); onChange(down); }
  };
  return html`<div class="fmt-picker line-size" role="group" aria-label="Line size">
    <button class=${`fmt${auto ? ' on' : ''}`} aria-pressed=${auto} title="Follow the label's Text size" disabled=${!ready}
      onPointerDown=${keepFocus} onClick=${() => onChange('normal')}><span class="fmt-text">Auto</span></button>
    <button class="fmt" aria-label="Smaller" title="Half a millimetre smaller" onPointerDown=${keepFocus}
      disabled=${!ready || down == null || down < LINE_MM_MIN - 0.01} onClick=${() => onChange(down)}>−</button>
    <label class=${`mm-box${auto ? '' : ' on'}`} title="Height of the capital letters. Type a size or use − and +">
      <input type="text" inputmode="decimal" aria-label="Letter height in mm" disabled=${!ready}
        value=${draft != null ? draft : mm == null ? '' : mmText(mm)} placeholder="–"
        onFocus=${(e) => e.currentTarget.select()} onInput=${(e) => setDraft(e.currentTarget.value)}
        onKeyDown=${onKeyDown} onBlur=${commit} />
      <span aria-hidden="true">mm</span>
    </label>
    <button class="fmt" aria-label="Bigger" title=${up != null && up > top + 0.01 ? 'As tall as this line fits next to the others' : 'Half a millimetre bigger'}
      onPointerDown=${keepFocus} disabled=${!ready || up == null || up > top + 0.01} onClick=${() => onChange(up)}>+</button>
  </div>`;
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

// On a wide screen the card splits in two: the text, and the extras in tabs beside it
function TextCard() {
  return html`<section class="card text-card"><div class="text-split"><div class="text-col"><${TextEditor} /></div>
    <div class="insert-col"><${InsertTabs} /></div></div></section>`;
}

// On a phone the text is the first tab of one card, with the codes, the picture and the options,
// so the page stays put: one panel at a time under the pinned preview
function PhoneTextCard() {
  const ref = useRef(null);
  useFitBetween(ref);
  return html`<section class="card insert-card text-card phone-tabs" ref=${ref}><${InsertTabs} phone /></section>`;
}

// Sizes the phone card to fill the room between the pinned preview and the Print bar on any
// screen, so the page never scrolls; the tab's panel scrolls inside the card instead. While
// typing the keyboard takes the room and the text box sizes itself (see useTypingRoom).
function useFitBetween(ref) {
  useEffect(() => {
    let frame = 0;
    const fit = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const card = ref.current;
        const panel = card && card.querySelector('.insert-panel');
        if (!panel) return;
        const main = card.closest('main');
        if (document.body.classList.contains('typing')) { panel.style.height = ''; main.style.paddingBottom = ''; return; }
        const bar = document.querySelector('.action-bar');
        const bottom = bar && bar.getClientRects().length ? bar.getBoundingClientRect().top : window.innerHeight;
        const top = card.getBoundingClientRect().top + window.scrollY;
        const chrome = card.offsetHeight - panel.offsetHeight;
        panel.style.height = `${Math.max(200, Math.floor(bottom - top - chrome - 12))}px`;
        // Leave room below the card for just the Print bar and the page tabs, so the page itself
        // has nothing to scroll
        main.style.paddingBottom = `${Math.floor(window.innerHeight - bottom)}px`;
      });
    };
    fit();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(fit) : null;
    const col = document.querySelector('.label-preview-col');
    if (observer && col) observer.observe(col);
    window.addEventListener('resize', fit);
    document.addEventListener('focusout', fit);
    return () => {
      cancelAnimationFrame(frame);
      const main = document.querySelector('main');
      if (main) main.style.paddingBottom = '';
      if (observer) observer.disconnect();
      window.removeEventListener('resize', fit);
      document.removeEventListener('focusout', fit);
    };
  }, []);
}

// The Settings tab: the label's settings, which scroll inside the card
function PhoneOptionsPanel() {
  const { mode } = useStore(app);
  return html`<div class="phone-options">
    <${SettingsHead} mode=${mode} phone />
    ${mode === 'flag' && html`<${FlagSection} />`}
    <${FontSection} />
    <${TapeSection} length=${mode !== 'flag'} />
    <${AdvancedSection} />
  </div>`;
}
// The Code tab: a QR code or a barcode, one switch apart, since a label rarely has both
let lastCode = null;
function CodePanel() {
  const { label } = useStore(app);
  const [kind, setCode] = useState(lastCode || (hasBarcode(label) && !hasQr(label) ? 'barcode' : 'qr'));
  const setKind = (k) => { lastCode = k; setCode(k); };
  return html`<div class="code-panel">
    <${Segmented} ariaLabel="Kind of code" options=${[['qr', 'QR code'], ['barcode', 'Barcode']]} value=${kind} onChange=${setKind} />
    ${kind === 'qr' ? html`<${QrPanel} />` : html`<${BarcodePanel} />`}
  </div>`;
}
const CODE_TAB = { id: 'code', name: 'Code', icon: 'qr', on: (label) => hasQr(label) || hasBarcode(label), Panel: CodePanel };
const OPTIONS_TAB = { id: 'options', name: 'Settings', icon: 'settings', on: () => false, Panel: PhoneOptionsPanel };

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
    <p>At the start of a line: <code>[3.5mm]</code> letters 3.5 mm tall (the size button sets it, Auto
      follows Text size), <code>&lt;&lt;</code> left, <code>&gt;&lt;</code> centre, <code>&gt;&gt;</code> right.
      The older <code>#</code> large, <code>##</code> medium and <code>-#</code> small still work.</p>
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
    <${Segmented} label="Direction" options=${DIRECTIONS} value=${label.direction || 'horizontal'}
      onChange=${(direction) => updateLabel({ direction })} />
    <p class="hint">${DIRECTION_HINTS[label.direction || 'horizontal']}${label.direction && label.direction !== 'horizontal' && (hasQr(label) || hasBarcode(label) || label.image) ? ' Codes and pictures are left out.' : ''}</p>
    <${BorderField} />
  <//>`;
}

// The border: a button showing the one on the label, which opens the picker
function BorderField() {
  const { label } = useStore(app);
  const { phase } = useStore(boot);
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const tape = label.tape_width_mm;
  useEffect(() => {
    if (phase !== 'ready') return undefined;
    let live = true;
    getBorderTiles(tape, 'Arimo').then((d) => { if (live) setData(d); }).catch(() => {});
    return () => { live = false; };
  }, [tape, phase]);
  const current = data && data.tiles.find((t) => t.id === label.frame);
  const pick = (frame) => { updateLabel({ frame }); setOpen(false); };
  return html`<${Field} label="Border">
    <button type="button" class="border-button" onClick=${() => setOpen(true)} aria-haspopup="dialog">
      <span class="border-thumb">${current ? html`<img src=${current.url} alt="" />` : html`<span class="muted">${label.frame === 'none' ? '' : '…'}</span>`}</span>
      <span class="border-name">${current ? current.name : 'None'}</span>
      <${Icon} name="chevron" size=${18} />
    </button>
    <${BorderSheet} open=${open} data=${data} value=${label.frame} onPick=${pick} onClose=${() => setOpen(false)} />
  <//>`;
}

let lastBorderCategory = null;
function BorderSheet({ open, data, value, onPick, onClose }) {
  const wide = useWide();
  const chosen = data && data.tiles.find((t) => t.id === value);
  const [category, setCategory] = useState(lastBorderCategory || (chosen && chosen.category) || 'simple');
  useEffect(() => { if (open && chosen) setCategory(chosen.category); }, [open]);
  const pickCategory = (c) => { lastBorderCategory = c; setCategory(c); };
  const tiles = data ? data.tiles.filter((t) => t.category === category) : [];
  return html`<${Sheet} open=${open} title="Border" onClose=${onClose} wide=${wide}>
    ${!data ? html`<p class="hint">Drawing the borders…</p>` : html`
      <div class="border-kinds">
        <${Segmented} ariaLabel="Kinds of border" options=${data.categories} value=${category} onChange=${pickCategory} />
      </div>
      <div class="border-grid">
        ${tiles.map((t) => html`<button type="button" class=${t.id === value ? 'border-tile on' : 'border-tile'}
          aria-pressed=${t.id === value} onClick=${() => onPick(t.id)}>
          <span class="border-art"><img src=${t.url} alt="" /></span>
          <span class="border-tile-name">${t.name}</span>
          ${t.id === value && html`<span class="border-check" aria-hidden="true">✓</span>`}
        </button>`)}
      </div>
      <div class="sheet-actions">
        <button type="button" class="secondary" disabled=${value === 'none'} onClick=${() => onPick('none')}>No border</button>
      </div>`}
  <//>`;
}

// Fit fills the tape; a size in mm is the height of a capital letter, the same on every label.
// A line with its own size in the editor ([3.5mm]) keeps it; with Fit the other lines fill the rest. Sizes too tall
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
  // Every line sized in the text: this has nothing left to size, so it rests
  const sized = !ports && everyLineSized(label.text || '');
  return html`<${Segmented} label="Text size" options=${options} value=${chosen} disabled=${sized}
      onChange=${(v) => onChange({ text_height_mm: v === 'fit' ? null : Number(v) })} />
    <p class="hint">${sized ? 'Every line has its own size in the text, so this has no effect. Set a line to Auto to use it again.'
      : TEXT_SIZES.some((v) => !fits(v))
      ? `Sizes over ${Math.floor(max * 10) / 10} mm don't fit this text ${ports ? 'between the dividers' : 'on the tape'}, so they're left out.`
      : ports ? 'Fit makes the text as big as the ports and the tape allow. Every port gets the same size.'
      : 'Fit fills the tape height. A size in mm is the height of a capital letter. Lines given their own size in the text keep it.'}</p>`;
}

// --- Extras next to the text ---------------------------------------------------------------

// The things that can go next to the text, as tabs.
// More kinds are added here.
const INSERTS = [
  { id: 'qr', name: 'QR code', icon: 'qr', on: hasQr, Panel: QrPanel },
  { id: 'barcode', name: 'Barcode', icon: 'barcode', on: hasBarcode, Panel: BarcodePanel },
  { id: 'picture', name: 'Picture', icon: 'image', on: (label) => !!label.image, Panel: PicturePanel },
];
let lastInsert = INSERTS[0].id;

const TEXT_TAB = { id: 'text', name: 'Text', icon: 'text', on: () => false, Panel: TextEditor };
let lastPhoneTab = 'text';
// On a phone: Text, Code, Picture and Settings
const PHONE_TABS = [TEXT_TAB, CODE_TAB, INSERTS.find((t) => t.id === 'picture'), OPTIONS_TAB];

function InsertTabs({ phone = false }) {
  const tabs = phone ? PHONE_TABS : INSERTS;
  const { label } = useStore(app);
  const [tab, setTab] = useState(phone ? lastPhoneTab : lastInsert);
  const pick = (id) => {
    if (phone) lastPhoneTab = id; else lastInsert = id;
    // Switching tabs closes the phone keyboard, so each tab opens at rest
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    setTab(id);
  };
  const current = tabs.find((t) => t.id === tab) || tabs[0];
  return html`<div class="insert-tabs">
    <div class="insert-tab-bar" role="tablist" aria-label=${phone ? 'Label content' : 'Add to the label'}>
      ${tabs.map((t) => html`<button role="tab" id=${`insert-tab-${t.id}`} aria-selected=${t.id === current.id}
        aria-controls="insert-panel" aria-label=${t.name} title=${t.name} class=${[t.id === current.id && 'on', t.on(label) && 'used'].filter(Boolean).join(' ')}
        onClick=${() => pick(t.id)}>
        <span class="tab-icon"><${Icon} name=${t.icon} size=${18} /></span><span class="tab-name">${t.name}</span>${!phone && t.on(label) && html`<span class="on-dot" title="On the label"></span>`}</button>`)}
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

// A one-line field with a small clear button at its right end while it has text in it
function ClearField({ value, onClear, children }) {
  return html`<div class="clear-field">${children}
    ${value && html`<button type="button" class="clear-x" aria-label="Clear" title="Clear"
      onPointerDown=${(e) => e.preventDefault()} onClick=${onClear}><${Icon} name="close" size=${16} /></button>`}
  </div>`;
}

function QrPanel() {
  const { label } = useStore(app);
  const [helper, setHelper] = useState(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const data = label.qr_data || '';
  const open = (h) => setHelper(h);
  return html`<div class="insert-group">
      <div class="field">
        <div class="field-label-row"><label class="field-label" for="qr-data">Content: a link or text</label>
          ${hasQr(label) && html`<${QrFitLine} short data=${data} tape=${label.tape_width_mm} scale=${label.qr_scale} />`}</div>
        <${ClearField} value=${data} onClear=${() => updateLabel({ qr_data: '', qr_enabled: false })}>
          <input id="qr-data" type="text" value=${data} placeholder="https://example.com"
            onInput=${(e) => updateLabel({ qr_data: e.currentTarget.value, qr_enabled: e.currentTarget.value !== '' })} />
        <//>
      </div>
      <div class="qr-helpers" role="group" aria-label="Make the content">
        ${QR_HELPERS.slice(0, QR_ROW).map((h) => html`<button class="secondary" onClick=${() => open(h)}>
          <${Icon} name=${h.icon} size=${18} /><span>${h.name}</span></button>`)}
        <span class="menu-anchor">
          <button class="secondary" aria-haspopup="menu" aria-expanded=${moreOpen} onClick=${() => setMoreOpen(true)}>
            <span>More</span><span class="caret" aria-hidden="true">▾</span></button>
          <${Menu} variant="tiles" open=${moreOpen} onClose=${() => setMoreOpen(false)}
            items=${QR_HELPERS.slice(QR_ROW).map((h) => ({ label: h.name, icon: h.icon, action: () => open(h) }))} />
        </span>
      </div>
      ${looksLikeSite(data) && html`<p class="hint qr-site">Phones show this as text. <button class="link-button"
        onClick=${() => updateLabel({ qr_data: `https://${data.trim()}`, qr_enabled: true })}>Add https://</button> to make it a link.</p>`}
    </div>
    <${Placement} field="qr" position=${label.qr_position} scale=${label.qr_scale} min=${0.6} max=${1.1} />
    ${helper && html`<${Sheet} open=${true} title=${helper.title} onClose=${() => setHelper(null)}>
      <${HelperForm} helper=${helper} onDone=${() => setHelper(null)} />
    <//>`}`;
}

// Whether phones will read the code at this tape width and size
function QrFitLine({ data, tape, scale, short = false }) {
  const [fit, setFit] = useState(null);
  useEffect(() => {
    let live = true;
    const timer = setTimeout(async () => {
      const result = data.trim() ? await qrFit(data, tape, scale) : null;
      if (live) setFit(result);
    }, 150);
    return () => { live = false; clearTimeout(timer); };
  }, [data, tape, scale]);
  const level = fit && fitLevel(fit.dots_per_module);
  if (!level) return null;
  const brief = { ok: 'Scans well', small: 'Hard to scan', dense: 'Too dense' }[level];
  const text = {
    ok: `Should scan well on ${tape} mm tape.`,
    small: `Small squares on ${tape} mm tape: it may need a steady phone. Shorter content helps.`,
    dense: `Too dense for ${tape} mm tape: phones may not read it. Use shorter content, or a bigger size or tape.`,
  }[level];
  return html`<p class=${`qr-fit ${level}`} title=${short ? text : undefined}><span class="qr-fit-dot" aria-hidden="true"></span>${short ? brief : text}</p>`;
}

// A helper's form in a sheet, with the code it makes and how well that scans on this tape
function HelperForm({ helper, onDone }) {
  const { label } = useStore(app);
  const [values, setValues] = useState(() => helperDefaults(helper));
  const [locating, setLocating] = useState(false);
  const set = (change) => setValues({ ...values, ...change });
  const code = helperCode(helper, values);
  const submit = (e) => {
    e.preventDefault();
    if (!code) return;
    updateLabel({ qr_enabled: true, qr_data: code });
    onDone();
  };
  const locate = (key) => {
    if (!navigator.geolocation) { say("This browser can't tell where you are."); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => { setLocating(false); set({ [key]: `${pos.coords.latitude.toFixed(6)}, ${pos.coords.longitude.toFixed(6)}` }); },
      () => { setLocating(false); say("Couldn't get your location. Paste coordinates or a map link instead."); },
      { enableHighAccuracy: true, timeout: 15000 },
    );
  };
  const field = (f) => {
    if (f.when && !f.when(values)) return null;
    const value = values[f.key];
    const onInput = (e) => set({ [f.key]: e.currentTarget.value });
    if (f.type === 'segmented') return html`<${Segmented} label=${f.label} value=${value} options=${f.options} onChange=${(v) => set({ [f.key]: v })} />`;
    if (f.type === 'select') return html`<${Select} label=${f.label} value=${value} options=${f.options} onChange=${(v) => set({ [f.key]: v })} />`;
    if (f.type === 'toggle') return html`<${Toggle} label=${f.label} checked=${value} onChange=${(v) => set({ [f.key]: v })} />`;
    if (f.type === 'textarea') return html`<${Field} label=${f.label}><textarea rows="2" value=${value} placeholder=${f.placeholder || ''} onInput=${onInput}></textarea><//>`;
    const input = html`<input type=${f.type || 'text'} value=${value} required=${f.required} placeholder=${f.placeholder || ''}
      autocomplete="off" onInput=${onInput} />`;
    if (!f.locate) return html`<${Field} label=${f.label}>${input}<//>`;
    return html`<div class="row icon-row"><${Field} label=${f.label}>${input}<//>
      <button type="button" class="secondary" disabled=${locating} onClick=${() => locate(f.key)}>
        <${Icon} name="locate" size=${18} /> ${locating ? 'Finding...' : 'Here'}</button></div>`;
  };
  return html`<form class="helper-form" onSubmit=${submit}>
    ${helper.fields.map(field)}
    <p class="hint">${helper.note}</p>
    ${code && html`<${QrFitLine} data=${code} tape=${label.tape_width_mm} scale=${label.qr_scale} />`}
    <div class="button-row"><button class="primary" type="submit" disabled=${!code}>${helper.button}</button></div>
  </form>`;
}

// Code 128, which holds plain letters, numbers and symbols; the bars keep a width scanners read,
// so Size only changes their height
function BarcodePanel() {
  const { label } = useStore(app);
  const data = label.barcode_data || '';
  return html`<div class="insert-group">
      <${Field} label="Content: a number or code">
        <${ClearField} value=${data} onClear=${() => updateLabel({ barcode_data: '', barcode_enabled: false })}>
          <input type="text" value=${data} placeholder="PN-10432" autocomplete="off" spellcheck="false"
            onInput=${(e) => updateLabel({ barcode_data: e.currentTarget.value, barcode_enabled: e.currentTarget.value !== '' })} />
        <//>
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
    <div class="card-head">
      <h2 class="card-title">On each port</h2>
      <${Segmented} ariaLabel="On each port" options=${PORT_CONTENT} value=${ports.port_use_names ? 'names' : 'numbers'}
        onChange=${(v) => updatePorts({ port_use_names: v === 'names' })} />
    </div>
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

// Font and tape of a label with its own settings: the port strip, or the one under kind (an
// outlet label) with its update function
function PortFontSection({ id = 'port-font', kind = 'ports', update = updatePorts }) {
  const state = useStore(app);
  const { fonts, tapeWidths } = state;
  const label = state[kind];
  const names = fonts.length ? fonts : [label.font_name];
  return html`<${Section} id=${id} title="Font and tape" summary=${`${label.font_name}, ${label.tape_width_mm} mm tape`}>
    <${FontField} label="Font" value=${label.font_name} fonts=${names} onChange=${(font_name) => update({ font_name })} />
    <${TextSizeField} label=${label} onChange=${update} />
    <${Segmented} label="Tape width" options=${tapeWidths.map((w) => [w, `${w} mm`])} value=${label.tape_width_mm}
      onChange=${(tape_width_mm) => update({ tape_width_mm: Number(tape_width_mm) })} />
    <${Select} label="Tape colour in the preview" value=${`${label.tape_bg_color}/${label.tape_fg_color}`}
      options=${TAPE_COLOURS} onChange=${(v) => { const [bg, fg] = v.split('/'); update({ tape_bg_color: bg, tape_fg_color: fg }); }} />
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
      disabled=${label.text_height_mm != null || everyLineSized(label.text || '')}
      display=${label.text_height_mm != null || everyLineSized(label.text || '') ? 'Off for a size in mm' : undefined}
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
  const [saving, setSaving] = useState(false);
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
          { label: 'Save as template', icon: 'templates', action: () => setSaving(true), disabled: !ready },
          { label: 'Save as picture', icon: 'download', action: savePicture, disabled: !render },
          { label: `Feed ${FEED_LENGTH_MM} mm of tape`, icon: 'feed', action: feed, disabled: !p.transport || p.busy || !ready },
        ]} />
      </span>
    </div>
    <${SaveTemplateSheet} open=${saving} onClose=${() => setSaving(false)} />
  </div>`;
}

// The main button: Go to queue while labels wait there, Connect without a printer, or Print
function PrimaryAction() {
  const { render, queue } = useStore(app);
  const p = useStore(printer);
  const { phase } = useStore(boot);
  const ready = phase === 'ready';
  const needsPrinter = p.supported && !p.transport;
  // With labels waiting in the queue, the next step is printing them together
  const queued = queueLabelCount(queue);
  if (queued > 0) {
    return html`<a class="button primary big" href="#/queue" title="Print the queue with this label or without it">
      <${Icon} name="queue" size=${20} /> <span>Go to queue (${queued})</span></a>`;
  }
  if (needsPrinter) {
    return html`<button class="primary big" disabled=${!ready || p.busy} onClick=${connectPrinter}>
      <${Icon} name="printer" size=${20} /> <span>Connect<span class="hide-narrow"> printer</span></span></button>`;
  }
  return html`<button class="primary big" disabled=${!ready || !render || p.busy || !p.supported}
    title="Print (Ctrl+P)" onClick=${printLabel}>
    <${Icon} name="printer" size=${20} /> ${p.busy ? 'Printing...' : 'Print'}</button>`;
}

function AddButton() {
  const { phase } = useStore(boot);
  return html`<button class="secondary big" disabled=${phase !== 'ready'} title="Add to queue (Ctrl+Enter)" onClick=${addToQueue}>
    <${Icon} name="queue" size=${20} /><span class="hide-narrow">Add to queue</span><span class="show-narrow">Add</span>
  </button>`;
}
