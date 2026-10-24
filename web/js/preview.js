// The label on a strip of tape, with its size and print time, or the dots the printer will print
import { useState } from 'preact/hooks';
import { html } from './html.js';
import { useStore } from './state.js';
import { app, boot } from './app.js';

const ZOOMS = [['fit', 'Fit'], ['2', '2×'], ['4', '4×']];

export function Preview() {
  const { render, renderError } = useStore(app);
  const { phase, text, error } = useStore(boot);
  const [view, setView] = useState('tape');
  const [zoom, setZoom] = useState('fit');

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
    stage = html`<div class=${`tape-scroll zoom-${zoom}`}>
      <div class="tape-strip" style=${{ background: tape }}>
        <img class=${dots ? 'dots' : ''} src=${dots ? render.dotsUrl : render.previewUrl}
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
        <span class="chip-group" role="group" aria-label="Zoom">
          ${ZOOMS.map(([value, name]) => html`<button class=${zoom === value ? 'on' : ''} onClick=${() => setZoom(value)}>${name}</button>`)}
        </span>
      </span>
    </div>
    ${m && m.warning && html`<p class="warning">${m.warning}</p>`}
    ${renderError && html`<p class="warning">${renderError}</p>`}
  </section>`;
}
