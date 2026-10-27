// A font menu that shows every font in its own face. A native select can't do that on all
// browsers, so this is a button with a list under it, used like one: arrow keys, Enter, Escape.
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { html } from './html.js';
import { Icon } from './icons.js';
import { fontFace } from './app.js';

function useFace(name) {
  const [family, setFamily] = useState(null);
  useEffect(() => {
    let live = true;
    setFamily(null);
    fontFace(name).then((f) => { if (live) setFamily(f); });
    return () => { live = false; };
  }, [name]);
  return family;
}

const faceStyle = (family) => (family ? { fontFamily: `"${family}", system-ui, sans-serif` } : null);

function FontOption({ name, selected, standard, onPick }) {
  const family = useFace(name);
  return html`<button type="button" role="option" aria-selected=${selected} class=${selected ? 'selected' : ''}
    data-font=${name} onClick=${() => onPick(name)}>
    <span class="font-sample" style=${faceStyle(family)}>${name}</span>
    ${name === standard && html`<span class="font-note">standard</span>`}
  </button>`;
}

// fonts: the font names; standard: one to mark as the app's own choice
export function FontPicker({ id, value, fonts, onChange, standard = null, ariaLabel = 'Font' }) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef(null);
  const listRef = useRef(null);
  const family = useFace(value);
  const close = (refocus = true) => {
    setOpen(false);
    if (refocus) buttonRef.current?.focus({ preventScroll: true });
  };
  const pick = (name) => { close(); if (name !== value) onChange(name); };

  // Placed in the window like the action menus: under the button when there is room, else above
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!open || !list) return;
    const anchor = buttonRef.current.getBoundingClientRect();
    const gap = 6;
    const room = Math.max(window.innerHeight - anchor.bottom, anchor.top) - gap - 8;
    list.style.maxHeight = `${Math.min(360, room)}px`;
    list.style.width = `${Math.max(anchor.width, 240)}px`;
    const height = list.getBoundingClientRect().height;
    const below = anchor.bottom + gap + height <= window.innerHeight - 8 || anchor.top < window.innerHeight - anchor.bottom;
    list.style.top = `${below ? anchor.bottom + gap : anchor.top - gap - height}px`;
    list.style.left = `${Math.max(8, Math.min(anchor.left, window.innerWidth - list.offsetWidth - 8))}px`;
    list.style.visibility = 'visible';
    const current = list.querySelector('[aria-selected="true"]') || list.querySelector('button');
    current?.scrollIntoView({ block: 'nearest' });
    current?.focus({ preventScroll: true });
  }, [open]);
  useEffect(() => {
    if (!open) return undefined;
    const onResize = () => close(false);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [open]);

  const onListKey = (e) => {
    const items = [...listRef.current.querySelectorAll('button')];
    const at = items.indexOf(document.activeElement);
    const go = (i) => { e.preventDefault(); items[Math.max(0, Math.min(items.length - 1, i))]?.focus(); };
    if (e.key === 'Escape' || e.key === 'Tab') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowDown') go(at + 1);
    else if (e.key === 'ArrowUp') go(at - 1);
    else if (e.key === 'Home') go(0);
    else if (e.key === 'End') go(items.length - 1);
  };
  const onButtonKey = (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); setOpen(true); }
  };

  return html`<span class="font-picker">
    <button id=${id} ref=${buttonRef} type="button" class="font-picker-button" aria-haspopup="listbox"
      aria-expanded=${open} aria-label=${`${ariaLabel}: ${value}`} onClick=${() => setOpen(!open)} onKeyDown=${onButtonKey}>
      <span class="font-sample" style=${faceStyle(family)}>${value}</span>
      <${Icon} name="chevron" size=${18} />
    </button>
    ${open && html`<div class="menu-backdrop" onClick=${() => close(false)}></div>
      <div ref=${listRef} class="font-list" role="listbox" aria-label=${ariaLabel} onKeyDown=${onListKey}>
        ${fonts.map((name) => html`<${FontOption} key=${name} name=${name} selected=${name === value}
          standard=${standard} onPick=${pick} />`)}
      </div>`}
  </span>`;
}
