// Shared controls. They are plain inputs underneath, so the keyboard and screen readers work.
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { html } from './html.js';
import { Icon } from './icons.js';

let nextId = 0;
const useId = (prefix) => {
  const ref = useRef(null);
  if (ref.current === null) ref.current = `${prefix}-${++nextId}`;
  return ref.current;
};

export function Field({ label, hint, children }) {
  return html`<div class="field">
    ${label && html`<span class="field-label">${label}</span>`}
    ${children}
    ${hint && html`<span class="hint">${hint}</span>`}
  </div>`;
}

// One choice out of a few, shown side by side: [['left', 'Left'], ['center', 'Center']]
export function Segmented({ label, ariaLabel, options, value, onChange, disabled = false }) {
  const name = useId('seg');
  return html`<${Field} label=${label}>
    <div class="segmented" role="radiogroup" aria-label=${label || ariaLabel}>
      ${options.map(([optionValue, text]) => html`
        <label class=${optionValue === value ? 'selected' : ''}>
          <input type="radio" name=${name} value=${optionValue} checked=${optionValue === value}
            disabled=${disabled} onChange=${() => onChange(optionValue)} />
          <span>${text}</span>
        </label>`)}
    </div>
  <//>`;
}

export function Select({ label, options, value, onChange, disabled = false }) {
  const id = useId('sel');
  return html`<div class="field">
    ${label && html`<label class="field-label" for=${id}>${label}</label>`}
    <select id=${id} value=${value} disabled=${disabled} onChange=${(e) => onChange(e.currentTarget.value)}>
      ${options.map(([optionValue, text]) => html`<option value=${optionValue}>${text}</option>`)}
    </select>
  </div>`;
}

export function Slider({ label, min, max, step = 1, value, format = String, onChange, disabled = false, display }) {
  const id = useId('range');
  return html`<div class="field slider">
    <div class="slider-head">
      <label class="field-label" for=${id}>${label}</label>
      <output for=${id}>${display ?? format(value)}</output>
    </div>
    <input id=${id} type="range" min=${min} max=${max} step=${step} value=${value} disabled=${disabled}
      onInput=${(e) => onChange(Number(e.currentTarget.value))} />
  </div>`;
}

export function Toggle({ label, checked, onChange, disabled = false }) {
  return html`<label class="toggle">
    <input type="checkbox" role="switch" checked=${checked} disabled=${disabled}
      onChange=${(e) => onChange(e.currentTarget.checked)} />
    <span class="toggle-track" aria-hidden="true"></span>
    <span>${label}</span>
  </label>`;
}

// A card whose body folds away; the open state is remembered per section for this visit
const openSections = new Map();
export function Section({ id, title, summary, defaultOpen = true, children }) {
  const open = openSections.has(id) ? openSections.get(id) : defaultOpen;
  return html`<details class="card section" open=${open}
    onToggle=${(e) => openSections.set(id, e.currentTarget.open)}>
    <summary><span class="section-title">${title}</span>${summary && html`<span class="section-summary">${summary}</span>`}</summary>
    <div class="section-body">${children}</div>
  </details>`;
}

// A dialog that slides up from the bottom on a phone and sits in the middle on a wide screen
export function Sheet({ open, title, onClose, children, wide = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  // Escape asks onClose like the close button does, so a sheet with unsaved work can say no
  return html`<dialog ref=${ref} class=${wide ? 'sheet wide' : 'sheet'} onClose=${onClose}
    onCancel=${(e) => { e.preventDefault(); onClose(); }}
    onClick=${(e) => { if (e.target === ref.current) onClose(); }}>
    <div class="sheet-body">
      <header class="sheet-head">
        <h2>${title}</h2>
        <button class="icon-button" aria-label="Close" onClick=${onClose}><${Icon} name="close" /></button>
      </header>
      ${open && children}
    </div>
  </dialog>`;
}

// A small menu of actions next to its button. It is placed in the window, not in the page,
// so it never sticks out of a scrolling panel: under the button when there is room, else above.
export function Menu({ open, onClose, items }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const menu = ref.current;
    if (!open || !menu) return;
    const anchor = menu.parentElement.getBoundingClientRect();
    const { width, height } = menu.getBoundingClientRect();
    const gap = 6;
    const below = anchor.bottom + gap + height <= window.innerHeight - 8 || anchor.top - gap - height < 8;
    menu.style.top = `${below ? anchor.bottom + gap : anchor.top - gap - height}px`;
    menu.style.left = `${Math.max(8, Math.min(anchor.right - width, window.innerWidth - width - 8))}px`;
    menu.style.visibility = 'visible';
    menu.querySelector('button:not(:disabled)')?.focus({ preventScroll: true });
  }, [open]);
  useEffect(() => {
    if (!open) return undefined;
    window.addEventListener('resize', onClose);
    return () => window.removeEventListener('resize', onClose);
  }, [open]);
  if (!open) return null;
  return html`<div class="menu-backdrop" onClick=${onClose} onWheel=${onClose}></div>
    <div ref=${ref} class="menu" role="menu" onKeyDown=${(e) => { if (e.key === 'Escape') onClose(); }}>
      ${items.filter(Boolean).map((item) => html`<button role="menuitem" disabled=${item.disabled}
        onClick=${() => { onClose(); item.action(); }}>
        ${item.icon && html`<${Icon} name=${item.icon} />`}<span>${item.label}</span>
      </button>`)}
    </div>`;
}

// True while the window is at least `width` pixels wide (the desktop layout starts at 900)
export function useWide(width = 900) {
  const query = `(min-width: ${width}px)`;
  const [wide, setWide] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setWide(list.matches);
    list.addEventListener('change', onChange);
    onChange();
    return () => list.removeEventListener('change', onChange);
  }, [query]);
  return wide;
}

// Hands a file to the browser to save
export function downloadBlob(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement('a'), { href: url, download: fileName });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
