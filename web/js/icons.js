// Line icons for the app's own buttons and navigation (24 x 24, drawn with currentColor)
import { html } from './html.js';

const PATHS = {
  label: html`<path d="M3 11.6V4a1 1 0 0 1 1-1h7.6a1 1 0 0 1 .7.3l8.4 8.4a1 1 0 0 1 0 1.4l-7.6 7.6a1 1 0 0 1-1.4 0L3.3 12.3a1 1 0 0 1-.3-.7z"/><circle cx="7.5" cy="7.5" r="1.5"/>`,
  queue: html`<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" stroke-width="3"/>`,
  icons: html`<rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/>`,
  templates: html`<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M9 9v11"/>`,
  settings: html`<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>`,
  printer: html`<path d="M7 8V3h10v5"/><rect x="3" y="8" width="18" height="9" rx="2"/><path d="M7 14h10v7H7z"/>`,
  more: html`<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>`,
  close: html`<path d="M6 6l12 12M18 6L6 18"/>`,
  image: html`<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>`,
  download: html`<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>`,
  feed: html`<path d="M4 12h12M12 7l5 5-5 5M20 5v14"/>`,
  help: html`<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01"/>`,
  column: html`<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>`,
  edit: html`<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/>`,
  up: html`<path d="M12 19V5M6 11l6-6 6 6"/>`,
  down: html`<path d="M12 5v14M6 13l6 6 6-6"/>`,
  star: html`<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>`,
  search: html`<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>`,
  trash: html`<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>`,
  plus: html`<path d="M12 5v14M5 12h14"/>`,
  minus: html`<path d="M5 12h14"/>`,
  grip: html`<path d="M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01" stroke-width="3"/>`,
  undo: html`<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>`,
  'rotate-left': html`<path d="M4 4v6h6"/><path d="M4.5 10A8 8 0 1 1 6 16.5"/>`,
  'rotate-right': html`<path d="M20 4v6h-6"/><path d="M19.5 10A8 8 0 1 0 18 16.5"/>`,
  refresh: html`<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>`,
  heart: html`<path d="M12 20s-7-4.4-9-9a4.8 4.8 0 0 1 9-3 4.8 4.8 0 0 1 9 3c-2 4.6-9 9-9 9z"/>`,
  github: html`<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.9a3.4 3.4 0 0 0-.9-2.6c3.1-.4 6.4-1.5 6.4-7A5.4 5.4 0 0 0 20 4.8 5.1 5.1 0 0 0 19.9 1S18.7.7 16 2.5a13.4 13.4 0 0 0-7 0C6.3.7 5.1 1 5.1 1A5.1 5.1 0 0 0 5 4.8a5.4 5.4 0 0 0-1.5 3.8c0 5.4 3.3 6.6 6.4 7A3.4 3.4 0 0 0 9 18.1V22"/>`,
  cloud: html`<path d="M7 18h10a4 4 0 0 0 .6-8 6 6 0 0 0-11.4 1.5A3.3 3.3 0 0 0 7 18z"/>`,
};

export function Icon({ name, size = 22, filled = false }) {
  return html`<svg class=${filled ? 'icon filled' : 'icon'} width=${size} height=${size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true">${PATHS[name]}</svg>`;
}
