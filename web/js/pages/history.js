// Print history: the labels printed lately. The one picked shows large on the left with what it
// was and buttons to print it again, queue it or edit it; the list on the right finds them by
// text, kind and day.
import { useEffect, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Icon } from '../icons.js';
import { Menu, useWide } from '../ui.js';
import { useStore } from '../state.js';
import { Preview } from '../preview.js';
import { binSummary } from './bin.js';
import { app, boot, printer, connectPrinter, itemTitle, textLines, openItem, printItem, queueItem, renderItem, say, BIN_FONT } from '../app.js';
import { history, historySize, entryItem, loadHistory, setPinned, removeEntry, clearHistory } from '../history.js';

const FILTERS = [['all', 'All'], ['text', 'Text'], ['bin', 'Bin'], ['pinned', 'Pinned']];

const dayStart = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
const timeOf = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

// "Today", "Yesterday" or the date, for the day groups and the Printed line
function dayName(iso) {
  const date = new Date(iso);
  const days = Math.round((dayStart(new Date()) - dayStart(date)) / 86400000);
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString(undefined, { weekday: days < 7 ? 'long' : undefined, day: 'numeric', month: 'long', year: sameYear ? undefined : 'numeric' });
}

function searchText(entry) {
  if (entry.mode === 'bin') return `${itemTitle(entry)} ${binSummary(entry.bin)}`.toLowerCase();
  return `${textLines(entry.label).join(' ')} ${entry.label.qr_data || ''}`.toLowerCase();
}

function describe(entry, render) {
  const length = render && render.metrics ? `, ${Math.round(render.metrics.print_length_mm)} mm long` : '';
  if (entry.mode === 'bin') return `Bin label, ${entry.tape_width_mm} mm tape${length}, ${(entry.font && entry.font.bin_font) || BIN_FONT}`;
  const l = entry.label;
  const extras = [l.qr_enabled && l.qr_data && 'QR code', l.image && 'picture'].filter(Boolean);
  return `Text label, ${entry.tape_width_mm} mm tape${length}, ${l.font_name}${extras.length ? ` with ${extras.join(' and ')}` : ''}`;
}

function printedLine(entry) {
  const when = `${dayName(entry.printed)} at ${timeOf(entry.printed)}`;
  const parts = [entry.copies > 1 ? `${when}, ${entry.copies} copies` : when];
  if (entry.times > 1) parts.push(`${entry.times} times in all`);
  return parts.join(' · ');
}

// The picked entry drawn like the Label page's preview
function useEntryRender(entry, ready) {
  const [render, setRender] = useState(null);
  useEffect(() => {
    if (!entry || !ready) { setRender(null); return undefined; }
    let gone = false;
    let made = null;
    renderItem(entryItem(entry)).then((r) => {
      made = r;
      if (gone) { URL.revokeObjectURL(r.previewUrl); URL.revokeObjectURL(r.dotsUrl); } else setRender(r);
    }, (err) => { if (!gone) { setRender(null); say(`Couldn't draw the label: ${err.message || err}`, true); } });
    return () => {
      gone = true;
      if (made) { URL.revokeObjectURL(made.previewUrl); URL.revokeObjectURL(made.dotsUrl); }
    };
  }, [entry && entry.id, entry && entry.changed, ready]);
  return render && entry ? render : null;
}

function Star({ on, onClick, title }) {
  return html`<button class=${`icon-button star${on ? ' on' : ''}`} aria-pressed=${on} aria-label=${title} title=${title} onClick=${onClick}>
    <${Icon} name="star" size=${20} filled=${on} /></button>`;
}

