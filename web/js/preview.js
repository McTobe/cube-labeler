// The label on a strip of tape, with its size and print time, or the dots the printer will print
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from './html.js';
import { useStore } from './state.js';
import { app, boot, updateLabel } from './app.js';
import { useWide } from './ui.js';

const ZOOMS = [['fit', 'Fit'], ['2', '2×'], ['4', '4×']];
// Room Fit leaves around the strip, in pixels, and the share of a tall stage the label may fill
const FIT_SIDE = 80;
const FIT_HEIGHT_SHARE = 0.6;
const PHONE_FIT_HEIGHT = 120;

// The width that shows the whole label as big as the stage allows (Fit)
function useFitWidth(stageRef, natural, wide) {
  const [box, setBox] = useState(null);
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return undefined;
    const observer = new ResizeObserver(() => setBox([stage.clientWidth, stage.clientHeight]));
    observer.observe(stage);
    return () => observer.disconnect();
  }, [stageRef.current]);
  if (!box || !natural) return null;
  const maxHeight = wide ? (box[1] - 40) * FIT_HEIGHT_SHARE : PHONE_FIT_HEIGHT;
  const scale = Math.min((box[0] - FIT_SIDE) / natural[0], maxHeight / natural[1]);
  return Math.max(40, Math.floor(natural[0] * scale));
}

export function Preview() {
  const { render, renderError, label } = useStore(app);
  const { phase, text, error } = useStore(boot);
  const [view, setView] = useState('tape');
  const [zoom, setZoom] = useState('fit');
  const stageRef = useRef(null);
  const [natural, setNatural] = useState(null);
  const wide = useWide();
  const fitWidth = useFitWidth(stageRef, natural, wide);

  let stage;
  if (phase === 'failed') {
    stage = html`<div class="stage-message error">Could not start: ${error}. Reload the page to try again.</div>`;
  } else if (!render) {
    stage = html`<div class="stage-message"><div class="spinner" aria-hidden="true"></div>
      <span>${phase === 'loading' ? text : 'Drawing...'}</span>
      ${phase === 'loading' && html`<span class="hint">The first start downloads about 15 MB. After that it starts from this device.</span>`}
    </div>`;
  } else {
    const dots = view === 'dots';
    const tape = dots ? '#ffffff' : render.label.tape_bg_color;
    const fit = zoom === 'fit' && fitWidth;
    stage = html`<div ref=${stageRef} class=${`tape-scroll zoom-${zoom}${fit ? ' fitted' : ''}`}>
      <div class="tape-strip" style=${{ background: tape }}>
        <img class=${dots ? 'dots' : ''} src=${dots ? render.dotsUrl : render.previewUrl}
          style=${fit ? { width: `${fitWidth}px` } : null}
          onLoad=${(e) => setNatural([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])}
          alt=${dots ? 'The dots the printer will print' : 'Label preview'} />
      </div>
    </div>`;
  }

  const m = render && render.metrics;
  return html`<section class="card preview" aria-label="Preview">
    ${stage}
    <div class="preview-bar">
      <span class="metrics">${m ? `${m.print_length_mm} mm label · ${m.total_used_length_mm} mm of tape · about ${Math.max(1, Math.round(m.print_duration_sec))} s` : ''}</span>
      <span class="preview-controls">
        <span class="chip-group" role="group" aria-label="Preview view">
          <button class=${view === 'tape' ? 'on' : ''} onClick=${() => setView('tape')}>Tape</button>
          <button class=${view === 'dots' ? 'on' : ''} onClick=${() => setView('dots')}>Print dots</button>
        </span>
        <span class="chip-group" role="group" aria-label="Measuring aids">
          <button class=${label.show_rulers ? 'on' : ''} aria-pressed=${label.show_rulers}
            onClick=${() => updateLabel({ show_rulers: !label.show_rulers })}>Rulers</button>
          <button class=${label.show_guides ? 'on' : ''} aria-pressed=${label.show_guides}
            title="Shows the part of the tape the printer can print on"
            onClick=${() => updateLabel({ show_guides: !label.show_guides })}>Printable area</button>
        </span>
        <span class="chip-group" role="group" aria-label="Zoom">
          ${ZOOMS.map(([value, name]) => html`<button class=${zoom === value ? 'on' : ''} onClick=${() => setZoom(value)}>${name}</button>`)}
        </span>
      </span>
    </div>
    ${m && m.warning && html`<p class="warning">${m.warning}</p>`}
    ${renderError && html`<p class="warning">${renderError}</p>`}
  </section>`;
}
