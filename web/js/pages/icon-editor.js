// The icon editor: turns a picture into a black-and-white icon, the same steps as the desktop
// editor (core/icon_editor.py runs in Python). Crop on the picture, tune how it is read, then
// fix single dots with the pencil and eraser. The original, the settings and the touch-ups are
// kept with the icon, so it can be opened and changed again later.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Icon } from '../icons.js';
import { Field, Segmented, Sheet, Slider, Toggle } from '../ui.js';
import { useStore } from '../state.js';
import { app } from '../app.js';
import { prepareIconOriginal, editIcon } from '../app.js';
import { ai, loadAi, currentService, redraw } from '../ai.js';
import { errorMessage } from '../../printer.js';
import {
  library, iconBytes, parseKeywords, saveUserIcon, updateUserIcon, USER_CATEGORY,
} from '../library.js';

const TOUCH_GRID = 64;
const TOUCH_INK = 1;
const TOUCH_ERASE = 2;
const CELL = 6;  // canvas pixels per touch-up cell; the canvas is scaled down to fit by CSS
const UNDO_LIMIT = 30;

const MODES = [['drawing', 'Drawing'], ['silhouette', 'Silhouette'], ['outline', 'Outline']];
const MODE_HINTS = {
  drawing: 'Dark parts become ink. Best for icons, logos and drawings.',
  silhouette: 'Like Drawing, with every enclosed gap filled for a solid shape, like the built-in icons.',
  outline: 'Traces the edges of a photo. Best for photos of a part on a plain background.',
};
const THICKNESS = [[-1, 'Thin'], [0, 'Normal'], [1, 'Bold'], [2, 'Bolder'], [3, 'Heavy']];
const TOOLS = [['look', 'Look'], ['pencil', 'Pencil'], ['eraser', 'Eraser']];
const TOOL_HINTS = {
  look: 'Pick Pencil or Eraser to fix single dots.',
  pencil: 'Tap or drag to add ink.',
  eraser: 'Tap or drag to remove ink.',
};
// A finished icon is already black and white, so a middle cutoff keeps it as it is
const FROM_ICON = { threshold: 128, remove_specks: false };

const blobUrl = (png) => (png ? URL.createObjectURL(new Blob([png], { type: 'image/png' })) : null);

// Names cameras, browsers and AI services give their files, which say nothing about the icon
const NAMELESS = /^(img|image|photo|pic|picture|screenshot|scan|dsc|pxl|download|pasted|gemini|chatgpt|dall|untitled)\b/i;

// "m3_hex-nut.png" gives "M3 hex nut"; "IMG_2041.jpg" or a random "NtXJBc.png" gives nothing
export function suggestedName(fileName) {
  const stem = fileName.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (!stem || NAMELESS.test(stem) || !/[a-z]{2}/i.test(stem)) return '';
  // One word with three or more capitals, some mid-word, like "NtXJBc": a random id
  if (!stem.includes(' ') && /[a-z][A-Z]/.test(stem) && /[A-Z].*[A-Z].*[A-Z]/.test(stem)) return '';
  return stem[0].toUpperCase() + stem.slice(1);
}

// An object URL for a PNG that is let go when the PNG changes or the component goes
function usePngUrl(png) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    const made = blobUrl(png);
    setUrl(made);
    return () => { if (made) URL.revokeObjectURL(made); };
  }, [png]);
  return url;
}

