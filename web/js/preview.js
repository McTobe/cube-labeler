// The label on a strip of tape, with its size and print time, or the dots the printer will print
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { html } from './html.js';
import { useStore } from './state.js';
import { app, boot, updateLabel } from './app.js';
import { useWide } from './ui.js';

const ZOOMS = [['fit', 'Fit'], ['2', '2×'], ['4', '4×']];
// Room Fit leaves around the strip, in pixels, and the share of a tall stage the label may fill
const FIT_SIDE = 80;
const FIT_HEIGHT_SHARE = 0.35;
const PHONE_FIT_HEIGHT = 120;
// Fit never draws the tape more than this many pixels per millimetre (about 3× real size on a
// desktop screen), so a short label sits on the stage like a label instead of filling it
const FIT_MAX_PX_PER_MM = 11;

// The width that shows the whole label as big as the stage allows (Fit)
function useFitWidth(stageRef, natural, wide, tapeMm) {
  const [box, setBox] = useState(null);
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return undefined;
    const observer = new ResizeObserver(() => setBox([stage.clientWidth, stage.clientHeight]));
    observer.observe(stage);
    return () => observer.disconnect();
  }, [stageRef.current]);
  if (!box || !natural) return null;
  const maxHeight = wide ? Math.min((box[1] - 40) * FIT_HEIGHT_SHARE, tapeMm * FIT_MAX_PX_PER_MM) : PHONE_FIT_HEIGHT;
  const scale = Math.min((box[0] - FIT_SIDE) / natural[0], maxHeight / natural[1]);
  return Math.max(40, Math.floor(natural[0] * scale));
}

// Shows the label being edited, or the strip passed in (the queue page passes its strip)
export function Preview({ strip, empty }) {
  const state = useStore(app);
  const render = strip === undefined ? state.render : strip;
  const renderError = strip === undefined ? state.renderError : null;
  const { label } = state;
  // Rulers are drawn on text labels
  const aids = strip === undefined && state.mode === 'text';
  const { phase, text, error } = useStore(boot);
  const [view, setView] = useState('tape');
  const [zoom, setZoom] = useState('fit');
  const stageRef = useRef(null);
  const [natural, setNatural] = useState(null);
  const wide = useWide();
  // Bin labels and queue strips are on 12 mm tape
  const tapeMm = strip === undefined && state.mode === 'text' ? Number(label.tape_width_mm) || 12 : 12;
  const fitWidth = useFitWidth(stageRef, natural, wide, tapeMm);
  // Zooming makes the stage taller, which must not change the size it zooms from
  const fitBase = useRef(null);
  if (zoom === 'fit' || !fitBase.current) fitBase.current = fitWidth;

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
    const dots = view === 'dots';
    const tape = dots ? '#ffffff' : render.tape_bg_color;
    // 2× and 4× zoom in from the Fit size, so they are always bigger
    const fit = fitBase.current ? fitBase.current * (zoom === 'fit' ? 1 : Number(zoom)) : null;
    stage = html`<div ref=${stageRef} class=${`tape-scroll zoom-${zoom}${fit ? ' fitted' : ''}`}>
      <div class="tape-strip" style=${{ background: tape }}>
        <img class=${dots ? 'dots' : ''} src=${dots ? render.dotsUrl : render.previewUrl}
          style=${fit ? { width: `${fit}px` } : null}
          onLoad=${(e) => setNatural([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])}
          alt=${dots ? 'The dots the printer will print' : 'Label preview'} />
      </div>
    </div>`;
  }

  const m = render && render.metrics;
  return html`<section class="card preview" aria-label="Preview">
    ${stage}
    <div class="preview-bar">
      <span class="metrics">${m ? `${m.label_count > 1 ? `${m.label_count} labels, ${m.print_length_mm} mm` : `${m.print_length_mm} mm label`} · ${m.total_used_length_mm} mm of tape · about ${Math.max(1, Math.round(m.print_duration_sec))} s` : ''}</span>
      <span class="preview-controls">
        <span class="chip-group" role="group" aria-label="Preview view">
          <button class=${view === 'tape' ? 'on' : ''} onClick=${() => setView('tape')}>Tape</button>
          <button class=${view === 'dots' ? 'on' : ''} onClick=${() => setView('dots')}>Print dots</button>
        </span>
        ${aids && html`<span class="chip-group" role="group" aria-label="Measuring aid">
          <button class=${label.show_rulers ? 'on' : ''} aria-pressed=${label.show_rulers}
            onClick=${() => updateLabel({ show_rulers: !label.show_rulers })}>Rulers</button>
        </span>`}
        <span class="chip-group" role="group" aria-label="Zoom">
          ${ZOOMS.map(([value, name]) => html`<button class=${zoom === value ? 'on' : ''} onClick=${() => setZoom(value)}>${name}</button>`)}
        </span>
      </span>
    </div>
    ${m && m.warning && html`<p class="warning">${m.warning}</p>`}
    ${renderError && html`<p class="warning">${renderError}</p>`}
  </section>`;
}
