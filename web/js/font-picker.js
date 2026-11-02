// Font menus that show every font in its own face. A native select can't do that on all
// browsers, so these are buttons with a list under them.
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { html } from './html.js';
import { Icon } from './icons.js';
import { Field, Segmented } from './ui.js';
import { useStore } from './state.js';
import { boot, addFont, fontFace } from './app.js';

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

// Font names are family plus style ("Arimo Medium", "Inter Bold Italic", plain "Arimo" for
// Regular), so the menus list each family once and the style is picked beside it.
const WEIGHTS = ['Thin', 'ExtraLight', 'Light', 'Regular', 'Medium', 'SemiBold', 'Bold', 'ExtraBold', 'Black'];

export function splitFont(name) {
  let family = name;
  const italic = family.endsWith(' Italic');
  if (italic) family = family.slice(0, -7);
  const weight = WEIGHTS.find((w) => family.endsWith(` ${w}`)) || 'Regular';
  if (family.endsWith(` ${weight}`)) family = family.slice(0, -weight.length - 1);
  const style = italic ? (weight === 'Regular' ? 'Italic' : `${weight} Italic`) : weight;
  return { family, style };
}

const styleRank = (style) => WEIGHTS.indexOf(style.replace(/ ?Italic$/, '') || 'Regular') * 2 + (style.endsWith('Italic') ? 1 : 0);

// family -> its fonts, lightest first: [{ name, style }]
export function fontFamilies(fonts) {
  const families = new Map();
  for (const name of fonts) {
    const { family, style } = splitFont(name);
    if (!families.has(family)) families.set(family, []);
    families.get(family).push({ name, style });
  }
  for (const styles of families.values()) styles.sort((a, b) => styleRank(a.style) - styleRank(b.style));
  return families;
}

// The font menus list the bundled families in groups, like a label maker's font list.
// Added fonts and any others go last, under "More fonts".
const FONT_GROUPS = [
  ['Everyday', ['Arimo', 'Inter', 'Roboto', 'Open Sans', 'Montserrat', 'Lexend', 'Nunito', 'Atkinson Hyperlegible', 'Varela Round']],
  ['Bold and condensed', ['Barlow Condensed', 'Oswald', 'Bebas Neue', 'Anton', 'Bungee', 'Lilita One', 'Black Ops One', 'Bangers', 'Shrikhand', 'Righteous', 'Fredoka']],
  ['Script and handwriting', ['Pacifico', 'Great Vibes', 'Caveat', 'Kaushan Script', 'Parisienne', 'Allura', 'Sacramento', 'Patrick Hand', 'Comic Neue', 'Indie Flower', 'Amatic SC']],
  ['Classic and decorative', ['EB Garamond', 'Zilla Slab', 'Cinzel', 'UnifrakturMaguntia', 'Uncial Antiqua', 'Poiret One', 'Monoton']],
  ['Typewriter and digital', ['JetBrains Mono', 'Courier Prime', 'Space Mono', 'VT323', 'Silkscreen', 'Audiowide', 'Allerta Stencil']],
];
const GROUP_OF = new Map(FONT_GROUPS.flatMap(([group, names], i) => names.map((n, j) => [n, { group, rank: i * 100 + j }])));
const OTHER_GROUP = { group: 'More fonts', rank: 10000 };

// The font a family switch lands on: the same style if the family has it, else its Regular
function inFamily(styles, style) {
  return (styles.find((s) => s.style === style) || styles.find((s) => s.style === 'Regular') || styles[0]).name;
}

function Face({ name, text }) {
  const family = useFace(name);
  return html`<span class="font-sample" style=${faceStyle(family)}>${text}</span>`;
}

function Option({ option, selected, onPick }) {
  return html`<button type="button" role="option" aria-selected=${selected} class=${selected ? 'selected' : ''}
    data-font=${option.key} onClick=${() => onPick(option.key)}>
    <${Face} name=${option.face} text=${option.text} />
    ${option.note && html`<span class="font-note">${option.note}</span>`}
  </button>`;
}