// The picture with a crop box drawn by dragging on it
function CropView({ png, crop, onCrop }) {
  const url = usePngUrl(png);
  const boxRef = useRef(null);
  const [drag, setDrag] = useState(null);
  const share = (e) => {
    const r = boxRef.current.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  };
  const down = (e) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    const p = share(e);
    setDrag([...p, ...p]);
  };
  const move = (e) => { if (drag) { const p = share(e); setDrag([drag[0], drag[1], ...p]); } };
  const up = () => {
    if (!drag) return;
    const [x0, y0, x1, y1] = drag;
    setDrag(null);
    if (Math.abs(x1 - x0) > 0.02 && Math.abs(y1 - y0) > 0.02) {
      onCrop([Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)]);
    }
  };
  const box = drag ? [Math.min(drag[0], drag[2]), Math.min(drag[1], drag[3]), Math.max(drag[0], drag[2]), Math.max(drag[1], drag[3])] : crop;
  return html`<div class="crop-stage">
    ${url ? html`<div class="crop-box" ref=${boxRef} onPointerDown=${down} onPointerMove=${move} onPointerUp=${up}
      onPointerCancel=${() => setDrag(null)} onDblClick=${() => onCrop(null)}>
      <img src=${url} alt="Your picture" draggable="false" />
      ${box && html`<div class="crop-rect" style=${{
        left: `${box[0] * 100}%`, top: `${box[1] * 100}%`, width: `${(box[2] - box[0]) * 100}%`, height: `${(box[3] - box[1]) * 100}%`,
      }}></div>`}
    </div>` : html`<p class="hint">Loading the picture…</p>`}
  </div>`;
}

// The icon, big, with the touch-up cells drawn over it right away while you draw
function TouchCanvas({ basePng, touch, tool, onStroke, onTouch }) {
  const ref = useRef(null);
  const [base, setBase] = useState(null);
  const stroke = useRef(null);

  useEffect(() => {
    let cancelled = false;
    if (!basePng) { setBase(null); return undefined; }
    createImageBitmap(new Blob([basePng], { type: 'image/png' })).then((bitmap) => { if (!cancelled) setBase(bitmap); });
    return () => { cancelled = true; };
  }, [basePng]);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext('2d');
    const side = TOUCH_GRID * CELL;
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, side, side);
    if (base) ctx.drawImage(base, 0, 0, side, side);
    const tint = tool !== 'look';
    for (let i = 0; i < touch.length; i++) {
      if (!touch[i]) continue;
      if (touch[i] === TOUCH_INK) ctx.fillStyle = tint ? '#1f6aa5' : '#000';
      else ctx.fillStyle = tint ? '#fca5a5' : '#fff';
      ctx.fillRect((i % TOUCH_GRID) * CELL, Math.floor(i / TOUCH_GRID) * CELL, CELL, CELL);
    }
  }, [base, touch, tool]);

  const cellAt = (e) => {
    const r = ref.current.getBoundingClientRect();
    const x = Math.floor(((e.clientX - r.left) / r.width) * TOUCH_GRID);
    const y = Math.floor(((e.clientY - r.top) / r.height) * TOUCH_GRID);
    return x >= 0 && y >= 0 && x < TOUCH_GRID && y < TOUCH_GRID ? y * TOUCH_GRID + x : -1;
  };
  // Fills every cell between the last one and this one, so a quick drag leaves no gaps
  const paint = (e) => {
    const cell = cellAt(e);
    const current = stroke.current;
    if (cell < 0 || !current) return;
    const from = current.last ?? cell;
    const x = from % TOUCH_GRID;
    const y = Math.floor(from / TOUCH_GRID);
    const tx = cell % TOUCH_GRID;
    const ty = Math.floor(cell / TOUCH_GRID);
    const steps = Math.max(Math.abs(tx - x), Math.abs(ty - y));
    let changed = false;
    for (let i = 0; i <= steps; i++) {
      const cx = steps ? Math.round(x + ((tx - x) * i) / steps) : tx;
      const cy = steps ? Math.round(y + ((ty - y) * i) / steps) : ty;
      const at = cy * TOUCH_GRID + cx;
      if (current.cells[at] !== current.value) {
        current.cells[at] = current.value;
        changed = true;
      }
    }
    current.last = cell;
    if (changed) onTouch(current.cells.slice());
  };
  const down = (e) => {
    if (tool === 'look' || !basePng) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    // A right click or the eraser removes ink
    const value = tool === 'eraser' || e.button === 2 ? TOUCH_ERASE : TOUCH_INK;
    stroke.current = { value, cells: touch.slice(), last: null };
    onStroke();
    paint(e);
  };
  const up = () => {
    if (stroke.current) {
      stroke.current = null;
      onTouch(null);
    }
  };
  return html`<canvas ref=${ref} class=${`touch-canvas${tool === 'look' ? '' : ' drawing'}`}
    width=${TOUCH_GRID * CELL} height=${TOUCH_GRID * CELL}
    onPointerDown=${down} onPointerMove=${paint} onPointerUp=${up} onPointerCancel=${up}
    onContextMenu=${(e) => e.preventDefault()} aria-label="The icon. Draw on it with the pencil or eraser." />`;
}

