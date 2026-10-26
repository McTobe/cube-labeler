// The Icons page: browse and search the icon library, keep favourites, add your own icons,
// and put an icon on a text label or a bin label. IconPickerSheet is the same browser in a
// sheet, for picking an icon straight from the label editors.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Icon } from '../icons.js';
import { Field, Sheet, downloadBlob, useWide } from '../ui.js';
import { useStore } from '../state.js';
import {
  app, boot, say, setMode, setImageBytes, setBinIconBytes, iconPrintPreview,
} from '../app.js';
import { IconEditorSheet } from './icon-editor.js';
import {
  library, views, listIcons, viewCount, iconUrl, iconBytes, isFavourite, toggleFavourite, markUsed,
  parseKeywords, updateUserIcon, deleteUserIcon, iconByKey, ALL, FAVOURITES, RECENT, USER_CATEGORY,
} from '../library.js';

const pngName = (icon) => `${icon.id}.png`;

// Puts an icon on the text label (as its picture) or the bin label (as its icon)
export async function putIconOn(icon, target) {
  const data = await iconBytes(icon);
  markUsed(icon);
  if (target === 'bin') setBinIconBytes(pngName(icon), data);
  else setImageBytes(pngName(icon), data);
}

function IconTile({ icon, onPick, onUse, selected }) {
  const { favourites } = useStore(library);
  return html`<button class=${selected ? 'icon-tile selected' : 'icon-tile'} title=${icon.title} aria-pressed=${selected}
    onClick=${() => onPick(icon)} onDblClick=${onUse ? () => onUse(icon) : undefined}>
    <span class="icon-art"><img src=${iconUrl(icon)} alt="" loading="lazy" /></span>
    <span class="icon-title">${icon.title}</span>
    ${favourites.includes(icon.key) && html`<span class="icon-fav" aria-label="Favourite"><${Icon} name="star" size=${14} filled /></span>`}
  </button>`;
}

// The views: chips that scroll sideways on a phone, a list down the side on a wide screen
function ViewList({ view, setView, wide }) {
  const counts = views().map((v) => [v, viewCount(v)]).filter(([v, n]) => n > 0 || v === ALL || v === view);
  if (!wide) {
    return html`<div class="view-chips" role="tablist">
      ${counts.map(([v, n]) => html`
        <button role="tab" aria-selected=${v === view} class=${v === view ? 'on' : ''} onClick=${() => setView(v)}>
          ${v}<span class="count">${n}</span>
        </button>`)}
    </div>`;
  }
  // All, Favourites and Recently used first, then the categories
  const special = new Set([ALL, FAVOURITES, RECENT]);
  const row = ([v, n]) => html`<button role="tab" aria-selected=${v === view} class=${v === view ? 'on' : ''}
    onClick=${() => setView(v)}><span>${v}</span><span class="count">${n}</span></button>`;
  return html`<nav class="view-list" role="tablist" aria-label="Categories">
    ${counts.filter(([v]) => special.has(v)).map(row)}
    <span class="view-list-head">Categories</span>
    ${counts.filter(([v]) => !special.has(v)).map(row)}
  </nav>`;
}

// Search box, views and the grid of icons
function IconBrowser({ onPick, onUse, view, setView, query, setQuery, selectedKey, wide = false, autoFocus = false }) {
  const lib = useStore(library);
  if (!lib.ready) return html`<p class="hint">Loading icons…</p>`;
  const icons = listIcons(view, query);
  let empty = 'No icons match your search.';
  if (!query) {
    if (view === FAVOURITES) empty = 'Tap the star on an icon to keep it here.';
    else if (view === RECENT) empty = 'Icons you put on labels show up here.';
    else if (view === USER_CATEGORY) empty = 'Icons you add from your own pictures show up here.';
  }
  const search = html`<label class="search-box">
    <${Icon} name="search" size=${18} />
    <input type="search" placeholder="Search icons" value=${query} autoFocus=${autoFocus}
      onInput=${(e) => setQuery(e.currentTarget.value)} />
  </label>`;
  const grid = icons.length
    ? html`<div class="icon-grid">${icons.map((icon) => html`<${IconTile} key=${icon.key} icon=${icon}
        selected=${icon.key === selectedKey} onPick=${onPick} onUse=${onUse} />`)}</div>`
    : html`<p class="hint empty-note">${empty}</p>`;
  if (!wide) {
    return html`<div class="icon-browser">${search}<${ViewList} view=${view} setView=${setView} />${grid}</div>`;
  }
  return html`<div class="icon-browser wide">
    <${ViewList} view=${view} setView=${setView} wide />
    <div class="browser-main">
      <div class="browser-head">${search}<span class="hint">${icons.length} ${icons.length === 1 ? 'icon' : 'icons'}</span></div>
      <div class="browser-grid">${grid}</div>
    </div>
  </div>`;
}

