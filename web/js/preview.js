// The label on a strip of tape, with its size and print time, or the dots the printer will print
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { html } from './html.js';
import { useStore } from './state.js';
import { app, boot, updateLabel, hush } from './app.js';
import { Icon } from './icons.js';
import { useWide } from './ui.js';

const ZOOMS = [['fit', 'Fit'], ['real', 'Real size']];
// Preview pixels are print dots (0.1411 mm); a CSS millimetre is 96 / 25.4 pixels, about real
// size on most screens
const REAL_PX_PER_DOT = 0.1411 * (96 / 25.4);
// Room Fit leaves around the strip, in pixels, and the share of a tall stage the label may fill
const FIT_SIDE = 80;
const FIT_HEIGHT_SHARE = 0.35;
const PHONE_FIT_HEIGHT = 120;
// Fit never draws the tape more than this many pixels per millimetre (about 3× real size on a
// desktop screen), so a short label sits on the stage like a label instead of filling it
const FIT_MAX_PX_PER_MM = 11;

// A strip longer than this wraps onto rows in Fit, at most MAX_ROWS of them
const WRAP_MM = 150;
const MAX_ROWS = 4;
const ROW_GAP = 18;

function useStageBox(stageRef) {
  const [box, setBox] = useState(null);
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return undefined;
    const observer = new ResizeObserver(() => setBox([stage.clientWidth, stage.clientHeight]));
    observer.observe(stage);
    return () => observer.disconnect();
  }, [stageRef.current]);
  return box;
}

// The width of the whole strip image that shows it as big as the stage allows (Fit). With
// rows, the widest row must fit across and all rows on top of each other must fit down.
function fitWidth(box, natural, wide, tapeMm, rows) {
  if (!box || !natural) return null;
  const n = rows.length;
  const widest = Math.max(...rows.map((r) => r.to - r.from));
  const share = n > 1 ? 0.8 : FIT_HEIGHT_SHARE;
  const maxHeight = wide
    ? Math.min((box[1] - 40 - ROW_GAP * (n - 1)) * share, n * tapeMm * FIT_MAX_PX_PER_MM)
    : n * PHONE_FIT_HEIGHT;
  const scale = Math.min((box[0] - FIT_SIDE) / (natural[0] * widest), maxHeight / (n * natural[1]));
  return Math.max(40, Math.floor(natural[0] * scale));
}

// Splits a long strip at the cut lines into rows of about the same length
function splitRows(spans, lengthMm) {
  const n = Math.min(MAX_ROWS, spans.length, Math.ceil(lengthMm / WRAP_MM));
  if (n < 2) return [{ from: 0, to: 1 }];
  const cuts = spans.slice(1).map((s, i) => (spans[i].to + s.from) / 2);
  const rows = [];
  let from = 0;
  for (let k = 1; k < n; k++) {
    const left = cuts.filter((c) => c > from);
    if (!left.length) break;
    const cut = left.reduce((best, c) => (Math.abs(c - k / n) < Math.abs(best - k / n) ? c : best));
    rows.push({ from, to: cut });
    from = cut;
  }
  rows.push({ from, to: 1 });
  return rows;
}