// Redraws the picture with the AI service chosen under Settings
function AiBox({ picture, onPicture, onRestore, canRestore }) {
  const state = useStore(ai);
  const { settings } = useStore(app);
  const [preset, setPreset] = useState(null);
  const [custom, setCustom] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState({ text: '', error: false });
  useEffect(() => { loadAi(); }, []);
  if (!state.ready) return null;
  const service = currentService();
  const hasKey = !!state.keys[service.id];
  const chosen = preset || state.presets[0].label;
  const isCustom = chosen === state.custom;
  const run = async () => {
    if (isCustom && !custom.trim()) { setMessage({ text: 'Type how the picture should be redrawn first.', error: true }); return; }
    setBusy(true);
    setMessage({ text: `Asking ${service.name} for an icon. This can take up to a minute…`, error: false });
    try {
      const png = await redraw(picture, chosen, custom);
      const mode = (state.presets.find((p) => p.label === chosen) || { mode: 'drawing' }).mode;
      await onPicture(png, mode);
      setMessage({ text: `${service.name}'s icon is ready. Tune it or touch it up, then save.`, error: false });
    } catch (err) {
      setMessage({ text: errorMessage(err), error: true });
    } finally {
      setBusy(false);
    }
  };
  return html`<div class="ai-box">
    <div class="editor-head">
      <h4><${Icon} name="sparkle" size=${16} /> Redraw it with ${service.name}</h4>
      ${canRestore && !busy && html`<button class="link-button" onClick=${() => onRestore(true)}>Use my picture</button>`}
    </div>
    ${hasKey ? html`<div class="ai-row">
      <select aria-label="Style" value=${chosen} disabled=${busy} onChange=${(e) => setPreset(e.currentTarget.value)}>
        ${[...state.presets.map((p) => [p.label, p.label]), [state.custom, 'Custom: your own words']].map(([v, t]) => html`<option value=${v}>${t}</option>`)}
      </select>
      <button class="primary" disabled=${busy || !picture} onClick=${run}>${busy ? 'Redrawing…' : 'Redraw'}</button>
    </div>
    ${isCustom && html`<input type="text" value=${custom} placeholder="e.g. front view, keep the two screw holes"
      onInput=${(e) => setCustom(e.currentTarget.value)} onKeyDown=${(e) => { if (e.key === 'Enter') run(); }} />`}`
      : html`<p class="hint">Needs your own ${service.name} API key: add it under <a href="#/settings" onClick=${() => onRestore(null)}>Settings</a>.
        ${service.id === 'gemini' ? ' Or make the picture at gemini.google.com and open or paste it here.' : ''}</p>`}
    ${message.text && html`<p class=${`status-line${message.error ? ' error' : ''}`} role="status">${message.text}</p>`}
  </div>`;
}

// What the editor opens with: a picture from a file, one of the user's icons, or a copy
// of an icon. Returns the original, its settings, touch-ups and details.
async function startingPoint(start) {
  if (start.kind === 'picture') {
    return {
      original: await prepareIconOriginal(start.data), edit: null, touch: new Uint8Array(TOUCH_GRID * TOUCH_GRID),
      title: suggestedName(start.name), category: USER_CATEGORY, keywords: '', note: '',
    };
  }
  const { icon } = start;
  const own = start.kind === 'edit' && icon.original && icon.edit;
  const touch = own && icon.touch && icon.touch.length === TOUCH_GRID * TOUCH_GRID
    ? new Uint8Array(icon.touch) : new Uint8Array(TOUCH_GRID * TOUCH_GRID);
  return {
    original: own ? icon.original : await prepareIconOriginal(await iconBytes(icon)),
    edit: own ? icon.edit : FROM_ICON,
    touch,
    title: start.kind === 'edit' ? icon.title : `${icon.title} (my copy)`,
    category: icon.user ? icon.category : (start.kind === 'copy' ? icon.category : USER_CATEGORY),
    keywords: icon.keywords.join(', '),
    note: start.kind === 'edit' && !own ? 'This icon has no original picture kept, so it opens from the icon itself.' : '',
  };
}