function useBrowserState() {
  const [view, setView] = useState(ALL);
  const [query, setQuery] = useState('');
  return { view, setView, query, setQuery };
}

// How the icon comes out on a 12 mm bin label
function PrintPreview({ icon }) {
  const { phase } = useStore(boot);
  const [url, setUrl] = useState(null);
  useEffect(() => {
    if (phase !== 'ready') return undefined;
    let cancelled = false;
    let made = null;
    iconBytes(icon).then(iconPrintPreview).then((png) => {
      if (cancelled) return;
      made = URL.createObjectURL(new Blob([png], { type: 'image/png' }));
      setUrl(made);
    }).catch((err) => console.warn(err));
    return () => { cancelled = true; if (made) URL.revokeObjectURL(made); };
  }, [icon.key, icon.png, phase]);
  return html`<figure class="print-preview">
    <span class="icon-art">${url ? html`<img src=${url} alt="" />` : null}</span>
    <figcaption>On the label</figcaption>
  </figure>`;
}

function UserIconFields({ icon }) {
  const { categories } = useStore(library);
  const [title, setTitle] = useState(icon.title);
  const [keywords, setKeywords] = useState(icon.keywords.join(', '));
  useEffect(() => { setTitle(icon.title); setKeywords(icon.keywords.join(', ')); }, [icon.key]);
  return html`<div class="user-icon-fields">
    <${Field} label="Name">
      <input type="text" value=${title} onInput=${(e) => setTitle(e.currentTarget.value)}
        onBlur=${() => updateUserIcon(icon.key, { title })} />
    <//>
    <${Field} label="Category">
      <select value=${icon.category} onChange=${(e) => updateUserIcon(icon.key, { category: e.currentTarget.value })}>
        ${[USER_CATEGORY, ...categories].map((c) => html`<option value=${c}>${c}</option>`)}
      </select>
    <//>
    <${Field} label="Search words" hint="Separate with commas">
      <input type="text" value=${keywords} onInput=${(e) => setKeywords(e.currentTarget.value)}
        onBlur=${() => updateUserIcon(icon.key, { keywords: parseKeywords(keywords) })} />
    <//>
  </div>`;
}

// What the icon is, how it prints, and what to do with it. In the picker, the main button
// puts it on the label being edited; on the Icons page it can go on either kind of label.
function DetailsBody({ icon, onClose, onEdit, onUse }) {
  const lib = useStore(library);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => setConfirmDelete(false), [icon.key]);
  const favourite = lib.favourites.includes(icon.key);

  const use = async (target) => {
    await putIconOn(icon, target);
    onClose();
    if (target === 'bin') setMode('bin');
    else setMode('text');
    location.hash = '#/label';
    say(`${icon.title} is on the ${target === 'bin' ? 'bin label' : 'label'}.`);
  };
  const download = async () => downloadBlob(new Blob([await iconBytes(icon)], { type: 'image/png' }), pngName(icon));
  const remove = () => {
    deleteUserIcon(icon.key);
    onClose();
  };

  return html`<div class="icon-details">
    <div class="icon-previews">
      <figure class="big-icon"><span class="icon-art"><img src=${iconUrl(icon)} alt="" /></span><figcaption>${icon.category}</figcaption></figure>
      <${PrintPreview} icon=${icon} />
    </div>
    ${icon.user ? html`<${UserIconFields} icon=${icon} />`
      : icon.keywords.length > 0 && html`<p class="hint keywords">${icon.keywords.join(', ')}</p>`}
    <div class="sheet-actions">
      ${onUse
        ? html`<button class="primary" onClick=${() => onUse(icon)}>Use this icon</button>`
        : html`<button class="primary" onClick=${() => use('text')}>Use on text label</button>
          <button class="secondary" onClick=${() => use('bin')}>Use on bin label</button>`}
    </div>
    <div class="sheet-actions minor">
      <button class=${favourite ? 'link-button on' : 'link-button'} aria-pressed=${favourite} onClick=${() => toggleFavourite(icon)}>
        <${Icon} name="star" size=${18} filled=${favourite} />${favourite ? 'Favourite' : 'Add to favourites'}
      </button>
      ${onEdit && (icon.user
        ? html`<button class="link-button" onClick=${() => onEdit({ kind: 'edit', icon })}><${Icon} name="edit" size=${18} />Edit</button>`
        : html`<button class="link-button" onClick=${() => onEdit({ kind: 'copy', icon })}><${Icon} name="edit" size=${18} />Make my own copy</button>`)}
      <button class="link-button" onClick=${download}><${Icon} name="download" size=${18} />Download</button>
      ${icon.user && onEdit && (confirmDelete
        ? html`<button class="link-button danger" onClick=${remove}><${Icon} name="trash" size=${18} />Delete for good</button>`
        : html`<button class="link-button" onClick=${() => setConfirmDelete(true)}><${Icon} name="trash" size=${18} />Delete</button>`)}
    </div>
  </div>`;
}