export function HistoryPage() {
  const h = useStore(history);
  useStore(app);  // the history size comes from the settings
  const p = useStore(printer);
  const ready = useStore(boot).phase === 'ready';
  const wide = useWide();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [picked, setPicked] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => { loadHistory(); }, []);

  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = h.entries.filter((e) => (filter === 'all' || (filter === 'pinned' ? e.pinned : e.mode === filter))
    && words.every((w) => searchText(e).includes(w)));
  const entry = h.entries.find((e) => e.id === picked) || shown[0] || null;
  const render = useEntryRender(entry, ready);

  const groups = [];
  for (const e of shown) {
    const day = dayName(e.printed);
    if (!groups.length || groups[groups.length - 1].day !== day) groups.push({ day, entries: [] });
    groups[groups.length - 1].entries.push(e);
  }
  const unpinned = h.entries.filter((e) => !e.pinned).length;
  const pinned = h.entries.length - unpinned;
  const keep = historySize();

  const pick = (e) => {
    setPicked(e.id);
    // On a phone the picked label is shown above the list
    if (!wide) window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  const title = entry ? itemTitle(entry) : '';
  const short = title.length > 30 ? `${title.slice(0, 29)}…` : title;
  const needsPrinter = p.supported && !p.transport;

  return html`<div class="label-page history-page">
    <div class="label-preview-col">
      <${Preview} strip=${entry ? render : null} tapeMm=${entry ? entry.tape_width_mm : 12}
        empty=${h.entries.length ? 'No printed label matches the search.' : 'Labels you print show up here, so you can print them again.'} />
      ${entry && html`<section class="card history-facts">
        <div class="card-head">
          <h2 class="card-title" title=${title}>${title}</h2>
          <span class="facts-tools">
            <${Star} on=${entry.pinned} title=${entry.pinned ? 'Unpin' : 'Pin: never drops off the history'}
              onClick=${() => setPinned(entry.id, !entry.pinned)} />
            <span class="menu-anchor">
              <button class="icon-button" aria-label="More" onClick=${() => setMenuOpen(true)}><${Icon} name="more" size=${20} /></button>
              <${Menu} open=${menuOpen} onClose=${() => setMenuOpen(false)} items=${[
                { label: 'Remove from history', icon: 'trash', action: () => { removeEntry(entry.id); setPicked(null); say(`Removed "${short}" from the history.`); } },
                { label: 'Clear history', icon: 'close', action: () => {
                  clearHistory();
                  setPicked(null);
                  say(pinned ? 'History cleared. Pinned labels are kept.' : 'History cleared.');
                } },
              ]} />
            </span>
          </span>
        </div>
        <dl class="facts">
          <dt>Printed</dt><dd>${printedLine(entry)}</dd>
          <dt>Label</dt><dd>${describe(entry, render)}</dd>
          <dt>Pinned</dt><dd>${entry.pinned ? 'Yes, it never drops off the history' : `No, it drops off after ${keep} newer prints`}</dd>
        </dl>
      </section>`}
      <div class="action-bar">
        <div class="action-buttons">
          ${needsPrinter
            ? html`<button class="primary big" disabled=${!ready || p.busy} onClick=${connectPrinter}>
                <${Icon} name="printer" size=${20} /> <span>Connect<span class="hide-narrow"> printer</span></span></button>`
            : html`<button class="primary big" disabled=${!ready || !entry || p.busy || !p.supported} onClick=${() => printItem(entryItem(entry))}>
                <${Icon} name="printer" size=${20} /> ${p.busy ? 'Printing...' : html`<span>Print<span class="hide-narrow"> again</span></span>`}</button>`}
          <button class="secondary big" disabled=${!ready || !entry} onClick=${() => queueItem(entryItem(entry))}>
            <${Icon} name="plus" size=${20} /> <span><span class="hide-narrow">Add to queue</span><span class="show-narrow">Add</span></span></button>
          <button class="secondary big" disabled=${!ready || !entry} onClick=${() => { openItem(entryItem(entry)); say(`Editing "${short}" from the history.`); }}>
            <${Icon} name="edit" size=${20} /> <span>Edit</span></button>
        </div>
      </div>
    </div>

    <div class="label-edit-col">
      <section class="card history-card">
        <div class="card-head">
          <h2 class="card-title">History</h2>
          <span class="hint">${unpinned} of ${keep}${pinned ? ` · ${pinned} pinned` : ''}</span>
        </div>
        <p class="hint history-note">Your last ${keep} printed labels. Pinned ones always stay.</p>
        <label class="search-box">
          <${Icon} name="search" size=${18} />
          <input type="search" placeholder="Search history" aria-label="Search history" value=${query}
            onInput=${(e) => setQuery(e.currentTarget.value)} />
        </label>
        <div class="segmented history-filter" role="radiogroup" aria-label="Show">
          ${FILTERS.map(([value, text]) => html`<label class=${filter === value ? 'selected' : ''}>
            <input type="radio" name="history-filter" value=${value} checked=${filter === value} onChange=${() => setFilter(value)} />
            <span>${text}</span></label>`)}
        </div>
        ${!h.entries.length ? html`<div class="history-empty">
            <${Icon} name="history" size=${36} />
            <p>No printed labels yet.</p>
            <p class="hint">Every label you print is kept here: open it again, queue it or print it once more.</p>
          </div>`
          : !shown.length ? html`<p class="hint history-empty">${filter === 'pinned' && !words.length
            ? 'No pinned labels. Pin one with its star to keep it for good.' : 'Nothing matches.'}</p>`
          : groups.map((g) => html`<div class="history-group" key=${g.day}>
            <h3 class="group-title">${g.day}</h3>
            <ul class="history-list">
              ${g.entries.map((e) => {
                const t = itemTitle(e);
                return html`<li key=${e.id} class=${`history-row${entry && e.id === entry.id ? ' active' : ''}`}>
                  <button class="history-pick" aria-current=${entry && e.id === entry.id ? 'true' : undefined} onClick=${() => pick(e)}>
                    <span class="queue-thumb">${h.thumbs[e.id] ? html`<img src=${h.thumbs[e.id]} alt="" />` : ''}</span>
                    <span class="queue-body">
                      <span class="history-title" title=${t}>${t}</span>
                      <span class="hint queue-detail">${e.tape_width_mm} mm · ${timeOf(e.printed)}${e.copies > 1 ? ` · ×${e.copies}` : ''}</span>
                    </span>
                  </button>
                  <${Star} on=${e.pinned} title=${e.pinned ? `Unpin ${t}` : `Pin ${t}`} onClick=${() => setPinned(e.id, !e.pinned)} />
                </li>`;
              })}
            </ul>
          </div>`)}
      </section>
    </div>
  </div>`;
}