// Shows the label being edited, or the strip passed in (the queue page passes its strip)
// spans (the queue's) are where each label sits on the strip: pointing at one calls onPoint
// with its list item, clicking calls onPick, and the label of item active is outlined
export function Preview({ strip, empty, spans, active, onPoint, onPick, tapeMm: stripTapeMm }) {
  const state = useStore(app);
  const render = strip === undefined ? state.render : strip;
  const renderError = strip === undefined ? state.renderError : null;
  const { label } = state;
  // Rulers are drawn on text labels
  const aids = strip === undefined;
  const { phase, text, error } = useStore(boot);
  const [zoomChoice, setZoom] = useState('fit');
  const stageRef = useRef(null);
  const [natural, setNatural] = useState(null);
  const wide = useWide();
  // Phones always use Fit: browsers there don't size CSS millimetres to the screen, so Real
  // size comes out far too small
  const zoom = wide ? zoomChoice : 'fit';
  // Bin labels and queue strips are on 12 mm tape; a label from the history says its own
  const editing = state.mode === 'ports' ? state.ports : label;
  const tapeMm = stripTapeMm || (strip === undefined && state.mode !== 'bin' ? Number(editing.tape_width_mm) || 12 : 12);
  const box = useStageBox(stageRef);
  const oneRow = [{ from: 0, to: 1 }];
  const lengthMm = render && render.metrics ? render.metrics.print_length_mm : 0;
  const rows = spans && zoom === 'fit' ? splitRows(spans, lengthMm) : oneRow;
  // Zooming makes the stage taller, which must not change the size it zooms from
  const fitBase = useRef(null);
  if (zoom === 'fit' || !fitBase.current) fitBase.current = fitWidth(box, natural, wide, tapeMm, oneRow);

  // Zooming keeps the middle of the label in the middle of the stage
  useLayoutEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    el.scrollLeft = (el.scrollWidth - el.clientWidth) / 2;
    el.scrollTop = (el.scrollHeight - el.clientHeight) / 2;
  }, [zoom]);

  let stage;
  if (phase === 'failed') {
    stage = html`<div class="stage-message error">Could not start: ${error}. Reload the page to try again.</div>`;
  } else if (!render && empty && phase === 'ready') {
    stage = html`<div class="stage-message">${empty}</div>`;
  } else if (!render) {
    stage = html`<div class="stage-message"><div class="spinner" aria-hidden="true"></div>
      <span>${phase === 'loading' ? text : 'Drawing...'}</span>
      ${phase === 'loading' && html`<span class="hint">The first start downloads about 15 MB. After that it starts from this device.</span>`}
    </div>`;
  } else {
    // Only the label being edited can show its dots (Advanced > Show print dots)
    const dots = strip === undefined && state.mode !== 'bin' && state.previewDots;
    const tape = dots ? '#ffffff' : render.tape_bg_color;
    // Real size draws each dot at its size on paper; a long strip scrolls inside the stage
    const fit = rows.length > 1 ? fitWidth(box, natural, wide, tapeMm, rows)
      : zoom === 'real' ? (natural ? Math.round(natural[0] * REAL_PX_PER_DOT) : null) : fitBase.current;
    const src = dots ? render.dotsUrl : render.previewUrl;
    const alt = dots ? 'The dots the printer will print' : 'Label preview';
    const loaded = (e) => setNatural([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight]);
    let content;
    if (spans && fit) {
      // Each row is a window onto the one strip image, with a target over every label in it
      content = html`<div class="tape-rows" onMouseLeave=${() => onPoint && onPoint(null)}>
        ${rows.map((row, r) => html`<div class="tape-strip" key=${r} style=${{ background: tape }}>
          <div class="strip-window" style=${{ width: `${Math.round((row.to - row.from) * fit)}px` }}>
            <img class=${dots ? 'dots' : ''} src=${src} alt=${r === 0 ? alt : ''} onLoad=${r === 0 ? loaded : null}
              style=${{ width: `${fit}px`, marginLeft: `${-row.from * fit}px` }} />
            ${spans.map((span, n) => (span.from >= row.from && span.to <= row.to) && html`<button key=${n}
              class=${`strip-label${span.item === active ? ' on' : ''}`} aria-label=${`Label ${n + 1}: show it in the list`}
              style=${{ left: `${(span.from - row.from) * fit}px`, width: `${(span.to - span.from) * fit}px` }}
              onMouseEnter=${() => onPoint && onPoint(span.item)} onFocus=${() => onPoint && onPoint(span.item)}
              onClick=${() => onPick && onPick(span.item)}></button>`)}
          </div>
        </div>`)}
      </div>`;
    } else {
      content = html`<div class="tape-strip" style=${{ background: tape }}>
        <img class=${dots ? 'dots' : ''} src=${src} style=${fit ? { width: `${fit}px` } : null} onLoad=${loaded} alt=${alt} />
      </div>`;
    }
    stage = html`<div ref=${stageRef} class=${`tape-scroll zoom-${zoom}${fit ? ' fitted' : ''}`}>${content}</div>`;
  }

  const m = render && render.metrics;
  // A port strip says what it lines up with, in place of the print time
  const ports = strip === undefined && render && render.item.mode === 'text' && render.item.label.layout === 'ports' ? render.item.label : null;
  const { status } = state;
  return html`<section class="card preview" aria-label="Preview">
    <div class="stage-wrap">
      ${stage}
      <div class="toast-slot" role="status" aria-live="polite">
        ${status.text && html`<div class=${`toast${status.error ? ' error' : ''}`} key=${status.id}>
          <span>${status.text}</span>
          <button class="icon-button" aria-label="Close message" onClick=${hush}><${Icon} name="close" size=${16} /></button>
        </div>`}
      </div>
    </div>
    <div class="preview-bar">
      <span class="metrics">${m ? `${m.label_count > 1 ? `${m.label_count} labels, ${m.print_length_mm} mm` : `${m.print_length_mm} mm label`}${rows.length > 1 ? ` in one strip, shown in ${rows.length} rows` : ''} · ${m.total_used_length_mm} mm of tape · ${ports ? `lines up with ${ports.port_count} ports` : `about ${Math.max(1, Math.round(m.print_duration_sec))} s`}` : ''}</span>
      <span class="preview-controls">
        ${aids && html`<span class="chip-group" role="group" aria-label="Measuring aid">
          <button class=${label.show_rulers ? 'on' : ''} aria-pressed=${label.show_rulers}
            onClick=${() => updateLabel({ show_rulers: !label.show_rulers })}>Rulers</button>
        </span>`}
        ${wide && html`<span class="chip-group" role="group" aria-label="Zoom">
          ${ZOOMS.map(([value, name]) => html`<button class=${zoom === value ? 'on' : ''} onClick=${() => setZoom(value)}>${name}</button>`)}
        </span>`}
      </span>
    </div>
    ${m && m.warning && html`<p class="warning">${m.warning}</p>`}
    ${renderError && html`<p class="warning">${renderError}</p>`}
  </section>`;
}
