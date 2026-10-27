// The printer chip in the top bar and the printer panel it opens
import { useState } from 'preact/hooks';
import { html } from './html.js';
import { Icon } from './icons.js';
import { Sheet, Segmented } from './ui.js';
import { useStore } from './state.js';
import { drive } from './gdrive.js';
import {
  app, boot, printer, connectPrinter, checkStatus, feed, forgetPrinter, FEED_LENGTH_MM,
  loadedRoll, startRoll, correctCount,
} from './app.js';
import { ROLL_LENGTHS_MM, LOW_TAPE_MM, rollLeft, rollUsed, rollPrints, formatTape, tapeName } from './tape.js';

function chipText(p, roll) {
  if (!p.supported) return 'No printing here';
  if (p.busy) return 'Working...';
  if (p.state === 'ready' && p.info) {
    // A phone drops the width to make room
    return html`<span class="chip-tape">${p.info.tape_width_mm} mm · </span>${roll ? `${formatTape(rollLeft(roll))} left` : 'Set tape roll'}`;
  }
  if (p.state === 'error') return p.message || 'Printer problem';
  if (p.state === 'paired') return 'Printer paired';
  return 'No printer';
}

export function PrinterChip() {
  const p = useStore(printer);
  useStore(app);
  const [open, setOpen] = useState(false);
  const roll = loadedRoll(p.info);
  // Amber when the roll is nearly used up
  const low = roll && p.state === 'ready' && !p.busy && rollLeft(roll) < LOW_TAPE_MM;
  return html`
    <button class=${`printer-chip state-${p.busy ? 'busy' : p.state}${low ? ' low-tape' : ''}`} onClick=${() => setOpen(true)}
      aria-label=${`Printer: ${p.state === 'ready' && p.info && !p.busy ? `${p.info.tape_width_mm} mm tape, ${roll ? `${formatTape(rollLeft(roll))} left` : 'no tape roll set'}` : chipText(p, roll)}`}>
      <span class="dot" aria-hidden="true"></span>
      <${Icon} name="printer" size=${18} />
      <span class="chip-label">${chipText(p, roll)}</span>
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
    ${info && info.tape_loaded !== false && html`<${TapeRoll} info=${info} />`}

    <div class="button-row">
      ${p.transport && html`<button class="primary" disabled=${p.busy || !ready} onClick=${checkStatus}>
        <${Icon} name="refresh" size=${18} /> Check status</button>`}
      <button class=${p.transport ? 'secondary' : 'primary'} disabled=${p.busy || !ready} onClick=${connectPrinter}>
        ${p.transport ? 'Pick another printer' : 'Connect printer'}</button>
      ${p.transport && html`<button class="secondary" disabled=${p.busy || !ready} onClick=${feed}>
        <${Icon} name="feed" size=${18} /> Feed ${FEED_LENGTH_MM} mm</button>`}
    </div>

    <div class="printer-links">
    ${p.transport && html`<button class="link-button forget" disabled=${p.busy} onClick=${forgetPrinter}>Forget this printer</button>`}
    <details class="help">
      <summary>Printer not in the list?</summary>
      <p>On Android, Chrome needs the <b>Nearby devices</b> permission (Settings › Apps › Chrome › Permissions).
        After allowing it, force stop Chrome and open it again; until then the list says "No compatible devices found".</p>
      <p>The printer has to be switched on and paired in the phone's or computer's Bluetooth settings.</p>
    </details>
    </div>
  </div>`;
}

const shortDate = (iso) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });

// The tape counter for the tape in the printer: what is left, and the new roll and correct actions
function TapeRoll({ info }) {
  useStore(app);
  const d = useStore(drive);
  const [sheet, setSheet] = useState(null);  // 'new' or 'correct'
  const roll = loadedRoll(info);
  const close = () => setSheet(null);
  const sheets = html`
    <${NewRollSheet} open=${sheet === 'new'} info=${info} onClose=${close} onDone=${close} />
    <${CorrectSheet} open=${sheet === 'correct'} info=${info} onClose=${close} />`;
  if (!roll) {
    return html`<section class="tape-roll">
      <div class="tape-roll-head"><h3>Tape roll</h3><span class="hint">${tapeName(info)}</span></div>
      <p class="hint">Say which roll is in the printer, and Cube Labeler counts how much tape is left as you print.</p>
      <div class="button-row"><button class="secondary" onClick=${() => setSheet('new')}>Set tape roll</button></div>
      ${sheets}
    </section>`;
  }
  const left = rollLeft(roll);
  const prints = rollPrints(roll);
  return html`<section class=${`tape-roll${left < LOW_TAPE_MM ? ' low' : ''}`}>
    <div class="tape-roll-head"><h3>Tape roll</h3><span class="hint">${tapeName(info)}, loaded ${shortDate(roll.loaded)}</span></div>
    <p class="tape-left"><b>${formatTape(left)}</b> of ${formatTape(roll.length_mm)} left</p>
    <div class="tape-bar" role="meter" aria-label="Tape left" aria-valuemin="0" aria-valuemax=${roll.length_mm} aria-valuenow=${Math.round(left)}>
      <span style=${{ width: `${Math.min(100, (100 * left) / roll.length_mm)}%` }}></span>
    </div>
    <p class="hint">${`${prints === 1 ? '1 print' : `${prints} prints`} so far, ${formatTape(rollUsed(roll))} used including the ${FEED_LENGTH_MM} mm feed of each print. `
      + (d.on ? 'Counted on all your devices through Drive sync.' : 'Turn on Drive sync to count on all your devices.')}</p>
    <div class="button-row">
      <button class="secondary" onClick=${() => setSheet('new')}>New roll</button>
      <button class="secondary" onClick=${() => setSheet('correct')}>Correct the count</button>
    </div>
    ${sheets}
  </section>`;
}