// On a wide screen the details sit in a panel beside the grid, like the desktop library
function DetailsPanel({ icon, ...rest }) {
  return html`<aside class="details-panel">
    ${icon
      ? html`<h2>${icon.title}</h2><${DetailsBody} icon=${icon} ...${rest} />`
      : html`<p class="hint empty-note">Pick an icon to see how it prints on a label.</p>`}
  </aside>`;
}

export function IconsPage() {
  const { phase } = useStore(boot);
  const { status } = useStore(app);
  useStore(library);
  const wide = useWide();
  const browser = useBrowserState();
  const [selected, setSelected] = useState(null);
  const [editing, setEditing] = useState(null);
  const fileRef = useRef(null);
  // On a wide screen the panel never stands empty: until an icon is picked it shows the first one
  const icon = (selected && iconByKey(selected)) || (wide ? listIcons(browser.view, browser.query)[0] || null : null);
  const onFile = async (e) => {
    const file = e.currentTarget.files[0];
    e.currentTarget.value = '';
    if (file) setEditing({ kind: 'picture', data: new Uint8Array(await file.arrayBuffer()), name: file.name });
  };
  const edit = (start) => { if (!wide) setSelected(null); setEditing(start); };
  const saved = (saved) => {
    say(`Saved ${saved.title}.`);
    browser.setQuery('');
    browser.setView(saved.category);
    setSelected(saved.key);
  };
  const details = { onClose: () => setSelected(null), onEdit: edit };
  return html`<section class="icons-page">
    <header class="page-head">
      <p class="hint">${wide ? 'Click an icon to see how it prints. Double-click puts it on a label.' : 'Tap an icon to see how it prints and put it on a label.'}</p>
      <button class="secondary" disabled=${phase !== 'ready'} onClick=${() => fileRef.current.click()}>
        <${Icon} name="plus" size=${18} />Add your own
      </button>
      <input ref=${fileRef} type="file" accept="image/*" hidden onChange=${onFile} />
    </header>
    ${status.text && html`<p class=${`status-line${status.error ? ' error' : ''}`} role="status">${status.text}</p>`}
    ${wide
      ? html`<div class="library-layout card">
          <${IconBrowser} ...${browser} wide selectedKey=${icon ? icon.key : null} onPick=${(i) => setSelected(i.key)} />
          <${DetailsPanel} icon=${icon} ...${details} />
        </div>`
      : html`<div class="card"><${IconBrowser} ...${browser} onPick=${(i) => setSelected(i.key)} /></div>
        <${Sheet} open=${!!icon} title=${icon ? icon.title : ''} onClose=${details.onClose}>
          ${icon && html`<${DetailsBody} icon=${icon} ...${details} />`}
        <//>`}
    <${IconEditorSheet} start=${editing} onClose=${() => setEditing(null)} onSaved=${saved} />
  </section>`;
}

// The library in a sheet. On a phone, tapping an icon puts it on the label right away; on a
// wide screen it shows the details first, and Use this icon (or a double-click) puts it on.
export function IconPickerSheet({ open, target, onClose }) {
  useStore(library);
  const wide = useWide();
  const browser = useBrowserState();
  const [selected, setSelected] = useState(null);
  useEffect(() => { if (!open) setSelected(null); }, [open]);
  const use = async (icon) => {
    await putIconOn(icon, target);
    onClose();
  };
  const icon = (selected && iconByKey(selected)) || (wide ? listIcons(browser.view, browser.query)[0] || null : null);
  return html`<${Sheet} open=${open} wide=${wide} title=${target === 'bin' ? 'Pick an icon for the bin label' : 'Pick an icon'} onClose=${onClose}>
    ${wide
      ? html`<div class="library-layout picker">
          <${IconBrowser} ...${browser} wide autoFocus selectedKey=${icon ? icon.key : null} onPick=${(i) => setSelected(i.key)} onUse=${use} />
          <${DetailsPanel} icon=${icon} onClose=${onClose} onUse=${use} />
        </div>`
      : html`<div class="picker-body"><${IconBrowser} ...${browser} onPick=${use} /></div>`}
  <//>`;
}
