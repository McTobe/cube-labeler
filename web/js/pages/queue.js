// The print queue: labels collected from the Label page, printed as one strip with cut lines
// between them. Each extra label saves the 25 mm of tape a separate print would feed first.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Icon } from '../icons.js';
import { Menu } from '../ui.js';
import { useStore } from '../state.js';
import { Preview } from '../preview.js';
import { binSummary } from './bin.js';
import { NewRollSheet } from '../printer-ui.js';
import { formatTape } from '../tape.js';
import {
  app, boot, printer, connectPrinter, itemTitle, moveQueueItem, removeQueueItem, clearQueue,
  editQueueItem, printQueue, keepPrintedQueue, showingQueue, savePicture, setQueueCopies,
  undoQueueRemoval, copiesOf, queueLabelCount, textLines, hasBarcode, BIN_FONT, MAX_TAPE_MM, checkStatus,
  hideQueueRun, stopQueueRun,
} from '../app.js';

function itemDetail(item) {
  // The font tells otherwise equal labels apart
  if (item.mode === 'bin') return `${binSummary(item.bin)} · ${item.font?.bin_font || BIN_FONT}`;
  const l = item.label;
  if (l.layout === 'ports') {
    return `${l.port_count} ports, ${Number(l.port_pitch_mm).toFixed(1)} mm apart · ${l.tape_width_mm} mm tape · ${l.font_name}`;
  }
  // The lines after the title tell labels with the same first line apart
  const more = textLines(l).slice(1).join(' · ');
  return `${l.layout === 'flag' ? `Cable flag, ${l.flag_cable_mm} mm cable · ` : ''}${more ? `${more} · ` : ''}${l.tape_width_mm} mm tape${l.fixed_width_mm ? `, ${l.fixed_width_mm} mm long` : ''}${l.qr_enabled && l.qr_data ? ', QR code' : ''}${hasBarcode(l) ? ', barcode' : ''} · ${l.font_name}`;
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
    const gap = rows.length > 1 ? rows[1].top - rows[0].bottom : 0;
    let state = { from, over: from, dy: 0, step: rows[from].height + gap };
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

// How many labels, how much tape and how long, and what printing them together saves
function summary(count, render) {
  const m = render && render.count === count ? render.metrics : null;
  const parts = [count === 1 ? '1 label' : `${count} labels`];
  if (m) parts.push(`${Math.round(m.total_used_length_mm)} mm of tape`, `about ${Math.max(1, Math.round(m.print_duration_sec))} s`);
  const saving = count > 1 ? `Printing them together saves ${25 * (count - 1)} mm of tape.` : 'Add another label to start saving tape.';
  return html`${parts.join(' · ')}<br />${saving}`;
}

const labelRange = (part) => (part.from === part.to ? `label ${part.from + 1}` : `labels ${part.from + 1} to ${part.to + 1}`);
const partSize = (part) => formatTape(part.mm);

// The queue needs more than one print: longer than the printer's limit, or than the roll's
// tape left. Says how it splits, and prints it in parts or (when it fits one print) anyway.
function PlanCard({ plan, busy, onNewRoll }) {
  const { parts, long, needed, left } = plan;
  const short = left !== null && needed > left;
  const anyway = !long && html`<button class="secondary" disabled=${busy} onClick=${() => printQueue({ whole: true })}>Print it all anyway</button>`;
  if (parts[0].newRoll) {
    return html`<section class="card tape-plan short">
      <h2 class="card-title">Not enough tape for the first label</h2>
      <p>This strip needs about <b>${formatTape(needed)}</b>, and the roll has about <b>${formatTape(left)}</b> left.
        That is not enough for the first label, so load a new roll first.</p>
      <div class="button-row">
        <button class="primary" disabled=${busy} onClick=${onNewRoll}>New roll loaded, print</button>
        ${anyway}
      </div>
    </section>`;
  }
  const when = (part, i) => {
    if (i === 0) return 'Prints now.';
    if (part.newRoll) return 'Prints after you load a new roll.';
    return `Prints after part ${i}.`;
  };
  return html`<section class=${`card tape-plan${short ? ' short' : ''}`}>
    <h2 class="card-title">${short ? 'Not enough tape for the whole queue' : 'Too long for one print'}</h2>
    <p>${short
      ? html`This strip needs about <b>${formatTape(needed)}</b>, and the roll has about <b>${formatTape(left)}</b> left.`
      : html`This strip needs about <b>${formatTape(needed)}</b>, and the printer prints up to ${formatTape(MAX_TAPE_MM)} at a time.`}</p>
    <ol class="tape-parts">
      ${parts.map((part, i) => html`<li><b>Part ${i + 1}:</b> ${labelRange(part)}, ${partSize(part)}. ${when(part, i)}</li>`)}
    </ol>
    <p class="hint">Labels are never cut in half. The parts are split at a cut line.</p>
    <div class="button-row">
      <button class="primary" disabled=${busy} onClick=${() => printQueue()}>Print in ${parts.length} parts</button>
      ${anyway}
    </div>
  </section>`;
}

// Between two parts: what to do before the next one prints
function RunCard({ run, width, busy, onNewRoll }) {
  const part = run.parts[run.next];
  const n = run.next + 1;
  if (part.newRoll) {
    return html`<section class="card tape-plan">
      <h2 class="card-title">Part ${run.next} printed. Load a new roll</h2>
      <p>Put a new ${width} mm roll in the printer, then print part ${n}: ${labelRange(part)}, ${partSize(part)}.</p>
      <div class="button-row">
        <button class="primary" disabled=${busy} onClick=${onNewRoll}>New roll loaded, print part ${n}</button>
        <button class="secondary" onClick=${hideQueueRun}>Later</button>
      </div>
    </section>`;
  }
  return html`<section class="card tape-plan">
    <h2 class="card-title">Part ${run.next} of ${run.parts.length} printed</h2>
    <p>Cut off the strip, then print part ${n}: ${labelRange(part)}, ${partSize(part)}.</p>
    <div class="button-row">
      <button class="primary" disabled=${busy} onClick=${() => printQueue()}>Print part ${n}</button>
      <button class="secondary" onClick=${hideQueueRun}>Later</button>
    </div>
  </section>`;
}

export function QueuePage() {
  const { queue, queueRender, thumbs, queuePrinted, queueUndo, queuePlan, queueRun } = useStore(app);
  const [rollSheet, setRollSheet] = useState(false);
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
  const nextPart = queueRun ? queueRun.parts[queueRun.next] : queuePlan ? queuePlan.parts[0] : null;
  let printText = count ? `Print queue (${count})` : 'Print queue';
  if (queueRun) printText = `Print part ${queueRun.next + 1} of ${queueRun.parts.length}`;
  else if (queuePlan && queuePlan.parts.length > 1 && !nextPart.newRoll) printText = `Print in ${queuePlan.parts.length} parts (${count})`;
  // A part that goes on a new roll: read the new roll's tape, say its length, then print
  const newRollThenPrint = async () => {
    await checkStatus();
    if (printer.get().info && printer.get().state === 'ready') setRollSheet(true);
  };
  const print = () => (nextPart && nextPart.newRoll ? newRollThenPrint() : printQueue());
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
            : html`<button class="primary big" disabled=${!ready || !count || p.busy || !p.supported} onClick=${print}>
                <${Icon} name="printer" size=${20} /> ${p.busy ? 'Printing...' : printText}</button>`}
          <span class="menu-anchor">
            <button class="secondary big icon-only" aria-label="More actions" onClick=${() => setMenuOpen(true)}>
              <${Icon} name="more" /></button>
            <${Menu} open=${menuOpen} onClose=${() => setMenuOpen(false)} items=${[
              { label: 'Save strip as picture', icon: 'download', action: () => savePicture(true), disabled: !queueRender },
              { label: 'Clear queue', icon: 'close', action: clearQueue, disabled: !count || p.busy },
              queueRun && { label: 'Stop printing in parts', icon: 'undo', action: stopQueueRun, disabled: p.busy },
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
      ${queueRun && !queueRun.hidden && html`<${RunCard} run=${queueRun} width=${queueRender ? queueRender.tape_width_mm : ''}
        busy=${p.busy || needsPrinter} onNewRoll=${newRollThenPrint} />`}
      ${!queueRun && queuePlan && html`<${PlanCard} plan=${queuePlan} busy=${p.busy || needsPrinter || !ready} onNewRoll=${newRollThenPrint} />`}
      <${NewRollSheet} open=${rollSheet} info=${p.info} action="Start counting and print"
        onClose=${() => setRollSheet(false)} onDone=${() => { setRollSheet(false); printQueue(); }} />
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
        <section class="card queue-card">
          <div class="card-head">
            <h2 class="card-title">Queue</h2>
            <button class="secondary" disabled=${p.busy} onClick=${clearQueue}>Clear</button>
          </div>
          <p class="hint queue-summary">${summary(count, queueRender)}</p>
          <ol class=${`queue-list${drag ? ' dragging' : ''}`} ref=${listRef}>
            ${queue.map((item, i) => {
              const title = itemTitle(item);
              const copies = copiesOf(item);
              const classes = ['queue-item'];
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
                </span>
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
              </li>`;
            })}
          </ol>
        </section>`}
    </div>
  </div>`;
}