const LENGTH_OPTIONS = [...ROLL_LENGTHS_MM.map((mm) => [String(mm), formatTape(mm)]), ['other', 'Other']];

// Which roll went in: the count starts again from full
export function NewRollSheet({ open, info, onClose, onDone, action = 'Start counting' }) {
  const last = info && loadedRoll(info);
  const [choice, setChoice] = useState(null);
  const [other, setOther] = useState('');
  const picked = choice ?? (last && !ROLL_LENGTHS_MM.includes(last.length_mm) ? 'other' : String(last ? last.length_mm : ROLL_LENGTHS_MM[0]));
  const otherText = other || (last && picked === 'other' ? String(last.length_mm / 1000) : '');
  const lengthMm = picked === 'other' ? Math.round(parseFloat(otherText.replace(',', '.')) * 1000) : Number(picked);
  const valid = lengthMm >= 100 && lengthMm <= 100000;
  const done = () => {
    startRoll(info, lengthMm);
    setChoice(null);
    setOther('');
    onDone();
  };
  return html`<${Sheet} open=${open} title="New tape roll" onClose=${onClose}>
    ${info && html`<div class="tape-sheet">
      <p>Which roll did you put in? The count starts again from full.</p>
      <${Segmented} label="Roll length" options=${LENGTH_OPTIONS} value=${picked} onChange=${setChoice} />
      ${picked === 'other' && html`<label class="field">
        <span class="field-label">Length in metres</span>
        <input type="number" class="tape-number" min="0.1" max="100" step="0.1" inputmode="decimal" value=${otherText}
          onInput=${(e) => setOther(e.currentTarget.value)} />
      </label>`}
      <p class="hint">Brother TZe rolls are 8 m. Some other brands are 4 m or 5 m.</p>
      <div class="field">
        <span class="field-label">Tape</span>
        <span>${info.tape_width_mm} mm ${info.tape_type ? info.tape_type.toLowerCase() : ''}, ${String(info.tape_color).toLowerCase()} with ${String(info.text_color).toLowerCase()} text <span class="hint">(read from the printer)</span></span>
      </div>
      <div class="button-row">
        <button class="primary" disabled=${!valid} onClick=${done}>${action}</button>
        <button class="secondary" onClick=${onClose}>Cancel</button>
      </div>
    </div>`}
  <//>`;
}

// Sets what is left, when the count and the roll disagree
function CorrectSheet({ open, info, onClose }) {
  const roll = loadedRoll(info);
  const [text, setText] = useState('');
  const shown = text || (roll ? String(Math.floor(rollLeft(roll) / 100) / 10) : '');
  const leftMm = Math.round(parseFloat(shown.replace(',', '.')) * 1000);
  const valid = roll && leftMm >= 0 && leftMm <= roll.length_mm;
  const done = () => {
    correctCount(info, leftMm);
    setText('');
    onClose();
  };
  return html`<${Sheet} open=${open} title="Correct the count" onClose=${onClose}>
    ${roll && html`<div class="tape-sheet">
      <p>How much tape is left on the roll? Counting goes on from there.</p>
      <label class="field">
        <span class="field-label">Tape left in metres</span>
        <input type="number" class="tape-number" min="0" max=${roll.length_mm / 1000} step="0.1" inputmode="decimal" value=${shown}
          onInput=${(e) => setText(e.currentTarget.value)} />
      </label>
      <p class="hint">For when the count is off, for example after printing from another app or device without sync.</p>
      <div class="button-row">
        <button class="primary" disabled=${!valid} onClick=${done}>Save</button>
        <button class="secondary" onClick=${onClose}>Cancel</button>
      </div>
    </div>`}
  <//>`;
}
