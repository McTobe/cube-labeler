// Network outlet labels: a code like DA01P02 3/4 built from its parts (see outlet-code.js).
// The parts sit under the preview in three columns like the bin label editor; the code style
// and a short how-to sit in the side panel.
import { useEffect, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Field, Section, Segmented } from '../ui.js';
import { useStore } from '../state.js';
import { app, boot, updateOutlet, addOutlets, say, MAX_OUTLET_ROW } from '../app.js';
import {
  OUTLET_PANEL_KINDS, OUTLET_PORTS, OUTLET_SEPARATORS, OUTLET_PAIRS, OUTLET_DIGITS, OUTLET_LINES,
  outletPorts, outletStyleSummary,
} from '../outlet-code.js';

const SKIP = 'Leave empty to skip';

// A text field for one part of the code; what is typed shows as typed, spaces included
function Part({ label, field, placeholder = SKIP, inputmode = 'text' }) {
  const { outlet } = useStore(app);
  const value = outlet[field] ?? '';
  const [text, setText] = useState(String(value));
  useEffect(() => { if (String(value) !== text.trim() && String(value) !== text) setText(String(value)); }, [value]);
  return html`<${Field} label=${label}>
    <input type="text" inputmode=${inputmode} value=${text} placeholder=${placeholder} autocomplete="off" spellcheck="false"
      onInput=${(e) => { setText(e.currentTarget.value); updateOutlet({ [field]: e.currentTarget.value.trim() }); }} />
  <//>`;
}

// A whole number field; empty or not a number keeps the last good value in the label
function Count({ label, field, min, max, placeholder }) {
  const { outlet } = useStore(app);
  const value = outlet[field];
  const [text, setText] = useState(String(value ?? ''));
  useEffect(() => { if (parseInt(text, 10) !== Number(value)) setText(String(value ?? '')); }, [value]);
  const onInput = (e) => {
    const typed = e.currentTarget.value;
    setText(typed);
    const n = /^\s*\d+\s*$/.test(typed) ? parseInt(typed, 10) : NaN;
    if (n >= min && n <= max) updateOutlet({ [field]: n });
  };
  return html`<${Field} label=${label}>
    <input type="text" inputmode="numeric" value=${text} placeholder=${placeholder} autocomplete="off" onInput=${onInput}
      onBlur=${() => setText(String(value ?? ''))} />
  <//>`;
}

function addAndNext() {
  if (!addOutlets(true)) return;
  const { outlet } = app.get();
  say(`${app.get().status.text} Next up: ${outletPorts(outlet) || 'the next outlet'}.`);
}

// The parts of the code: under the preview on a wide screen, first on a phone
export function OutletCard() {
  const { outlet } = useStore(app);
  const { phase } = useStore(boot);
  const kind = OUTLET_PANEL_KINDS.find(([v]) => v === outlet.outlet_panel_kind) || OUTLET_PANEL_KINDS[0];
  return html`<section class="card bin-card outlet-card">
    <div class="card-head">
      <h2 class="card-title">Outlet code</h2>
      <button class="secondary" disabled=${phase !== 'ready'} title="Add to the queue and count the ports on for the next outlet"
        onClick=${addAndNext}>Add to queue and start the next</button>
    </div>
    <div class="bin-grid three outlet-grid">
      <div class="bin-col">
        <${Part} label="Building" field="outlet_building" />
        <${Part} label="Floor" field="outlet_floor" />
        <${Part} label="Room" field="outlet_room" />
      </div>
      <div class="bin-col">
        <${Part} label="Rack" field="outlet_rack" placeholder="DA01" />
        <${Segmented} label="Panel is called" options=${OUTLET_PANEL_KINDS} value=${kind[0]}
          onChange=${(outlet_panel_kind) => updateOutlet({ outlet_panel_kind })} />
        <${Part} label=${kind[0] === 'P' ? 'Panel' : kind[0] === 'U' ? 'Rack unit (U)' : 'Module (M)'} field="outlet_panel" placeholder="02" />
      </div>
      <div class="bin-col">
        <${Segmented} label="Ports on the outlet" options=${OUTLET_PORTS.map(([v, n]) => [String(v), n])}
          value=${String(outlet.outlet_ports)} onChange=${(v) => updateOutlet({ outlet_ports: Number(v) })} />
        <${Part} label="First port" field="outlet_first" placeholder=${SKIP} inputmode="numeric" />
        <${Count} label="Labels in a row" field="outlet_row" min=${1} max=${MAX_OUTLET_ROW} placeholder="1" />
      </div>
    </div>
  </section>`;
}

// The side panel: what the mode is for, then how the code is written
export function OutletHelp() {
  return html`<section class="card drawer-card">
    <h2 class="card-title">Network outlet labels</h2>
    <p class="hint">Labels for wall outlets and patch panel ports, with a code that says where the cable goes, like DA01P02 3/4.</p>
    <ol class="how-to">
      <li>Fill in the parts of the code you use. Empty parts are left out.</li>
      <li>Pick One, Two or Four ports on the outlet and the first port.</li>
      <li>Add the label to the queue.</li>
    </ol>
    <p class="hint">"Add to queue and start the next" counts the ports on, so 3/4 becomes 5/6. Labels in a row adds several at once: 3/4, 5/6, 7/8.</p>
  </section>`;
}

export function OutletStyleSection() {
  const { outlet } = useStore(app);
  return html`<${Section} id="outlet-style" title="Code style" summary=${outletStyleSummary(outlet)}>
    <${Segmented} label="Between the parts" options=${OUTLET_SEPARATORS} value=${outlet.outlet_sep}
      onChange=${(outlet_sep) => updateOutlet({ outlet_sep })} />
    <${Segmented} label="Two ports shown as" options=${OUTLET_PAIRS} value=${outlet.outlet_pair}
      onChange=${(outlet_pair) => updateOutlet({ outlet_pair })} />
    <${Segmented} label="Numbers" options=${OUTLET_DIGITS.map(([v, n]) => [String(v), n])} value=${String(outlet.outlet_digits)}
      onChange=${(v) => updateOutlet({ outlet_digits: Number(v) })} />
    <${Segmented} label="Lines" options=${OUTLET_LINES.map(([v, n]) => [String(v), n])} value=${String(outlet.outlet_lines)}
      onChange=${(v) => updateOutlet({ outlet_lines: Number(v) })} />
    <p class="hint">Two lines puts the building, floor and room small on top and the rack, panel and ports big under them. Numbers pads the panel and port numbers with zeros, so 2 becomes 02 or 002.</p>
  <//>`;
}
