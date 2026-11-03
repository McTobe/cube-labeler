// Power outlet labels: a code like A1A Gr. 13 built from its parts (see power-code.js). The twin
// of the network outlet editor (outlet.js): the parts sit under the preview in three columns,
// the code style and a short how-to sit in the side panel.
import { useEffect, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Field, Section, Segmented } from '../ui.js';
import { useStore } from '../state.js';
import { app, boot, updatePower, addPowers, say, MAX_POWER_ROW } from '../app.js';
import {
  POWER_GROUP_KINDS, POWER_PHASES, POWER_VOLTAGES, POWER_SEPARATORS, POWER_DIGITS, POWER_LINES, POWER_EXTRAS,
  powerGroup, powerStyleSummary,
} from '../power-code.js';

const SKIP = 'Leave empty to skip';

// A text field for one part of the code; what is typed shows as typed, spaces included
function Part({ label, field, placeholder = SKIP, inputmode = 'text' }) {
  const { power } = useStore(app);
  const value = power[field] ?? '';
  const [text, setText] = useState(String(value));
  useEffect(() => { if (String(value) !== text.trim() && String(value) !== text) setText(String(value)); }, [value]);
  return html`<${Field} label=${label}>
    <input type="text" inputmode=${inputmode} value=${text} placeholder=${placeholder} autocomplete="off" spellcheck="false"
      onInput=${(e) => { setText(e.currentTarget.value); updatePower({ [field]: e.currentTarget.value.trim() }); }} />
  <//>`;
}

// How many copies to add; empty or not a number keeps the last good value in the label
function Copies() {
  const { power } = useStore(app);
  const value = power.power_row;
  const [text, setText] = useState(String(value ?? ''));
  useEffect(() => { if (parseInt(text, 10) !== Number(value)) setText(String(value ?? '')); }, [value]);
  const onInput = (e) => {
    const typed = e.currentTarget.value;
    setText(typed);
    const n = /^\s*\d+\s*$/.test(typed) ? parseInt(typed, 10) : NaN;
    if (n >= 1 && n <= MAX_POWER_ROW) updatePower({ power_row: n });
  };
  return html`<${Field} label="Labels in a row">
    <input type="text" inputmode="numeric" value=${text} placeholder="1" autocomplete="off" onInput=${onInput}
      onBlur=${() => setText(String(value ?? ''))} />
  <//>`;
}

function addAndNext() {
  if (!addPowers(true)) return;
  const { power } = app.get();
  say(`${app.get().status.text} Next up: ${powerGroup(power) || 'the next group'}.`);
}

// The parts of the code: under the preview on a wide screen, first on a phone
export function PowerCard() {
  const { power } = useStore(app);
  const { phase } = useStore(boot);
  return html`<section class="card bin-card outlet-card power-card">
    <div class="card-head">
      <h2 class="card-title">Outlet code</h2>
      <button class="secondary" disabled=${phase !== 'ready'} title="Add to the queue and count the group on for the next outlets"
        onClick=${addAndNext}>Add to queue and start the next</button>
    </div>
    <div class="bin-grid three outlet-grid">
      <div class="bin-col">
        <${Part} label="Building" field="power_building" />
        <${Part} label="Floor" field="power_floor" />
        <${Part} label="Room" field="power_room" />
      </div>
      <div class="bin-col">
        <${Part} label="Central" field="power_central" placeholder="A1A" />
        <${Segmented} label="Group is called" options=${POWER_GROUP_KINDS} value=${power.power_group_kind}
          onChange=${(power_group_kind) => updatePower({ power_group_kind })} />
        <${Part} label="Group" field="power_group" placeholder="13" inputmode="numeric" />
      </div>
      <div class="bin-col">
        <${Segmented} label="Phase" options=${POWER_PHASES} value=${power.power_phase}
          onChange=${(power_phase) => updatePower({ power_phase })} />
        <${Segmented} label="Voltage" options=${POWER_VOLTAGES} value=${power.power_voltage}
          onChange=${(power_voltage) => updatePower({ power_voltage })} />
        <${Copies} />
      </div>
    </div>
  </section>`;
}

// The side panel: what the mode is for, then how the code is written
export function PowerHelp() {
  return html`<section class="card drawer-card">
    <h2 class="card-title">Power outlet labels</h2>
    <p class="hint">Labels for wall sockets and other outlets, with the central and the group that feeds them, like A1A Gr. 13.</p>
    <ol class="how-to">
      <li>Type the central and the group. Empty parts are left out.</li>
      <li>Add the phase or voltage if you want them on the label. All is L1-L3, for three-phase outlets.</li>
      <li>Add the label to the queue.</li>
    </ol>
    <p class="hint">One group usually feeds several outlets, so Labels in a row adds copies of the same label. "Add to queue and start the next" then counts the group on, so Gr. 13 becomes Gr. 14.</p>
  </section>`;
}

export function PowerStyleSection() {
  const { power } = useStore(app);
  return html`<${Section} id="power-style" title="Code style" summary=${powerStyleSummary(power)}>
    <${Segmented} label="Between the parts" options=${POWER_SEPARATORS} value=${power.power_sep}
      onChange=${(power_sep) => updatePower({ power_sep })} />
    <${Segmented} label="Numbers" options=${POWER_DIGITS.map(([v, n]) => [String(v), n])} value=${String(power.power_digits)}
      onChange=${(v) => updatePower({ power_digits: Number(v) })} />
    <${Segmented} label="Lines" options=${POWER_LINES.map(([v, n]) => [String(v), n])} value=${String(power.power_lines)}
      onChange=${(v) => updatePower({ power_lines: Number(v) })} />
    <${Segmented} label="Phase and voltage" options=${POWER_EXTRAS} value=${power.power_extra}
      onChange=${(power_extra) => updatePower({ power_extra })} />
    <p class="hint">Two lines puts the building, floor and room small on top. Small line puts the phase and voltage small under the code. Numbers pads the group with zeros, so 3 becomes 03 or 003.</p>
  <//>`;
}