function EditorBody({ start, onDone, dirtyRef }) {
  const { categories } = useStore(library);
  const fileRef = useRef(null);
  const [state, setState] = useState(null);  // { original, edit, touch, title, category, keywords, note }
  const [result, setResult] = useState(null);
  const [tool, setTool] = useState('look');
  const [undo, setUndo] = useState([]);
  const [error, setError] = useState('');
  const [drawing, setDrawing] = useState(false);
  const [beforeAi, setBeforeAi] = useState(null);
  const busy = useRef({ running: false, again: false });
  const latest = useRef(null);
  latest.current = state;

  const setDirty = () => { dirtyRef.current = true; };
  const update = (change) => { setDirty(); setState((s) => ({ ...s, ...change })); };
  const changeEdit = (change) => update({ edit: { ...(latest.current.edit || {}), ...change } });

  const loadStart = async (from) => {
    setError('');
    try {
      const point = await startingPoint(from);
      setState(point);
      setUndo([]);
    } catch (err) {
      setError(`Could not open that picture: ${errorMessage(err)}`);
    }
  };
  useEffect(() => { dirtyRef.current = false; loadStart(start); }, [start]);

  // Python redoes the icon after each change; one call at a time, the newest settings win
  const refresh = async () => {
    if (busy.current.running) { busy.current.again = true; return; }
    busy.current.running = true;
    try {
      do {
        busy.current.again = false;
        const s = latest.current;
        if (!s) break;
        try {
          setResult(await editIcon(s.original, s.edit, s.touch));
        } catch (err) {
          setError(errorMessage(err));
        }
      } while (busy.current.again);
    } finally {
      busy.current.running = false;
    }
  };
  useEffect(() => {
    if (!state || drawing) return undefined;
    const timer = setTimeout(refresh, 60);
    return () => clearTimeout(timer);
  }, [state && state.original, state && state.edit, state && state.touch, drawing]);

  // Paste a picture from the clipboard
  useEffect(() => {
    const onPaste = (e) => {
      const item = [...(e.clipboardData ? e.clipboardData.items : [])].find((i) => i.type.startsWith('image/'));
      if (!item) return;
      e.preventDefault();
      item.getAsFile().arrayBuffer().then((buf) => newPicture(new Uint8Array(buf), 'Pasted picture'));
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, []);

  const newPicture = async (data, name) => {
    setError('');
    try {
      const original = await prepareIconOriginal(data);
      const s = latest.current;
      update({
        original, edit: null, touch: new Uint8Array(TOUCH_GRID * TOUCH_GRID),
        title: s && s.title ? s.title : suggestedName(name), note: '',
      });
      setUndo([]);
    } catch (err) {
      setError(`Could not read ${name}: ${errorMessage(err)}`);
    }
  };
  const onFile = async (e) => {
    const file = e.currentTarget.files[0];
    e.currentTarget.value = '';
    if (file) await newPicture(new Uint8Array(await file.arrayBuffer()), file.name);
  };

  if (!state) {
    return html`<div class="editor-loading">${error ? html`<p class="status-line error">${error}</p>` : html`<span class="spinner"></span><p class="hint">Opening…</p>`}</div>`;
  }

  const edit = result ? result.edit : { mode: 'drawing', threshold: null, thickness: 0, remove_specks: true, fill_holes: false, invert: false };
  const shown = { ...edit, ...(state.edit || {}) };
  const auto = shown.threshold == null;
  const canSave = !!(result && result.has_ink) && !drawing;

  const turn = (quarter) => changeEdit({ rotate: (((shown.rotate || 0) + quarter) % 4 + 4) % 4, crop: null });
  const pushUndo = () => setUndo((u) => [...u.slice(-(UNDO_LIMIT - 1)), state.touch]);
  const onTouch = (cells) => {
    if (cells) {
      setDrawing(true);
      setDirty();
      setState((s) => ({ ...s, touch: cells }));
    } else {
      setDrawing(false);
    }
  };
  const undoTouch = () => {
    if (!undo.length) return;
    update({ touch: undo[undo.length - 1] });
    setUndo((u) => u.slice(0, -1));
  };
  const clearTouch = () => {
    if (!state.touch.some(Boolean)) return;
    pushUndo();
    update({ touch: new Uint8Array(TOUCH_GRID * TOUCH_GRID) });
  };

  const save = () => {
    if (!canSave) return;
    const details = {
      title: state.title, category: state.category, keywords: parseKeywords(state.keywords),
      png: result.icon_png, original: state.original, edit: result.edit, touch: state.touch.some(Boolean) ? state.touch : null,
    };
    const icon = start.kind === 'edit' && start.icon.user ? updateUserIcon(start.icon.key, details) : saveUserIcon(details);
    dirtyRef.current = false;
    onDone(icon);
  };

  return html`<div class="icon-editor">
    <section class="editor-picture">
      <div class="editor-head">
        <h3>Picture</h3>
        <span class="editor-tools">
          ${shown.crop && html`<button class="link-button" onClick=${() => changeEdit({ crop: null })}>Show all</button>`}
          <button class="link-button" onClick=${() => fileRef.current.click()}>Another picture</button>
        </span>
        <input ref=${fileRef} type="file" accept="image/*" hidden onChange=${onFile} />
      </div>
      <${CropView} png=${result && result.view_png} crop=${shown.crop} onCrop=${(crop) => changeEdit({ crop })} />
      <p class="hint">Drag on the picture to crop it. You can also paste a picture.</p>
      <${AiBox} picture=${beforeAi || state.original} canRestore=${!!beforeAi}
        onPicture=${async (png, mode) => {
          if (!beforeAi) setBeforeAi(state.original);
          update({ original: await prepareIconOriginal(png), edit: { mode }, touch: new Uint8Array(TOUCH_GRID * TOUCH_GRID) });
          setUndo([]);
        }}
        onRestore=${(restore) => {
          if (!restore) return;
          update({ original: beforeAi, edit: null, touch: new Uint8Array(TOUCH_GRID * TOUCH_GRID) });
          setBeforeAi(null);
          setUndo([]);
        }} />
    </section>

    <section class="editor-result">
      <div class="editor-head">
        <h3>Icon</h3>
        <span class="editor-tools">
          <button class="link-button" disabled=${!undo.length} onClick=${undoTouch}>Undo</button>
          <button class="link-button" onClick=${clearTouch}>Clear touch-ups</button>
        </span>
      </div>
      <div class="tool-row">
        <div class="chip-group tool-pick" role="radiogroup" aria-label="Tool">
          ${TOOLS.map(([id, label]) => html`<button role="radio" aria-checked=${tool === id} class=${tool === id ? 'on' : ''}
            onClick=${() => setTool(id)}>${label}</button>`)}
        </div>
        <span class="turn-buttons">
          <button class="icon-button" aria-label="Turn left" title="Turn left" onClick=${() => turn(-1)}><${Icon} name="rotate-left" size=${18} /></button>
          <button class="icon-button" aria-label="Turn right" title="Turn right" onClick=${() => turn(1)}><${Icon} name="rotate-right" size=${18} /></button>
          <button class=${`icon-button${shown.flip ? ' on' : ''}`} aria-label="Mirror" title="Mirror" aria-pressed=${!!shown.flip}
            onClick=${() => changeEdit({ flip: !shown.flip, crop: null })}><${Icon} name="mirror" size=${18} /></button>
        </span>
      </div>
      <div class="result-row">
        <${TouchCanvas} basePng=${result && result.base_png} touch=${state.touch} tool=${tool}
          onStroke=${pushUndo} onTouch=${onTouch} />
        <${PrintDots} png=${result && result.print_png} />
      </div>
      <p class="hint">${TOOL_HINTS[tool]}</p>
      ${result && !result.has_ink && html`<p class="status-line error">No ink left. Try another darkness cutoff or Swap black and white.</p>`}

      <${Segmented} label="Read the picture as" options=${MODES} value=${shown.mode} onChange=${(mode) => changeEdit({ mode })} />
      <p class="hint mode-hint">${MODE_HINTS[shown.mode]}</p>
      <${Segmented} label="Line thickness" options=${THICKNESS} value=${shown.thickness || 0} onChange=${(thickness) => changeEdit({ thickness })} />
      <details class="fine-tune">
        <summary><span>Fine-tune</span><span class="hint">${fineTuneSummary(shown, auto, result)}</span></summary>
        <${Toggle} label="Automatic darkness cutoff" checked=${auto}
          onChange=${(on) => changeEdit({ threshold: on ? null : (result ? result.threshold : 128) })} />
        <${Slider} label="Darkness cutoff" min=${1} max=${254} value=${auto && result ? result.threshold : (shown.threshold ?? 128)}
          disabled=${auto} display=${auto ? `Automatic (${result ? result.threshold : '…'})` : String(shown.threshold)}
          onChange=${(threshold) => changeEdit({ threshold })} />
        <${Toggle} label="Swap black and white" checked=${!!shown.invert} onChange=${(invert) => changeEdit({ invert })} />
        <${Toggle} label="Remove specks" checked=${!!shown.remove_specks} onChange=${(remove_specks) => changeEdit({ remove_specks })} />
        <${Toggle} label="Fill enclosed gaps" checked=${!!shown.fill_holes} onChange=${(fill_holes) => changeEdit({ fill_holes })} />
        <button class="link-button" onClick=${() => update({ edit: null })}>Reset all settings</button>
      </details>
    </section>

    <section class="editor-details">
      <${Field} label="Name">
        <input type="text" value=${state.title} placeholder="e.g. WAGO 221, M3 hex screw"
          onInput=${(e) => update({ title: e.currentTarget.value })} />
      <//>
      <${Field} label="Category">
        <select value=${state.category} onChange=${(e) => update({ category: e.currentTarget.value })}>
          ${[USER_CATEGORY, ...categories].map((c) => html`<option value=${c}>${c}</option>`)}
        </select>
      <//>
      <${Field} label="Search words, with commas">
        <input type="text" value=${state.keywords} placeholder="e.g. connector, lever"
          onInput=${(e) => update({ keywords: e.currentTarget.value })} />
      <//>
    </section>

    <footer class="editor-actions">
      <p class=${`status-line${error ? ' error' : ''}`}>${error || state.note}</p>
      <button class="secondary" onClick=${() => onDone(null)}>Cancel</button>
      <button class="primary" disabled=${!canSave} onClick=${save}>Save icon</button>
    </footer>
  </div>`;
}

// What Fine-tune holds, folded: only the settings that differ from how a new picture opens
function fineTuneSummary(edit, auto, result) {
  const parts = [auto ? `Cutoff auto${result ? ` (${result.threshold})` : ''}` : `Cutoff ${edit.threshold}`];
  if (edit.invert) parts.push('swapped');
  if (!edit.remove_specks) parts.push('specks kept');
  if (edit.fill_holes) parts.push('gaps filled');
  return parts.join(' · ');
}

function PrintDots({ png }) {
  const url = usePngUrl(png);
  return html`<figure class="print-dots">
    <span class="dots-art">${url && html`<img src=${url} alt="" />`}</span>
    <figcaption>How it prints on a 12 mm bin label</figcaption>
  </figure>`;
}

// start: { kind: 'picture', data, name } | { kind: 'edit', icon } | { kind: 'copy', icon }, or null when closed.
// onSaved gets the saved icon.
export function IconEditorSheet({ start, onClose, onSaved }) {
  const dirtyRef = useRef(false);
  const close = (icon) => {
    if (!icon && dirtyRef.current && !window.confirm('Close the editor without saving this icon?')) return;
    dirtyRef.current = false;
    onClose();
    if (icon) onSaved(icon);
  };
  const title = start && start.kind === 'edit' ? 'Edit icon' : 'New icon';
  return html`<${Sheet} open=${!!start} wide title=${title} onClose=${() => close(null)}>
    ${start && html`<${EditorBody} start=${start} dirtyRef=${dirtyRef} onDone=${close} />`}
  <//>`;
}