// A button with a list under it, used like a select: arrow keys, Enter, Escape.
// options: [{ key, text, face, note }], each shown in the font named by face.
function Picker({ id, value, options, onChange, ariaLabel, disabled = false }) {
  // Headers only when the list has more than one group
  const grouped = new Set(options.map((o) => o.group).filter(Boolean)).size > 1;
  const [open, setOpen] = useState(false);
  const buttonRef = useRef(null);
  const listRef = useRef(null);
  const current = options.find((o) => o.key === value) || { text: value, face: value };
  const close = (refocus = true) => {
    setOpen(false);
    if (refocus) buttonRef.current?.focus({ preventScroll: true });
  };
  const pick = (key) => { close(); if (key !== value) onChange(key); };
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
      aria-expanded=${open} aria-label=${`${ariaLabel}: ${current.text}`} disabled=${disabled}
      onClick=${() => setOpen(!open)} onKeyDown=${onButtonKey}>
      <${Face} name=${current.face} text=${current.text} />
      <${Icon} name="chevron" size=${18} />
    </button>
    ${open && html`<div class="menu-backdrop" onClick=${() => close(false)}></div>
      <div ref=${listRef} class="font-list" role="listbox" aria-label=${ariaLabel} onKeyDown=${onListKey}>
        ${options.map((option, i) => html`${grouped && option.group !== (options[i - 1] || {}).group
          && html`<div class="font-group" role="presentation">${option.group}</div>`}<${Option} key=${option.key} option=${option}
          selected=${option.key === value} onPick=${pick} />`)}
      </div>`}
  </span>`;
}

function useFamilies(value, fonts, standard) {
  const families = fontFamilies(fonts.includes(value) ? fonts : [...fonts, value]);
  const { family, style } = splitFont(value);
  const standardFamily = standard && splitFont(standard).family;
  const familyOptions = [...families].map(([name, styles], i) => {
    const { group, rank } = GROUP_OF.get(name) || { ...OTHER_GROUP, rank: OTHER_GROUP.rank + i };
    return { key: name, text: name, face: inFamily(styles, 'Regular'), note: name === standardFamily ? 'standard' : null, group, rank };
  }).sort((a, b) => a.rank - b.rank);
  const styles = families.get(family);
  const styleOptions = styles.map((s) => ({ key: s.name, text: s.style, face: s.name, note: s.name === standard ? 'standard' : null }));
  const pickFamily = (name, onChange) => onChange(inFamily(families.get(name), style));
  return { family, familyOptions, styleOptions, pickFamily };
}

// A font menu with each family once, and the family's styles in a second, smaller menu.
// For tight spots like the Settings rows. standard: a font to mark as the app's own choice.
export function FontPicker({ value, fonts, onChange, standard = null, ariaLabel = 'Font' }) {
  const { family, familyOptions, styleOptions, pickFamily } = useFamilies(value, fonts, standard);
  return html`<span class="font-picker-stack">
    <${Picker} value=${family} options=${familyOptions} ariaLabel=${ariaLabel} onChange=${(f) => pickFamily(f, onChange)} />
    <${Picker} value=${value} options=${styleOptions} ariaLabel=${`${ariaLabel} weight`}
      disabled=${styleOptions.length < 2} onChange=${onChange} />
  </span>`;
}

// Up to four styles side by side; more than that (an added font family) in a menu
function WeightField({ value, styleOptions, onChange }) {
  if (styleOptions.length > 4) {
    return html`<${Field} label="Weight">
      <${Picker} value=${value} options=${styleOptions} ariaLabel="Weight" onChange=${onChange} />
    <//>`;
  }
  return html`<${Segmented} label="Weight" value=${value} disabled=${styleOptions.length < 2} onChange=${onChange}
    options=${styleOptions.map((o) => [o.key, html`<${Face} name=${o.face} text=${o.text} />`])} />`;
}

// A labelled font menu with an Add font button next to it and the family's weights under it.
// An added font is chosen right away.
export function FontField({ label, value, fonts, onChange, standard = null }) {
  const { phase } = useStore(boot);
  const fileRef = useRef(null);
  const { family, familyOptions, styleOptions, pickFamily } = useFamilies(value, fonts, standard);
  const onFile = async (e) => {
    const file = e.currentTarget.files[0];
    e.currentTarget.value = '';
    const name = file && await addFont(file);
    if (name) onChange(name);
  };
  return html`<div class="row">
    <${Field} label=${label}>
      <${Picker} value=${family} options=${familyOptions} ariaLabel=${label} onChange=${(f) => pickFamily(f, onChange)} />
    <//>
    <button class="secondary add-font" disabled=${phase !== 'ready'} onClick=${() => fileRef.current.click()}>Add font</button>
    <input ref=${fileRef} type="file" accept=".ttf,.otf,.ttc" hidden onChange=${onFile} />
  </div>
  <${WeightField} value=${value} styleOptions=${styleOptions} onChange=${onChange} />`;
}
