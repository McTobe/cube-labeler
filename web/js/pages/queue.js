// The print queue: labels collected from the Label page, printed as one strip with cut lines
// between them. Each extra label saves the 25 mm of tape a separate print would feed first.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Icon } from '../icons.js';
import { Menu } from '../ui.js';
import { useStore } from '../state.js';
import { Preview } from '../preview.js';
import { binSummary } from './bin.js';
import {
  app, boot, printer, connectPrinter, itemTitle, moveQueueItem, removeQueueItem, clearQueue,
  editQueueItem, printQueue, keepPrintedQueue, showingQueue, savePicture, setQueueCopies,
  undoQueueRemoval, copiesOf, queueLabelCount, textLines,
} from '../app.js';

function itemDetail(item) {
  if (item.mode === 'bin') return binSummary(item.bin);
  const l = item.label;
  // The lines after the title tell labels with the same first line apart
  const more = textLines(l).slice(1).join(' · ');
  return `${more ? `${more} · ` : ''}${l.tape_width_mm} mm tape${l.fixed_width_mm ? `, ${l.fixed_width_mm} mm long` : ''}${l.qr_enabled && l.qr_data ? ', QR code' : ''}`;
}

// Dragging a row by its handle: where it started, where it would land and how far it moved
function useRowDrag(listRef, count) {
  const [drag, setDrag] = useState(null);
  const start = (e, from) => {
    if (e.button > 0) return;
    e.preventDefault();
    const rows = [...listRef.current.children].map((row) => row.getBoundingClientRect());
    const handle = e.currentTarget;
    handle.setPointerCapture(e.pointerId);
    const startY = e.clientY;
    let state = { from, over: from, dy: 0, step: rows[from].height + 8 };
    setDrag(state);
    const move = (ev) => {
      const dy = ev.clientY - startY;
      const middle = rows[from].top + rows[from].height / 2 + dy;
      let over = rows.filter((r, i) => i !== from && r.top + r.height / 2 < middle).length;
      over = Math.max(0, Math.min(count - 1, over));
      state = { ...state, over, dy };
      setDrag(state);
    };
    const end = () => {
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', end);
      handle.removeEventListener('pointercancel', end);
      setDrag(null);
      moveQueueItem(state.from, state.over);
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
  };
  // How far each row moves out of the way of the dragged one
  const offset = (i) => {
    if (!drag) return 0;
    if (i === drag.from) return drag.dy;
    if (drag.from < i && i <= drag.over) return -drag.step;
    if (drag.over <= i && i < drag.from) return drag.step;
    return 0;
  };
  return { drag, start, offset };
}

export function QueuePage() {
  const { queue, queueRender, thumbs, queuePrinted, queueUndo } = useStore(app);
  const p = useStore(printer);
  const { phase } = useStore(boot);
  const [menuOpen, setMenuOpen] = useState(false);
  // The label pointed at on the strip or in the list, and the one just picked on the strip
  const [active, setActive] = useState(null);
  const [picked, setPicked] = useState(null);
  const listRef = useRef(null);
  const ready = phase === 'ready';
  const { drag, start, offset } = useRowDrag(listRef, queue.length);

  useEffect(() => {
    showingQueue(true);
    return () => showingQueue(false);
  }, []);
  useEffect(() => { if (ready) showingQueue(true); }, [ready]);
  useEffect(() => {
    if (picked === null) return undefined;
    const row = listRef.current && listRef.current.children[picked];
    if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    const timer = setTimeout(() => setPicked(null), 1500);
    return () => clearTimeout(timer);
  }, [picked]);

  const count = queueLabelCount(queue);
  const needsPrinter = p.supported && !p.transport;
  // The strip and its spans can lag a moment behind the list while it redraws
  const spans = queueRender && queueRender.count === count ? queueRender.spans : null;
  return html`<div class="label-page queue-page">
    <div class="label-preview-col">
      <${Preview} strip=${count ? queueRender : null} spans=${spans} active=${drag ? null : active}
        onPoint=${setActive} onPick=${setPicked}
        empty="Your print queue is empty. Design a label, then choose Add to queue." />
      <div class="action-bar">
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
              { label: 'Clear queue', icon: 'close', action: clearQueue, disabled: !count || p.busy },
            ]} />
          </span>
        </div>
      </div>
    </div>

    <div class="label-edit-col">
      ${queueUndo && html`<div class="card undo-bar" role="status">
        <span>${queueUndo.text}</span>
        <button class="secondary" onClick=${undoQueueRemoval}><${Icon} name="undo" size=${18} /> Undo</button>
      </div>`}
      ${queuePrinted > 0 && html`<section class="card printed">
        <p>Printed ${queuePrinted} labels. Clear the queue?</p>
        <div class="button-row">
          <button class="primary" onClick=${clearQueue}>Clear queue</button>
          <button class="secondary" onClick=${keepPrintedQueue}>Keep it</button>
        </div>
      </section>`}
      ${queue.length === 0 ? html`<section class="card soon">
        <${Icon} name="queue" size=${40} />
        <h2>No labels yet</h2>
        <p>Labels in the queue print as one strip, saving about 25 mm of tape per extra label.</p>
        <p><a class="link-button" href="#/label">Design a label</a></p>
      </section>` : html`
        <p class="queue-summary hint">${count === 1 ? 'Add another label to start saving tape.' : `${count} labels in one strip save ${25 * (count - 1)} mm of tape.`}</p>
        <ol class=${`queue-list${drag ? ' dragging' : ''}`} ref=${listRef}>
          ${queue.map((item, i) => {
            const title = itemTitle(item);
            const copies = copiesOf(item);
            const classes = ['card', 'queue-item'];
            if (active === i && !drag) classes.push('active');
            if (picked === i) classes.push('picked');
            if (drag && drag.from === i) classes.push('lifted');
            return html`<li class=${classes.join(' ')} key=${item.id}
              style=${offset(i) ? { transform: `translateY(${offset(i)}px)` } : null}
              onMouseEnter=${() => setActive(i)} onMouseLeave=${() => setActive(null)}>
              <span class="drag-handle" title="Drag to move" onPointerDown=${(e) => start(e, i)}><${Icon} name="grip" size=${18} /></span>
              <span class="queue-thumb">${thumbs[item.id] ? html`<img src=${thumbs[item.id]} alt="" />` : ''}</span>
              <span class="queue-body">
                <span class="queue-title" title=${title}>${title}</span>
                <span class="hint queue-detail">${itemDetail(item)}</span>
                <span class="queue-controls">
                  <span class="copies" role="group" aria-label=${`Copies of ${title}`}>
                    <button class="icon-button" aria-label="One copy less" onClick=${() => setQueueCopies(i, copies - 1)}><${Icon} name="minus" size=${16} /></button>
                    <span class="copies-count" aria-live="polite">×${copies}</span>
                    <button class="icon-button" aria-label="One copy more" disabled=${copies >= 99} onClick=${() => setQueueCopies(i, copies + 1)}><${Icon} name="plus" size=${16} /></button>
                  </span>
                  <span class="queue-actions">
                    <button class="icon-button" aria-label="Move up" disabled=${i === 0} onClick=${() => moveQueueItem(i, i - 1)}><${Icon} name="up" size=${18} /></button>
                    <button class="icon-button" aria-label="Move down" disabled=${i === queue.length - 1} onClick=${() => moveQueueItem(i, i + 1)}><${Icon} name="down" size=${18} /></button>
                    <button class="icon-button" aria-label="Edit" onClick=${() => editQueueItem(i)}><${Icon} name="edit" size=${18} /></button>
                    <button class="icon-button danger" aria-label="Remove" onClick=${() => removeQueueItem(i)}><${Icon} name="close" size=${18} /></button>
                  </span>
                </span>
              </span>
            </li>`;
          })}
        </ol>`}
    </div>
  </div>`;
}
