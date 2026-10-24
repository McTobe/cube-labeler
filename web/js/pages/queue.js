// The print queue: labels collected from the Label page, printed as one strip with cut lines
// between them. Each extra label saves the 25 mm of tape a separate print would feed first.
import { useEffect, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Icon } from '../icons.js';
import { Menu } from '../ui.js';
import { useStore } from '../state.js';
import { Preview } from '../preview.js';
import {
  app, boot, printer, connectPrinter, itemTitle, moveQueueItem, removeQueueItem, clearQueue,
  editQueueItem, printQueue, keepPrintedQueue, showingQueue, savePicture,
} from '../app.js';

function itemDetail(item) {
  if (item.mode === 'bin') return `Bin label, ${item.bin.label_width_mm} mm`;
  const l = item.label;
  return `${l.tape_width_mm} mm tape${l.fixed_width_mm ? `, ${l.fixed_width_mm} mm long` : ''}${l.qr_enabled && l.qr_data ? ', QR code' : ''}`;
}

export function QueuePage() {
  const { queue, queueRender, thumbs, queuePrinted, status } = useStore(app);
  const p = useStore(printer);
  const { phase } = useStore(boot);
  const [menuOpen, setMenuOpen] = useState(false);
  const ready = phase === 'ready';

  useEffect(() => {
    showingQueue(true);
    return () => showingQueue(false);
  }, []);
  useEffect(() => { if (ready) showingQueue(true); }, [ready]);

  const count = queue.length;
  const needsPrinter = p.supported && !p.transport;
  return html`<div class="label-page queue-page">
    <div class="label-preview-col">
      <${Preview} strip=${count ? queueRender : null}
        empty="Your print queue is empty. Design a label, then choose Add to queue." />
      <div class="action-bar">
        <p class=${`status-line${status.error ? ' error' : ''}`} role="status">${status.text}</p>
        <div class="action-buttons">
          ${needsPrinter
            ? html`<button class="primary big" disabled=${!ready || p.busy} onClick=${connectPrinter}>
                <${Icon} name="printer" size=${20} /> <span>Connect<span class="hide-narrow"> printer</span></span></button>`
            : html`<button class="primary big" disabled=${!ready || !count || p.busy || !p.supported} onClick=${printQueue}>
                <${Icon} name="printer" size=${20} /> ${p.busy ? 'Printing...' : count ? `Print queue (${count})` : 'Print queue'}</button>`}
          <span class="menu-anchor">
            <button class="secondary big icon-only" aria-label="More actions" onClick=${() => setMenuOpen(true)}>
              <${Icon} name="more" /></button>
            <${Menu} open=${menuOpen} onClose=${() => setMenuOpen(false)} items=${[
              { label: 'Save strip as picture', icon: 'download', action: () => savePicture(true), disabled: !queueRender },
              { label: 'Clear queue', icon: 'close', action: () => { if (confirm(`Remove all ${count} labels from the queue?`)) clearQueue(); }, disabled: !count || p.busy },
            ]} />
          </span>
        </div>
      </div>
    </div>

    <div class="label-edit-col">
      ${queuePrinted > 0 && html`<section class="card printed">
        <p>Printed ${queuePrinted} labels. Clear the queue?</p>
        <div class="button-row">
          <button class="primary" onClick=${clearQueue}>Clear queue</button>
          <button class="secondary" onClick=${keepPrintedQueue}>Keep it</button>
        </div>
      </section>`}
      ${count === 0 ? html`<section class="card soon">
        <${Icon} name="queue" size=${40} />
        <h2>No labels yet</h2>
        <p>Labels in the queue print as one strip, saving about 25 mm of tape per extra label.</p>
        <p><a class="link-button" href="#/label">Design a label</a></p>
      </section>` : html`
        <p class="queue-summary hint">${count === 1 ? 'Add another label to start saving tape.' : `${count} labels in one strip save ${25 * (count - 1)} mm of tape.`}</p>
        <ol class="queue-list">
          ${queue.map((item, i) => html`<li class="card queue-item" key=${item.id}>
            <span class="queue-thumb">${thumbs[item.id] ? html`<img src=${thumbs[item.id]} alt="" />` : ''}</span>
            <span class="queue-text">
              <span class="queue-title">${i + 1}. ${itemTitle(item)}</span>
              <span class="hint">${itemDetail(item)}</span>
            </span>
            <span class="queue-actions">
              <button class="icon-button" aria-label="Move up" disabled=${i === 0} onClick=${() => moveQueueItem(i, -1)}><${Icon} name="up" size=${18} /></button>
              <button class="icon-button" aria-label="Move down" disabled=${i === count - 1} onClick=${() => moveQueueItem(i, 1)}><${Icon} name="down" size=${18} /></button>
              <button class="icon-button" aria-label="Edit" onClick=${() => editQueueItem(i)}><${Icon} name="edit" size=${18} /></button>
              <button class="icon-button danger" aria-label="Remove" onClick=${() => removeQueueItem(i)}><${Icon} name="close" size=${18} /></button>
            </span>
          </li>`)}
        </ol>`}
    </div>
  </div>`;
}
