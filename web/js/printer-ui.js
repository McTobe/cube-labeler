// The printer chip in the top bar and the printer panel it opens
import { useState } from 'preact/hooks';
import { html } from './html.js';
import { Icon } from './icons.js';
import { Sheet } from './ui.js';
import { useStore } from './state.js';
import { boot, printer, connectPrinter, checkStatus, feed, forgetPrinter, FEED_LENGTH_MM } from './app.js';

function chipText(p) {
  if (!p.supported) return 'No printing here';
  if (p.busy) return 'Working...';
  if (p.state === 'ready' && p.info) return `${p.info.tape_width_mm} mm tape`;
  if (p.state === 'error') return p.message || 'Printer problem';
  if (p.state === 'paired') return 'Printer paired';
  return 'No printer';
}

export function PrinterChip() {
  const p = useStore(printer);
  const [open, setOpen] = useState(false);
  return html`
    <button class=${`printer-chip state-${p.busy ? 'busy' : p.state}`} onClick=${() => setOpen(true)}
      aria-label=${`Printer: ${chipText(p)}`}>
      <span class="dot" aria-hidden="true"></span>
      <${Icon} name="printer" size=${18} />
      <span class="chip-label">${chipText(p)}</span>
    </button>
    <${Sheet} open=${open} title="Printer" onClose=${() => setOpen(false)}>
      <${PrinterPanel} />
    <//>`;
}

export function PrinterPanel() {
  const p = useStore(printer);
  const { phase } = useStore(boot);
  const ready = phase === 'ready';

  if (!p.supported) {
    return html`<div class="printer-panel">
      <p>This browser can't talk to the printer. Use Chrome or Edge on Android, Windows, macOS or Linux.</p>
      <p class="hint">You can still design labels here and save them as pictures.</p>
    </div>`;
  }

  const info = p.info;
  return html`<div class="printer-panel">
    ${info ? html`<dl class="facts">
      <dt>Printer</dt><dd>${info.model}</dd>
      <dt>Tape</dt><dd>${info.tape_width_mm} mm ${info.tape_type ? info.tape_type.toLowerCase() : ''}, ${info.tape_color} with ${info.text_color} text</dd>
      <dt>Power</dt><dd>${info.power}</dd>
      ${info.errors.length > 0 && html`<dt>Problem</dt><dd class="error">${info.errors.join(', ')}</dd>`}
    </dl>` : html`<p>${p.transport
      ? 'A printer was paired on this device earlier. Check its status to wake it up.'
      : 'Pair the PT-P300BT in your Bluetooth settings first, then connect it here.'}</p>`}
    ${p.message && p.state === 'error' && !info && html`<p class="error">${p.message}</p>`}

    <div class="button-row">
      ${p.transport && html`<button class="primary" disabled=${p.busy || !ready} onClick=${checkStatus}>
        <${Icon} name="refresh" size=${18} /> Check status</button>`}
      <button class=${p.transport ? 'secondary' : 'primary'} disabled=${p.busy || !ready} onClick=${connectPrinter}>
        ${p.transport ? 'Pick another printer' : 'Connect printer'}</button>
      ${p.transport && html`<button class="secondary" disabled=${p.busy || !ready} onClick=${feed}>
        <${Icon} name="feed" size=${18} /> Feed ${FEED_LENGTH_MM} mm</button>`}
      ${p.transport && html`<button class="link-button forget" disabled=${p.busy} onClick=${forgetPrinter}>Forget this printer</button>`}
    </div>

    <details class="help">
      <summary>Printer not in the list?</summary>
      <p>On Android, Chrome needs the <b>Nearby devices</b> permission (Settings › Apps › Chrome › Permissions).
        After allowing it, force stop Chrome and open it again; until then the list says "No compatible devices found".</p>
      <p>The printer has to be switched on and paired in the phone's or computer's Bluetooth settings.</p>
    </details>
  </div>`;
}
