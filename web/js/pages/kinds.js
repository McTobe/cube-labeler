// Picking the kind of label: a sheet with every kind as a card, the way the Templates page shows
// its starting points (a picture of an example label, the name and what it is for). On a wide
// screen it is a dialog with four cards a row; on a phone it slides up, two cards a row.
import { useEffect } from 'preact/hooks';
import { html } from '../html.js';
import { Icon } from '../icons.js';
import { Sheet } from '../ui.js';
import { useStore } from '../state.js';
import { app, boot, setMode, DEFAULT_LABEL, DEFAULT_PORTS, DEFAULT_OUTLET, DEFAULT_DATES, DEFAULT_ASSET, DEFAULT_BREAKERS } from '../app.js';
import { dateText } from '../dates.js';
import { templates, thumbnail } from '../templates.js';

// What each kind is for, in one line
export const KIND_NOTES = {
  text: 'Any text, with QR codes, barcodes and pictures.',
  bin: 'Drawers of screws and parts, on 12 mm tape.',
  flag: 'Wraps round a cable and reads from both sides.',
  ports: 'One strip over a row of switch or panel ports.',
  outlet: 'Codes for wall outlets, like DA01P02 3/4.',
  breakers: 'Names over the breakers in a fuse box.',
  asset: 'Numbered tags with a barcode or QR code.',
  date: 'Food and leftovers, with made and use-by dates.',
};

// A small example of each kind, drawn once for its card
export const KIND_EXAMPLES = {
  text: () => ({ mode: 'text', label: { ...DEFAULT_LABEL, text: 'Cube Labeler' } }),
  bin: () => {
    const bin = app.get().bin;
    return bin ? { mode: 'bin', bin: { ...bin.fastener, kind: 'fastener' } } : null;
  },
  flag: () => ({ mode: 'text', label: { ...DEFAULT_LABEL, layout: 'flag', text: 'NAS', font_name: 'Arimo Bold' } }),
  ports: () => ({ mode: 'text', label: { ...DEFAULT_PORTS, port_count: 6 } }),
  outlet: () => ({ mode: 'text', label: { ...DEFAULT_OUTLET, text: 'DA01P02 3/4' } }),
  date: () => {
    const label = { ...DEFAULT_DATES, date_name: 'Chili', date_portions: '2', date_show: 'use' };
    return { mode: 'text', label: { ...label, text: dateText(label) } };
  },
  asset: () => ({ mode: 'text', label: { ...DEFAULT_ASSET, asset_owner: 'Workshop', asset_number: '0042' } }),
  breakers: () => ({ mode: 'text', label: { ...DEFAULT_BREAKERS, breaker_prefix: 'F',
    // Single breakers only: in a small picture a wide one reads as a gap
    breakers: ['Lights', 'Oven', 'Washer', 'Bath', 'Garage'].map((name) => ({ name, number: '', modules: 1, blank: false })) } }),
};

function KindCard({ kind, on, pick }) {
  const { thumbs } = useStore(templates);
  const { phase } = useStore(boot);
  const key = `kind:${kind.id}`;
  const example = KIND_EXAMPLES[kind.id];
  useEffect(() => {
    const item = example && example();
    if (phase === 'ready' && item) thumbnail(key, item);
  }, [phase]);
  return html`<li class=${on ? 'card template-card kind-card on' : 'card template-card kind-card'}>
    <button class="template-open" role="menuitemradio" aria-checked=${on} onClick=${() => pick(kind.id)}>
      <span class="template-thumb">${thumbs[key] ? html`<img src=${thumbs[key]} alt="" />` : html`<${Icon} name=${kind.icon} size=${28} />`}</span>
      <span class="kind-name"><${Icon} name=${kind.icon} size=${18} /><span class="template-name">${kind.name}</span></span>
      <span class="hint">${KIND_NOTES[kind.id] || ''}</span>
    </button>
  </li>`;
}

// kinds: the MODES that are ready (label.js), so this file needs no list of its own
export function KindSheet({ open, onClose, kinds }) {
  const { mode } = useStore(app);
  const pick = (id) => { onClose(); setMode(id); };
  return html`<${Sheet} open=${open} title="Kind of label" onClose=${onClose} wide>
    <ul class="template-grid kind-grid" role="menu">
      ${kinds.map((kind) => html`<${KindCard} key=${kind.id} kind=${kind} on=${mode === kind.id} pick=${pick} />`)}
    </ul>
  <//>`;
}
