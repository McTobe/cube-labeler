// The Icons page: browse and search the icon library, keep favourites, add your own icons,
// and put an icon on a text label or a bin label. IconPickerSheet is the same browser in a
// sheet, for picking an icon straight from the label editors.
import { useEffect, useRef, useState } from 'preact/hooks';
import { html } from '../html.js';
import { Icon } from '../icons.js';
import { Field, Sheet, downloadBlob } from '../ui.js';
import { useStore } from '../state.js';
import {
  app, boot, say, setMode, setImageBytes, setBinIconBytes, iconPrintPreview,
} from '../app.js';
import { IconEditorSheet } from './icon-editor.js';
import {
  library, views, listIcons, viewCount, iconUrl, iconBytes, isFavourite, toggleFavourite, markUsed,
  parseKeywords, saveUserIcon, updateUserIcon, deleteUserIcon, ALL, USER_CATEGORY,
} from '../library.js';

const pngName = (icon) => `${icon.id}.png`;

// Puts an icon on the text label (as its picture) or the bin label (as its icon)
export async function putIconOn(icon, target) {
  const data = await iconBytes(icon);
  markUsed(icon);
  if (target === 'bin') setBinIconBytes(pngName(icon), data);
  else setImageBytes(pngName(icon), data);
}

function IconTile({ icon, onPick }) {
  const { favourites } = useStore(library);
  return html`<button class="icon-tile" title=${icon.title} onClick=${() => onPick(icon)}>
    <span class="icon-art"><img src=${iconUrl(icon)} alt="" loading="lazy" /></span>
    <span class="icon-title">${icon.title}</span>
    ${favourites.includes(icon.key) && html`<span class="icon-fav" aria-label="Favourite"><${Icon} name="star" size=${14} filled /></span>`}
  </button>`;
}

// Search box, view chips and the grid of icons
function IconBrowser({ onPick, view, setView, query, setQuery, autoFocus = false }) {
  const lib = useStore(library);
  if (!lib.ready) return html`<p class="hint">Loading icons…</p>`;
  const icons = listIcons(view, query);
  const counts = views().map((v) => [v, viewCount(v)]);
  let empty = 'No icons match your search.';
  if (!query) {
    if (view === 'Favourites') empty = 'Tap the star on an icon to keep it here.';
    else if (view === 'Recently used') empty = 'Icons you put on labels show up here.';
    else if (view === USER_CATEGORY) empty = 'Icons you add from your own pictures show up here.';
  }
  return html`<div class="icon-browser">
    <label class="search-box">
      <${Icon} name="search" size=${18} />
      <input type="search" placeholder="Search icons" value=${query} autoFocus=${autoFocus}
        onInput=${(e) => setQuery(e.currentTarget.value)} />
    </label>
    <div class="view-chips" role="tablist">
      ${counts.filter(([v, n]) => n > 0 || v === ALL || v === view).map(([v, n]) => html`
        <button role="tab" aria-selected=${v === view} class=${v === view ? 'on' : ''} onClick=${() => setView(v)}>
          ${v}<span class="count">${n}</span>
        </button>`)}
    </div>
    ${icons.length
      ? html`<div class="icon-grid">${icons.map((icon) => html`<${IconTile} key=${icon.key} icon=${icon} onPick=${onPick} />`)}</div>`
      : html`<p class="hint empty-note">${empty}</p>`}
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

function IconDetails({ iconKey, onClose, onEdit }) {
  const lib = useStore(library);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => setConfirmDelete(false), [iconKey]);
  const icon = iconKey ? listIcons(ALL).find((i) => i.key === iconKey) : null;
  const favourite = icon && lib.favourites.includes(icon.key);

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

  return html`<${Sheet} open=${!!icon} title=${icon ? icon.title : ''} onClose=${onClose}>
    ${icon && html`<div class="icon-details">
      <div class="icon-previews">
        <figure class="big-icon"><span class="icon-art"><img src=${iconUrl(icon)} alt="" /></span><figcaption>${icon.category}</figcaption></figure>
        <${PrintPreview} icon=${icon} />
      </div>
      ${icon.user ? html`<${UserIconFields} icon=${icon} />`
        : icon.keywords.length > 0 && html`<p class="hint keywords">${icon.keywords.join(', ')}</p>`}
      <div class="sheet-actions">
        <button class="primary" onClick=${() => use('text')}>Use on text label</button>
        <button class="secondary" onClick=${() => use('bin')}>Use on bin label</button>
      </div>
      <div class="sheet-actions minor">
        <button class=${favourite ? 'link-button on' : 'link-button'} aria-pressed=${favourite} onClick=${() => toggleFavourite(icon)}>
          <${Icon} name="star" size=${18} filled=${favourite} />${favourite ? 'Favourite' : 'Add to favourites'}
        </button>
        ${icon.user
          ? html`<button class="link-button" onClick=${() => onEdit({ kind: 'edit', icon })}><${Icon} name="edit" size=${18} />Edit</button>`
          : html`<button class="link-button" onClick=${() => onEdit({ kind: 'copy', icon })}><${Icon} name="edit" size=${18} />Make my own copy</button>`}
        <button class="link-button" onClick=${download}><${Icon} name="download" size=${18} />Download</button>
        ${icon.user && (confirmDelete
          ? html`<button class="link-button danger" onClick=${remove}><${Icon} name="trash" size=${18} />Delete for good</button>`
          : html`<button class="link-button" onClick=${() => setConfirmDelete(true)}><${Icon} name="trash" size=${18} />Delete</button>`)}
      </div>
    </div>`}
  <//>`;
}

export function IconsPage() {
  const { phase } = useStore(boot);
  const { status } = useStore(app);
  const browser = useBrowserState();
  const [selected, setSelected] = useState(null);
  const [editing, setEditing] = useState(null);
  const fileRef = useRef(null);
  const onFile = async (e) => {
    const file = e.currentTarget.files[0];
    e.currentTarget.value = '';
    if (file) setEditing({ kind: 'picture', data: new Uint8Array(await file.arrayBuffer()), name: file.name });
  };
  const edit = (start) => { setSelected(null); setEditing(start); };
  const saved = (icon) => {
    say(`Saved ${icon.title}.`);
    browser.setQuery('');
    browser.setView(icon.category);
    setSelected(icon.key);
  };
  return html`<section class="icons-page">
    <header class="page-head">
      <p class="hint">Tap an icon to see how it prints and put it on a label.</p>
      <button class="secondary" disabled=${phase !== 'ready'} onClick=${() => fileRef.current.click()}>
        <${Icon} name="plus" size=${18} />Add your own
      </button>
      <input ref=${fileRef} type="file" accept="image/*" hidden onChange=${onFile} />
    </header>
    ${status.text && html`<p class=${`status-line${status.error ? ' error' : ''}`} role="status">${status.text}</p>`}
    <div class="card"><${IconBrowser} ...${browser} onPick=${(icon) => setSelected(icon.key)} /></div>
    <${IconDetails} iconKey=${selected} onClose=${() => setSelected(null)} onEdit=${edit} />
    <${IconEditorSheet} start=${editing} onClose=${() => setEditing(null)} onSaved=${saved} />
  </section>`;
}

// The library in a sheet; picking an icon puts it on the label right away
export function IconPickerSheet({ open, target, onClose }) {
  const browser = useBrowserState();
  const pick = async (icon) => {
    await putIconOn(icon, target);
    onClose();
  };
  return html`<${Sheet} open=${open} title="Pick an icon" onClose=${onClose}>
    <div class="picker-body"><${IconBrowser} ...${browser} onPick=${pick} /></div>
  <//>`;
}
