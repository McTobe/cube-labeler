// Date label editor: food for the freezer or the fridge, and opened jars. What is in it, the
// day it was made and how long it keeps; the use-by date is worked out (see dates.js).
// Laid out like the bin label editor: three columns under the preview, settings on the right.
import { useRef } from 'preact/hooks';
import { html } from '../html.js';
import { Field, Section, Segmented } from '../ui.js';
import { useStore } from '../state.js';
import { Chips } from './bin.js';
import { app, boot, updateDates, addToQueue, say } from '../app.js';
import { KEEPS, DATE_NAMES, DATE_SHOWS, DATE_STYLES, madeDay, useByDay, formatDay, parseDay, isoDay } from '../dates.js';

const SHORT_MONTH = { month: 'short', day: 'numeric' };

// Made: today, yesterday, or a day picked from the calendar. A picked day shows on its button.
function MadeField({ dates }) {
  const pickRef = useRef(null);
  const picked = parseDay(dates.date_made);
  const value = picked ? 'pick' : dates.date_made === 'yesterday' ? 'yesterday' : 'today';
  const openPicker = () => {
    const input = pickRef.current;
    input.value = isoDay(madeDay(dates.date_made));
    try { input.showPicker(); } catch { input.focus(); }
  };
  // The picked button is already on, so clicking it again doesn't change the choice
  const onClick = (e) => {
    if (picked && e.target.closest('label:last-child')) { e.preventDefault(); openPicker(); }
  };
  const onPick = (e) => {
    const day = parseDay(e.currentTarget.value);
    if (!day) return;
    const today = isoDay(new Date());
    const yesterday = isoDay(madeDay('yesterday'));
    const made = e.currentTarget.value === today ? 'today' : e.currentTarget.value === yesterday ? 'yesterday' : e.currentTarget.value;
    updateDates({ date_made: made });
  };
  const options = [['today', 'Today'], ['yesterday', 'Yesterday'],
    ['pick', picked ? picked.toLocaleDateString('en-GB', SHORT_MONTH) : 'Pick a day']];
  return html`<div class="made-field" onClickCapture=${onClick}>
    <${Segmented} label="Made" options=${options} value=${value}
      onChange=${(v) => (v === 'pick' ? openPicker() : updateDates({ date_made: v }))} />
    <input ref=${pickRef} class="day-picker" type="date" tabindex="-1" aria-hidden="true" onChange=${onPick} />
  </div>`;
}

// Adds the label to the queue and clears the name and portions for the next one; the dates stay
function addAndNext() {
  if (!addToQueue()) return;
  updateDates({ date_name: '', date_portions: '' });
  say(`${app.get().status.text} Ready for the next one.`);
  setTimeout(() => {
    const first = document.querySelector('.date-card input[name="date-name"]');
    if (first) first.focus();
  });
}

// What is in it, when it was made and how long it keeps: under the preview on a wide screen
export function DateCard() {
  const { dates } = useStore(app);
  const { phase } = useStore(boot);
  const keeps = KEEPS.find(([id]) => id === dates.date_keeps) ? dates.date_keeps : '3m';
  const name = dates.date_name.trim().toLowerCase();
  return html`<section class="card bin-card date-card">
    <div class="card-head">
      <h2 class="card-title">What's in it</h2>
      <button class="secondary" disabled=${phase !== 'ready'} title="Add to the queue and clear the name and portions for the next one"
        onClick=${addAndNext}>Add to queue and start the next</button>
    </div>
    <div class="bin-grid three dates">
      <div class="bin-col">
        <div class="bin-group">
          <${Field} label="Name">
            <input type="text" name="date-name" value=${dates.date_name} placeholder="Chili con carne" autocomplete="off"
              onInput=${(e) => updateDates({ date_name: e.currentTarget.value })} />
          <//>
          <${Chips} label="Common names" values=${DATE_NAMES}
            current=${DATE_NAMES.find((n) => name.startsWith(n.toLowerCase()))} onPick=${(date_name) => updateDates({ date_name })} />
        </div>
      </div>
      <div class="bin-col">
        <div class="bin-group">
          <${MadeField} dates=${dates} />
        </div>
        <div class="bin-group">
          <${Field} label="Keeps for">
            <${Chips} label="Keeps for" cols=${3} values=${KEEPS.map(([, n]) => n)}
              current=${KEEPS.find(([id]) => id === keeps)[1]}
              onPick=${(n) => updateDates({ date_keeps: KEEPS.find(([, v]) => v === n)[0] })} />
          <//>
        </div>
      </div>
      <div class="bin-col">
        <div class="bin-group">
          <${Field} label="Portions">
            <input type="text" value=${dates.date_portions} placeholder="Optional, e.g. 2" autocomplete="off"
              onInput=${(e) => updateDates({ date_portions: e.currentTarget.value })} />
          <//>
        </div>
        <div class="bin-group">
          <${Segmented} label="Show" options=${DATE_SHOWS} value=${dates.date_show}
            onChange=${(date_show) => updateDates({ date_show })} />
        </div>
      </div>
    </div>
  </section>`;
}

// The how-to and the date style, in the side panel
export function DateOptions() {
  const { dates } = useStore(app);
  const today = new Date();
  const made = madeDay(dates.date_made, today);
  const style = DATE_STYLES.includes(dates.date_style) ? dates.date_style : 'words';
  return html`
    <section class="card drawer-card">
      <h2 class="card-title">Date labels</h2>
      <p class="hint">Labels for the freezer, the fridge and opened jars, with the day it was made and when to use it by.</p>
      <ol class="how-to">
        <li>Type or tap what is in it.</li>
        <li>Pick how long it keeps. The use-by date is worked out for you.</li>
        <li>Add the label to the queue.</li>
      </ol>
      <p class="hint">Filling the freezer? "Add to queue and start the next" keeps the dates and clears the name for the next one.</p>
    </section>
    <${Section} id="date-style" title="Date style" summary=${formatDay(today, style)}>
      <${Segmented} label="Dates as" options=${DATE_STYLES.map((s) => [s, formatDay(today, s)])} value=${style}
        onChange=${(date_style) => updateDates({ date_style })} />
      <p class="hint">${dates.date_show === 'made' ? `Made ${formatDay(made, style)}.`
        : `Made ${formatDay(made, style)}, use by ${formatDay(useByDay(made, dates.date_keeps), style)}.`} "Today" is the day the label is printed, also from a template.</p>
    <//>`;
}
